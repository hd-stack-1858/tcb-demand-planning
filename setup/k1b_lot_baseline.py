"""
K1b — Blinkit lot baseline diff report.

Compares DB sku_cogs_lots.qty_remaining vs latest SOH Total Sellable per SKU/WH.

Design rules (from approved K1 plan):
  N2  3-day cool-off: exclude lots where assembled_at >= today - 3 days
  N3  Sellable-only: compare against Total Sellable, never Recalled column
  N4  Net scheduled inventory shown separately — may explain gaps for recent shipments

In-transit notes shown for any WH where a shipment was made after SOH timestamp
(2026-06-17 12:03:34 IST) or within the previous 14 days (possibly not yet
fully processed into Blinkit's sellable stock).

Usage:
    python setup/k1b_lot_baseline.py
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta, datetime, timezone, timezone
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("TCB_ENV", "prod")

import openpyxl
from tcb.db import get_client

SOH_FILE   = Path(__file__).parent.parent / "data/blinkit/auto/inventory/SOH/InventoryData_18Jun2026.xlsx"
SOH_TS     = datetime(2026, 6, 18, 12, 2, 43)           # from row 1 of SOH file
COOLOFF_CUTOFF = date.today() - timedelta(days=3)        # exclude lots assembled >= this date
TRANSIT_WINDOW_DAYS = 14                                  # flag shipments within this window


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_wh_num(code: str) -> int | None:
    """BLK_WH_1873 → 1873"""
    try:
        return int(code.split("_")[-1])
    except (ValueError, AttributeError):
        return None


# ── load data ─────────────────────────────────────────────────────────────────

def load_soh(path: Path) -> tuple[str, list[dict]]:
    """Parse SOH Excel. Returns (timestamp_str, list of row dicts).
    Uses Blinkit Item ID (col 0, 10xxxxxx) for SKU matching — maps to
    our sku_channel_ids.platform_pid_additional."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = [r for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]
    wb.close()
    ts_str = str(rows[0][0])  # "This sheet was generated at 2026-06-17 12:03:34"
    # headers at rows[2], data from rows[3:]
    result = []
    for r in rows[3:]:
        item_id   = r[0]   # Blinkit Item ID (10xxxxxx) = platform_pid_additional
        wh_fid    = r[5]   # Warehouse Facility ID (numeric) = suffix of BLK_WH_NNNN
        wh_name   = r[6]
        net_sched = int(r[7]  or 0)   # Net scheduled (incoming at WH, not yet sellable)
        sellable  = int(r[10] or 0)   # Total sellable
        damaged   = int(r[15] or 0)
        lost      = int(r[16] or 0)
        if item_id and wh_fid:
            result.append({
                "item_id":   int(item_id),
                "wh_fid":    int(wh_fid),
                "wh_name":   wh_name,
                "net_sched": net_sched,
                "sellable":  sellable,
                "damaged":   damaged,
                "lost":      lost,
            })
    return ts_str, result


def load_mappings(db) -> tuple[dict, dict, int]:
    """Returns (item_id_to_sku, wh_num_to_loc, blk_id).
    item_id_to_sku: platform_pid_additional (int) -> sku_id.
    Prefer TCB009_1 over TCB009 when both share the same item ID."""
    rows = (db.table("sku_channel_ids")
              .select("sku_id, platform_pid_additional")
              .eq("channel_code", "BLK")
              .execute().data)
    item_id_to_sku: dict[int, str] = {}
    for r in rows:
        try:
            iid = int(r["platform_pid_additional"])
        except (ValueError, TypeError):
            continue
        existing = item_id_to_sku.get(iid)
        # prefer TCB009_1 / TCB009_2 over TCB009 for the same item ID
        if existing is None or r["sku_id"] > existing:
            item_id_to_sku[iid] = r["sku_id"]

    blk_id = next(r["channel_id"] for r in db.table("channels").select("channel_id,code").execute().data if r["code"] == "BLK")
    wh_rows = (db.table("partner_locations")
                 .select("location_id, code, name")
                 .eq("channel_id", blk_id)
                 .eq("location_type", "WH")
                 .execute().data)
    wh_num_to_loc: dict[int, dict] = {}
    for w in wh_rows:
        n = _extract_wh_num(w["code"])
        if n is not None:
            wh_num_to_loc[n] = {"location_id": w["location_id"], "name": w["name"]}

    return item_id_to_sku, wh_num_to_loc, blk_id


def load_db_lots(db, blk_id: int) -> dict[tuple[str, int], int]:
    """(sku_id, location_id) → sum of qty_remaining. WH-type locations only, cool-off applied."""
    # Get WH location_ids so we never include dark-store lots in comparison
    wh_loc_ids = {
        r["location_id"] for r in
        db.table("partner_locations").select("location_id")
          .eq("channel_id", blk_id).eq("location_type", "WH").execute().data
    }
    lots = (db.table("sku_cogs_lots")
              .select("sku_id, partner_location_id, qty_remaining, assembled_at")
              .eq("channel_id", blk_id)
              .gt("qty_remaining", 0)
              .execute().data)
    totals: dict[tuple[str, int], int] = defaultdict(int)
    skipped_cooloff = skipped_ds = skipped_null = 0
    for lot in lots:
        loc_id = lot["partner_location_id"]
        if loc_id is None:
            skipped_null += 1
            continue
        if loc_id not in wh_loc_ids:
            skipped_ds += 1
            continue
        try:
            asm = date.fromisoformat(str(lot["assembled_at"])[:10])
        except (ValueError, TypeError):
            continue
        if asm >= COOLOFF_CUTOFF:
            skipped_cooloff += 1
            continue
        totals[(lot["sku_id"], loc_id)] += int(lot["qty_remaining"])
    print(f"  [cool-off]  Skipped {skipped_cooloff} lot rows (assembled >= {COOLOFF_CUTOFF})")
    if skipped_null:
        print(f"  [null-loc]  Skipped {skipped_null} lot rows (partner_location_id IS NULL)")
    if skipped_ds:
        print(f"  [ds-filter] Skipped {skipped_ds} lot rows at dark-store locations")
    return dict(totals)


def load_bug_a_recalls(db, blk_id: int) -> dict[tuple[str, int], int]:
    """Returns Bug A exposure: recalls logged BEFORE the K1a fix (before 2026-06-18)
    where partner_location_id IS NULL — these are the returns that fell through to the
    OWN_WH fallback without decrementing the Blinkit lot.
    Keyed by (sku_id, known_location_id_if_inferrable) — grouped by sku only for display."""
    own_id = next(r["channel_id"] for r in db.table("channels").select("channel_id,code").execute().data if r["code"] == "OWN_WH")
    # RETURN txns from BLK with partner_location_id IS NULL = Bug A signature
    # (Bug A fix deployed 2026-06-18 — returns before that date and returns without loc_id)
    txns = (db.table("sku_inventory_transactions")
              .select("txn_id, sku_id, quantity, partner_location_id, created_at, notes")
              .eq("type", "RETURN")
              .eq("from_channel_id", blk_id)
              .is_("partner_location_id", "null")
              .lt("created_at", "2026-06-18")
              .execute().data)
    # Group by sku_id (we can't reliably infer which WH the recall came from for the old bug)
    totals: dict[str, int] = defaultdict(int)
    for t in txns:
        totals[t["sku_id"]] += int(t["quantity"])
    return dict(totals)


def load_intransit(db, blk_id: int) -> dict[tuple[str, int], int]:
    """Recent TRANSFER_OUT to Blinkit WHs within TRANSIT_WINDOW_DAYS, grouped by (sku_id, location_id)."""
    own_id = next(r["channel_id"] for r in db.table("channels").select("channel_id,code").execute().data if r["code"] == "OWN_WH")
    cutoff = (date.today() - timedelta(days=TRANSIT_WINDOW_DAYS)).isoformat()
    txns = (db.table("sku_inventory_transactions")
              .select("sku_id, quantity, partner_location_id, created_at")
              .eq("type", "TRANSFER_OUT")
              .eq("from_channel_id", own_id)
              .eq("to_channel_id", blk_id)
              .gte("created_at", cutoff)
              .execute().data)
    totals: dict[tuple[str, int], int] = defaultdict(int)
    for t in txns:
        if t["partner_location_id"]:
            totals[(t["sku_id"], t["partner_location_id"])] += int(t["quantity"])
    return dict(totals)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"K1b Blinkit Lot Baseline Diff")
    print(f"  SOH file  : {SOH_FILE.name}")
    print(f"  Cool-off  : exclude lots assembled >= {COOLOFF_CUTOFF} (today - 3 days)")
    print()

    db = get_client()

    ts_str, soh_rows = load_soh(SOH_FILE)
    print(f"  SOH timestamp: {ts_str}")
    print(f"  SOH rows     : {len(soh_rows)}")

    item_id_to_sku, wh_num_to_loc, blk_id = load_mappings(db)
    db_lots   = load_db_lots(db, blk_id)
    intransit = load_intransit(db, blk_id)
    bug_a     = load_bug_a_recalls(db, blk_id)

    # WH location_id -> name lookup for DB-only rows
    wh_names = {
        r["location_id"]: r["name"] for r in
        db.table("partner_locations").select("location_id,name")
          .eq("channel_id", blk_id).eq("location_type", "WH").execute().data
    }

    # Aggregate SOH by (sku_id, location_id)
    soh_by_key: dict[tuple[str, int], dict] = {}
    skipped_no_sku: set[int] = set()
    skipped_no_wh:  set[tuple] = set()

    for row in soh_rows:
        sku_id = item_id_to_sku.get(row["item_id"])
        if sku_id is None:
            skipped_no_sku.add(row["item_id"])
            continue
        loc = wh_num_to_loc.get(row["wh_fid"])
        if loc is None:
            skipped_no_wh.add((row["wh_fid"], row["wh_name"]))
            continue
        key = (sku_id, loc["location_id"])
        if key not in soh_by_key:
            soh_by_key[key] = {"wh_name": loc["name"], "sellable": 0, "net_sched": 0, "damaged": 0, "lost": 0}
        soh_by_key[key]["sellable"]  += row["sellable"]
        soh_by_key[key]["net_sched"] += row["net_sched"]
        soh_by_key[key]["damaged"]   += row["damaged"]
        soh_by_key[key]["lost"]      += row["lost"]

    if skipped_no_sku:
        print(f"  [SKIP] SOH item IDs with no SKU mapping: {sorted(skipped_no_sku)}")
    if skipped_no_wh:
        print(f"  [SKIP] SOH WH Facility IDs with no location mapping:")
        for fid, fname in sorted(skipped_no_wh):
            print(f"         FacilityID={fid}  Name={fname}")

    all_keys = set(soh_by_key.keys()) | set(db_lots.keys())

    report = []
    for key in sorted(all_keys, key=lambda k: (k[0], k[1])):
        sku_id, loc_id = key
        soh_data    = soh_by_key.get(key, {})
        soh_sell    = soh_data.get("sellable", 0)
        soh_sched   = soh_data.get("net_sched", 0)
        db_qty      = db_lots.get(key, 0)
        transit_qty = intransit.get(key, 0)
        bug_a_qty   = bug_a.get(sku_id, 0)   # Bug A exposure (sku-level, not WH-specific)
        wh_name     = soh_data.get("wh_name") or wh_names.get(loc_id, f"loc_id={loc_id}")

        delta = db_qty - soh_sell

        if delta == 0:
            action = "OK"
        elif delta > 0:
            unexplained = delta - transit_qty - soh_sched
            if unexplained <= 0:
                action = f"OK (transit/incoming explains +{delta})"
            elif abs(unexplained) <= 2:
                action = f"MINOR (+{unexplained} unexplained)"
            else:
                action = f"REVIEW  DB overstated by {unexplained} after adjustments"
        else:
            action = f"REVIEW  DB understated by {abs(delta)}"

        notes = []
        if transit_qty > 0:
            notes.append(f"in-transit (last {TRANSIT_WINDOW_DAYS}d): {transit_qty}")
        if soh_sched > 0:
            notes.append(f"net-scheduled (incoming at WH not yet sellable): {soh_sched}")
        if bug_a_qty > 0:
            notes.append(f"Bug A recall not lot-decremented: {bug_a_qty} (sku-level, may explain drift)")
        if soh_data.get("damaged", 0) > 0 or soh_data.get("lost", 0) > 0:
            notes.append(f"unsellable: {soh_data.get('damaged',0)} dmg + {soh_data.get('lost',0)} lost")

        report.append({
            "SKU":      sku_id,
            "WH":       wh_name,
            "DB lots":  db_qty,
            "SOH sell": soh_sell,
            "Delta":    delta,
            "Transit":  transit_qty,
            "Sched":    soh_sched,
            "BugA":     bug_a_qty,
            "Action":   action,
            "Notes":    " | ".join(notes),
        })

    # Print report
    print()
    print("=" * 130)
    print(f"  {'SKU':<12} {'WH':<30} {'DB lots':>8} {'SOH sell':>9} {'Delta':>7} {'Transit':>8} {'Sched':>7} {'BugA':>6}  Action")
    print("=" * 130)
    for r in report:
        flag = " <<<" if "REVIEW" in r["Action"] else ""
        print(f"  {r['SKU']:<12} {r['WH']:<30} {r['DB lots']:>8} {r['SOH sell']:>9}"
              f" {r['Delta']:>7} {r['Transit']:>8} {r['Sched']:>7} {r['BugA']:>6}  {r['Action']}{flag}")
        if r["Notes"]:
            print(f"  {'':12} {'':30}   note: {r['Notes']}")
    print("=" * 130)

    review_rows = [r for r in report if "REVIEW" in r["Action"]]
    ok_rows     = [r for r in report if not r["Action"].startswith("REVIEW")]
    print()
    print(f"Summary: {len(report)} SKU/WH pairs | {len(ok_rows)} OK/minor | {len(review_rows)} need review")
    if review_rows:
        print()
        print("Rows needing review (for Himanshu sign-off):")
        for r in review_rows:
            print(f"  {r['SKU']} @ {r['WH']}  delta={r['Delta']}  {r['Action']}")


if __name__ == "__main__":
    main()
