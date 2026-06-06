"""
Lot integrity checker -- verify sku_cogs_lots.qty_remaining is correct.

Runs five checks against the DB and prints an inventory position summary.
Default: prod. Use --env dev to check dev DB.

Usage:
  python setup/check_lots_integrity.py [--env dev|prod]

Checks:
  1. Basic bounds -- no lot with qty_remaining < 0 or > qty_assembled
  2. Own WH: lot qty_remaining == sku_inventory.qty_on_hand (per SKU)
  3. Transfer -> lot balance: TRANSFER_OUT qty == lot qty_assembled (per channel/location)
  4. Consumption vs finalized orders: lots consumed == finalized order units (per channel)
  5. INVENTORY POSITION -- unsold stock summary by location (main output)
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


def _banner(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def _result(label: str, status: str, detail: str = "") -> None:
    sym = {"PASS": "[OK]", "FAIL": "[!!]", "WARN": "[??]"}.get(status, "[??]")
    line = f"  {sym} {label}"
    if detail:
        line += f"  ->  {detail}"
    print(line)


def main(env: str) -> None:
    os.environ["TCB_ENV"] = env
    from tcb.db import get_client
    db = get_client()

    # -- Master lookups --------------------------------------------------------

    channels = {r["channel_id"]: r for r in db.table("channels").select("*").execute().data}
    ch_by_code = {r["code"]: r["channel_id"] for r in channels.values()}

    own_wh_id = ch_by_code.get("OWN_WH")
    if not own_wh_id:
        print("ERROR: OWN_WH channel not found -- cannot run checks.")
        sys.exit(1)

    # Partner channel IDs (non-OWN_WH channels that use TRANSFER_OUT)
    sor_fba_outright_ids = {
        cid for cid, ch in channels.items()
        if ch.get("business_model") in ("FBA", "SOR", "OUTRIGHT")
    }

    loc_by_id = {
        r["location_id"]: r
        for r in db.table("partner_locations").select("location_id,name,code,channel_id").execute().data
    }

    skus = {r["sku_id"]: r["name"] for r in db.table("skus").select("sku_id,name").execute().data}

    # -- Fetch raw data --------------------------------------------------------

    all_lots = db.table("sku_cogs_lots").select(
        "lot_id,sku_id,channel_id,partner_location_id,assembled_at,qty_assembled,qty_remaining,unit_cogs"
    ).execute().data

    sku_inv = db.table("sku_inventory").select(
        "sku_id,channel_id,qty_on_hand"
    ).eq("channel_id", own_wh_id).execute().data

    transfer_txns = db.table("sku_inventory_transactions").select(
        "sku_id,to_channel_id,partner_location_id,quantity"
    ).eq("type", "TRANSFER_OUT").execute().data

    # Finalized orders by channel (status FULFILLED/REPLACEMENT, lot_cogs_finalized=TRUE)
    finalized_orders = db.table("orders").select(
        "sku_id,channel_id,quantity,status,lot_cogs_finalized"
    ).eq("lot_cogs_finalized", True).in_("status", ["FULFILLED", "REPLACEMENT"]).execute().data

    # -------------------------------------------------------------------------
    # CHECK 1: Basic lot bounds
    # -------------------------------------------------------------------------
    _banner("CHECK 1 -- Basic lot bounds (no negatives, no over-assembly)")

    negative_lots = [l for l in all_lots if l["qty_remaining"] < 0]
    over_lots = [l for l in all_lots if l["qty_remaining"] > l["qty_assembled"]]

    if negative_lots:
        _result("Negative qty_remaining", FAIL,
                f"{len(negative_lots)} lot(s): {[l['lot_id'] for l in negative_lots]}")
    else:
        _result("No negative qty_remaining", PASS)

    if over_lots:
        _result("qty_remaining <= qty_assembled", FAIL,
                f"{len(over_lots)} lot(s): {[l['lot_id'] for l in over_lots]}")
    else:
        _result("qty_remaining <= qty_assembled for all lots", PASS)

    total_assembled = sum(l["qty_assembled"] for l in all_lots)
    total_remaining = sum(l["qty_remaining"] for l in all_lots)
    total_consumed  = total_assembled - total_remaining
    print(f"\n  All lots: {len(all_lots)} rows | "
          f"assembled={total_assembled} | remaining={total_remaining} | consumed={total_consumed}")

    # -------------------------------------------------------------------------
    # CHECK 2: Own WH -- lot qty_remaining == sku_inventory.qty_on_hand
    # -------------------------------------------------------------------------
    _banner("CHECK 2 -- Own WH lots <-> sku_inventory.qty_on_hand")

    own_lots: dict[str, int] = defaultdict(int)
    for l in all_lots:
        if l["channel_id"] == own_wh_id and l["partner_location_id"] is None:
            own_lots[l["sku_id"]] += l["qty_remaining"]

    inv_qty: dict[str, int] = {r["sku_id"]: int(r["qty_on_hand"]) for r in sku_inv}

    all_skus_own = set(own_lots.keys()) | set(inv_qty.keys())
    mismatches_own = []
    for sku_id in sorted(all_skus_own):
        lot_q = own_lots.get(sku_id, 0)
        inv_q = inv_qty.get(sku_id, 0)
        if lot_q != inv_q:
            mismatches_own.append((sku_id, lot_q, inv_q))

    if not mismatches_own:
        _result("All Own WH lot totals match sku_inventory", PASS,
                f"{len(all_skus_own)} SKU(s) checked")
    else:
        _result("Own WH lot <-> inventory mismatch", FAIL,
                f"{len(mismatches_own)} SKU(s) diverge:")
        print(f"\n  {'SKU':<14} {'Lot total':>10} {'Inventory':>10} {'Delta':>7}")
        for sku_id, lot_q, inv_q in mismatches_own:
            print(f"  {sku_id:<14} {lot_q:>10} {inv_q:>10} {lot_q - inv_q:>+7}  <-- FIX NEEDED")

    # -------------------------------------------------------------------------
    # CHECK 3: Transfer -> lot balance
    # Every TRANSFER_OUT should create an equal qty in sku_cogs_lots.qty_assembled
    # -------------------------------------------------------------------------
    _banner("CHECK 3 -- TRANSFER_OUT qty == lot qty_assembled (per channel/location)")

    # Group TRANSFER_OUT txns: (sku_id, to_channel_id, partner_location_id) -> qty
    transfer_by_key: dict[tuple, int] = defaultdict(int)
    for t in transfer_txns:
        key = (t["sku_id"], t["to_channel_id"], t.get("partner_location_id"))
        transfer_by_key[key] += int(t["quantity"])

    # Group lot qty_assembled for partner channels
    lot_asm_by_key: dict[tuple, int] = defaultdict(int)
    for l in all_lots:
        if l["channel_id"] == own_wh_id:
            continue  # own WH lots are created by assembly, not transfer
        key = (l["sku_id"], l["channel_id"], l.get("partner_location_id"))
        lot_asm_by_key[key] += int(l["qty_assembled"])

    all_keys = set(transfer_by_key.keys()) | set(lot_asm_by_key.keys())
    mismatches_txfr = []
    for key in sorted(all_keys, key=lambda k: (k[0], k[1] or 0, k[2] or 0)):
        sku_id, ch_id, loc_id = key
        txfr_q = transfer_by_key.get(key, 0)
        lot_q  = lot_asm_by_key.get(key, 0)
        if txfr_q != lot_q:
            mismatches_txfr.append((sku_id, ch_id, loc_id, txfr_q, lot_q))

    if not mismatches_txfr:
        _result("All TRANSFER_OUT qtys match lot qty_assembled", PASS,
                f"{len(all_keys)} key(s) checked")
    else:
        _result("Transfer -> lot mismatch", FAIL,
                f"{len(mismatches_txfr)} key(s) diverge:")
        print(f"\n  {'SKU':<14} {'Channel':<18} {'Location':<28} {'Transferred':>12} {'Lot_asm':>8} {'Delta':>7}")
        for sku_id, ch_id, loc_id, txfr_q, lot_q in mismatches_txfr:
            ch_name  = channels.get(ch_id, {}).get("code", str(ch_id))
            loc_name = loc_by_id.get(loc_id, {}).get("name", str(loc_id)) if loc_id else "--"
            print(f"  {sku_id:<14} {ch_name:<18} {loc_name:<28} {txfr_q:>12} {lot_q:>8} {txfr_q - lot_q:>+7}")

    # -------------------------------------------------------------------------
    # CHECK 4: Lot consumption vs finalized orders (per channel)
    # -------------------------------------------------------------------------
    _banner("CHECK 4 -- Lot consumption vs finalized order units (per channel)")
    print("  Note: Blinkit uses state-level FIFO -- per-WH won't match; channel total should.")

    # Lots consumed per channel (excl own WH -- those are dispatch events, not SOR)
    consumed_by_ch: dict[int, int] = defaultdict(int)
    for l in all_lots:
        if l["channel_id"] == own_wh_id:
            continue
        consumed_by_ch[l["channel_id"]] += int(l["qty_assembled"]) - int(l["qty_remaining"])

    # Finalized order units per channel
    finalized_by_ch: dict[int, int] = defaultdict(int)
    for o in finalized_orders:
        finalized_by_ch[o["channel_id"]] += int(o["quantity"])

    all_ch_ids = set(consumed_by_ch.keys()) | set(finalized_by_ch.keys())
    check4_ok = True
    print(f"\n  {'Channel':<20} {'Lots consumed':>14} {'Finalized orders':>17} {'Delta':>7}")
    for ch_id in sorted(all_ch_ids):
        if ch_id == own_wh_id:
            continue
        ch_name = channels.get(ch_id, {}).get("code", str(ch_id))
        cons = consumed_by_ch.get(ch_id, 0)
        fin  = finalized_by_ch.get(ch_id, 0)
        delta = cons - fin
        marker = "" if delta == 0 else "  <-- mismatch"
        if delta != 0:
            check4_ok = False
        print(f"  {ch_name:<20} {cons:>14} {fin:>17} {delta:>+7}{marker}")

    if check4_ok:
        _result("Lot consumption matches finalized orders for all partner channels", PASS)
    else:
        _result("Consumption/order mismatch found", WARN,
                "Non-zero delta = pending orders not yet finalized OR lot seeding divergence")

    # -------------------------------------------------------------------------
    # CHECK 5: INVENTORY POSITION -- unsold stock by location
    # -------------------------------------------------------------------------
    _banner("CHECK 5 -- UNSOLD INVENTORY POSITION (qty_remaining by location)")
    print("  This is the authoritative view of assembled units not yet sold.\n")

    # Build position: location label -> {sku_id: qty_remaining}
    # Own WH: use sku_inventory (already verified to match lots in Check 2)
    position: dict[str, dict[str, int]] = {}

    # Own WH from sku_inventory (more reliable if Check 2 passes)
    own_pos = {sku_id: q for sku_id, q in inv_qty.items() if q > 0}
    if own_pos:
        position["Own WH (Bengaluru)"] = own_pos

    # Partner locations: aggregate from lots
    partner_pos: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for l in all_lots:
        if l["channel_id"] == own_wh_id:
            continue
        if int(l["qty_remaining"]) <= 0:
            continue
        loc_id = l.get("partner_location_id")
        ch_id  = l["channel_id"]
        label_key = (ch_id, loc_id)
        partner_pos[label_key][l["sku_id"]] += int(l["qty_remaining"])

    for (ch_id, loc_id), sku_qtys in sorted(partner_pos.items(), key=lambda x: (x[0][0], x[0][1] or 0)):
        ch_code  = channels.get(ch_id, {}).get("code", f"ch{ch_id}")
        loc_name = loc_by_id.get(loc_id, {}).get("name", "") if loc_id else ""
        label = f"{ch_code} -- {loc_name}" if loc_name else ch_code
        position[label] = {k: v for k, v in sku_qtys.items() if v > 0}

    # Print summary table
    all_sku_ids = sorted({s for pos in position.values() for s in pos})
    header = f"{'Location':<35}" + "".join(f"{s:>8}" for s in all_sku_ids) + f"{'TOTAL':>8}"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")

    grand_totals: dict[str, int] = defaultdict(int)
    location_totals: dict[str, int] = {}
    for label, sku_qtys in position.items():
        row_total = sum(sku_qtys.values())
        location_totals[label] = row_total
        cells = "".join(f"{sku_qtys.get(s, 0):>8}" for s in all_sku_ids)
        print(f"  {label:<35}{cells}{row_total:>8}")
        for s in all_sku_ids:
            grand_totals[s] += sku_qtys.get(s, 0)

    # Grand total row
    grand_row = "".join(f"{grand_totals.get(s, 0):>8}" for s in all_sku_ids)
    total_all = sum(grand_totals.values())
    print(f"  {'-' * len(header)}")
    print(f"  {'GRAND TOTAL':<35}{grand_row}{total_all:>8}")

    # Warn on any lot at a partner channel with no matching partner_location_id
    unlocated = [
        l for l in all_lots
        if l["channel_id"] != own_wh_id
        and l.get("partner_location_id") is None
        and l["qty_remaining"] > 0
    ]
    if unlocated:
        print(f"\n  [{WARN}] {len(unlocated)} lot(s) at partner channel with no partner_location_id "
              f"(shown above under channel code without WH name):")
        for l in unlocated:
            ch_code = channels.get(l["channel_id"], {}).get("code", "?")
            print(f"       lot_id={l['lot_id']}  sku={l['sku_id']}  ch={ch_code}  "
                  f"qty_remaining={l['qty_remaining']}")

    # -- Summary ---------------------------------------------------------------
    _banner("SUMMARY")
    check_results = [
        (not negative_lots and not over_lots, "Basic bounds"),
        (not mismatches_own,                  "Own WH lots <-> sku_inventory"),
        (not mismatches_txfr,                 "Transfer -> lot balance"),
        (check4_ok,                           "Consumption vs finalized orders"),
    ]
    all_pass = all(ok for ok, _ in check_results)
    for ok, name in check_results:
        _result(name, PASS if ok else FAIL)

    if all_pass:
        print("\n  All checks passed -- lot data is internally consistent.")
        print("  For external verification, run refresh_blinkit_lots.py against a fresh SOH file.")
    else:
        print("\n  One or more checks failed -- investigate before using lot data for planning.")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify sku_cogs_lots integrity")
    parser.add_argument("--env", choices=["dev", "prod"], default="prod")
    args = parser.parse_args()
    main(args.env)
