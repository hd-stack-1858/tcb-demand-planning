"""
Seed sku_cogs_lots from historical ASSEMBLY transactions.

Algorithm per SKU:
  1. Read ASSEMBLY txns (ordered oldest-first), group by (date, unit_cogs).
  2. Get current qty_on_hand at OWN_WH from sku_inventory.
  3. If on_hand > total_assembled: stock was seeded/received outside the app.
     Create a synthetic baseline lot at CATALOG_COGS for the untracked qty,
     dated 2025-12-01 (start of operations) — it sorts first in FIFO.
  4. Apply FIFO reduction across (synthetic + assembly) lots so that
     total qty_remaining = on_hand.
  5. Insert into sku_cogs_lots (OWN_WH only — partner lots are built
     going forward from new TRANSFER_OUTs).

Run once on each DB after migration 008:
  python setup/seed_sku_cogs_lots.py --env dev
  python setup/seed_sku_cogs_lots.py --env prod

Safe to re-run: SKUs that already have lots are skipped.
"""
import os, sys, argparse
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Historical baseline COGS for synthetic lots (stock assembled before the app existed).
# Authoritative values from Himanshu (May 2026) — pre-app, before new item batches.
CATALOG_COGS: dict[str, float] = {
    "TCB001": 441.3, "TCB002": 441.3,
    "TCB003": 700.8, "TCB004": 700.8,
    "TCB005": 472.7, "TCB006": 472.7,
    "TCB007": 609.2,
    "TCB008": 276.3,
    "TCB009": 334.2, "TCB009_1": 334.2,
    "TCB010": 840.2,
    "TCB011": 297.3,
    "TCB012": 305.5,
}

BASELINE_DATE = "2025-12-01"   # sorts before any real assembly date


def main(env: str):
    os.environ["TCB_ENV"] = env
    from tcb.db import get_client
    db = get_client()

    own_wh = db.table("channels").select("channel_id").eq("code", "OWN_WH").single().execute().data
    own_wh_id = own_wh["channel_id"]

    # ── 1. ASSEMBLY txns ─────────────────────────────────────────────────────
    asm_rows = (db.table("sku_inventory_transactions")
                  .select("sku_id, txn_date, unit_cogs, quantity")
                  .eq("type", "ASSEMBLY")
                  .order("txn_date")
                  .execute().data)

    null_cogs = [r for r in asm_rows if not r.get("unit_cogs")]
    if null_cogs:
        print(f"NOTE: {len(null_cogs)} ASSEMBLY txn(s) have NULL unit_cogs — skipped:")
        for r in null_cogs:
            print(f"  sku_id={r['sku_id']}  date={str(r['txn_date'])[:10]}  qty={r['quantity']}")

    good_asm = [r for r in asm_rows if r.get("unit_cogs")]

    # Group into lots (sku_id, date, unit_cogs) → qty_assembled
    lot_map: dict[tuple, dict] = {}
    for r in good_asm:
        assembled_at = str(r["txn_date"])[:10]
        key = (r["sku_id"], assembled_at, float(r["unit_cogs"]))
        if key not in lot_map:
            lot_map[key] = {"sku_id": r["sku_id"], "assembled_at": assembled_at,
                            "unit_cogs": float(r["unit_cogs"]), "qty_assembled": 0}
        lot_map[key]["qty_assembled"] += int(r["quantity"])

    lots_by_sku: dict[str, list] = defaultdict(list)
    for lot in sorted(lot_map.values(), key=lambda l: l["assembled_at"]):
        lots_by_sku[lot["sku_id"]].append(lot)

    # ── 2. Current OWN_WH stock ───────────────────────────────────────────────
    inv_rows = (db.table("sku_inventory")
                  .select("sku_id, qty_on_hand")
                  .eq("channel_id", own_wh_id)
                  .execute().data)
    current_qty: dict[str, int] = {r["sku_id"]: int(r["qty_on_hand"]) for r in inv_rows}

    # All SKUs that have any stock or any assembly history
    all_skus = set(current_qty) | set(lots_by_sku)

    # ── 3+4. Build lot list per SKU ───────────────────────────────────────────
    print(f"\n{'SKU':<12} {'On-hand':>8} {'Assembled':>10} {'Synthetic':>10}  Note")
    print("-" * 65)

    to_insert = []
    for sku_id in sorted(all_skus):
        on_hand        = current_qty.get(sku_id, 0)
        lots           = lots_by_sku.get(sku_id, [])
        total_assembled = sum(l["qty_assembled"] for l in lots)
        synthetic_qty  = max(0, on_hand - total_assembled)

        note = ""

        # Prepend synthetic baseline lot if on_hand exceeds assembly history
        if synthetic_qty > 0:
            catalog_cogs = CATALOG_COGS.get(sku_id)
            if catalog_cogs is None:
                note = f"SKIPPED — no CATALOG_COGS for {sku_id}"
                print(f"{sku_id:<12} {on_hand:>8} {total_assembled:>10} {synthetic_qty:>10}  {note}")
                continue
            lots = [{"sku_id": sku_id, "assembled_at": BASELINE_DATE,
                     "unit_cogs": catalog_cogs, "qty_assembled": synthetic_qty}] + lots
            note = f"synthetic baseline @ {catalog_cogs}"

        total_stock    = total_assembled + synthetic_qty
        total_dispatched = total_stock - on_hand   # always >= 0 now

        # FIFO: consume oldest lots first up to total_dispatched
        remaining_to_consume = total_dispatched
        for lot in lots:
            consume = min(lot["qty_assembled"], remaining_to_consume)
            lot["qty_remaining"] = lot["qty_assembled"] - consume
            remaining_to_consume -= consume

        if on_hand == 0:
            note = note or "zero stock — lots inserted for history"

        print(f"{sku_id:<12} {on_hand:>8} {total_assembled:>10} {synthetic_qty:>10}  {note}")
        for lot in lots:
            to_insert.append({
                "sku_id":        lot["sku_id"],
                "channel_id":    own_wh_id,
                "assembled_at":  lot["assembled_at"],
                "unit_cogs":     lot["unit_cogs"],
                "qty_assembled": lot["qty_assembled"],
                "qty_remaining": lot["qty_remaining"],
            })

    # ── 5. Insert (skip SKUs that already have lots) ───────────────────────────
    if not to_insert:
        print("\nNothing to insert.")
        return

    existing_sku_ids = {
        r["sku_id"]
        for r in db.table("sku_cogs_lots")
                   .select("sku_id")
                   .eq("channel_id", own_wh_id)
                   .execute().data
    }
    fresh   = [r for r in to_insert if r["sku_id"] not in existing_sku_ids]
    skipped = len([r for r in to_insert if r["sku_id"] in existing_sku_ids])

    if skipped:
        print(f"\n{skipped} lot row(s) skipped — those SKUs already have lots in sku_cogs_lots.")

    if fresh:
        db.table("sku_cogs_lots").insert(fresh).execute()
        open_lots = [r for r in fresh if r["qty_remaining"] > 0]
        print(f"\nInserted {len(fresh)} lot row(s) ({len(open_lots)} with remaining stock).")
    else:
        print("\nAll SKUs already have lots — nothing inserted.")

    print("\nVerify with:")
    print("  SELECT sku_id, assembled_at, unit_cogs, qty_assembled, qty_remaining")
    print("  FROM sku_cogs_lots ORDER BY sku_id, assembled_at;")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="dev", choices=["dev", "prod"])
    args = parser.parse_args()
    main(args.env)
