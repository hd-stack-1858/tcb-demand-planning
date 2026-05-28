"""
Audit Amazon lot over-consumption from the 3-day window bug.

Reads prod sku_cogs_lots and all AZ post-pivot FULFILLED orders, runs a
single clean FIFO pass to compute correct qty_remaining, then compares
against current DB state. Also shows which orders have wrong COGS locked in.

Run: python setup/archive/_check_az_lot_damage.py --env prod
"""

from __future__ import annotations
import argparse, os, sys
from pathlib import Path
from datetime import date
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

AZ_LOT_PIVOT = date(2026, 5, 2)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["dev","prod"], default="prod")
    args = parser.parse_args()
    os.environ["TCB_ENV"] = args.env

    from tcb.db import get_client
    db = get_client()

    # --- 1. Fetch all AZ lots (post-pivot, qty_assembled > 0) ---
    ch_rows_pre = db.table("channels").select("code,channel_id").execute().data
    az_ids_pre = [r["channel_id"] for r in ch_rows_pre if r["code"].startswith("AZ")]

    lots_raw = (db.table("sku_cogs_lots")
                  .select("lot_id, sku_id, channel_id, assembled_at, qty_assembled, qty_remaining, unit_cogs")
                  .in_("channel_id", az_ids_pre)
                  .gt("qty_assembled", 0)
                  .order("sku_id")
                  .order("assembled_at")
                  .execute().data)

    print(f"\nAZ lots: {len(lots_raw)} total")
    for lot in lots_raw:
        print(f"  lot_id={lot['lot_id']:4d}  sku={lot['sku_id']:<12s}  "
              f"qty_assembled={lot['qty_assembled']:4d}  "
              f"qty_remaining_current={lot['qty_remaining']:4d}  "
              f"unit_cogs={lot['unit_cogs']}")

    # --- 2. Fetch all post-pivot AZ FULFILLED orders (unique, ordered) ---
    az_ids = az_ids_pre

    orders = (db.table("orders")
                .select("order_id, sku_id, channel_id, order_date, quantity, state, cogs, lot_id, lot_cogs_finalized")
                .in_("channel_id", az_ids)
                .in_("status", ["FULFILLED", "REPLACEMENT"])
                .gte("order_date", AZ_LOT_PIVOT.isoformat())
                .order("order_date")
                .order("order_id")
                .execute().data)

    print(f"\nPost-pivot AZ FULFILLED orders: {len(orders)}")

    # --- 3. Clean FIFO simulation (each order counted once) ---
    # Group lots per sku: sorted by assembled_at (FIFO)
    from collections import OrderedDict
    lots_by_sku: dict[str, list[dict]] = defaultdict(list)
    for lot in lots_raw:
        lots_by_sku[lot["sku_id"]].append(dict(lot))  # mutable copy

    # Sort each sku's lots by assembled_at
    for sku_id in lots_by_sku:
        lots_by_sku[sku_id].sort(key=lambda x: x["assembled_at"])
        # Reset qty_remaining to qty_assembled for simulation
        for lot in lots_by_sku[sku_id]:
            lot["sim_remaining"] = lot["qty_assembled"]

    # Process each order once in date order
    order_results = []
    for order in orders:
        sku_id = order["sku_id"]
        qty = int(order["quantity"])
        sku_lots = lots_by_sku.get(sku_id, [])

        consumed = 0
        lot_id_used = None
        unit_cogs_correct = None

        for lot in sku_lots:
            if lot["sim_remaining"] <= 0:
                continue
            take = min(lot["sim_remaining"], qty - consumed)
            lot["sim_remaining"] -= take
            consumed += take
            if lot_id_used is None:
                lot_id_used = lot["lot_id"]
                unit_cogs_correct = lot["unit_cogs"]
            if consumed >= qty:
                break

        if consumed < qty:
            unit_cogs_correct = None  # fallback needed
            lot_id_used = None

        order_results.append({
            "order_id": order["order_id"],
            "sku_id": sku_id,
            "order_date": order["order_date"],
            "qty": qty,
            "lot_id_correct": lot_id_used,
            "cogs_correct": unit_cogs_correct,
            "cogs_current": order["cogs"],
            "lot_id_current": order["lot_id"],
            "lot_finalized_current": order["lot_cogs_finalized"],
        })

    # --- 4. Compute correct vs current lot qty_remaining ---
    print("\n=== LOT QUANTITY DAMAGE ===")
    print(f"{'lot_id':>7}  {'sku':<14}  {'qty_assembled':>13}  {'sim_remaining':>13}  {'current':>7}  {'delta':>6}")
    damaged_lots = []
    for sku_id, sku_lots in lots_by_sku.items():
        for lot in sku_lots:
            current = lot["qty_remaining"]
            correct = lot["sim_remaining"]
            delta = correct - current
            marker = " <-- FIX NEEDED" if delta != 0 else ""
            print(f"{lot['lot_id']:7d}  {sku_id:<14}  {lot['qty_assembled']:13d}  {correct:13d}  {current:7d}  {delta:+6d}{marker}")
            if delta != 0:
                damaged_lots.append({"lot_id": lot["lot_id"], "sku_id": sku_id,
                                     "correct": correct, "current": current, "delta": delta})

    # --- 5. Orders with wrong COGS locked in ---
    wrong_cogs_orders = []
    for r in order_results:
        if not r["lot_finalized_current"]:
            continue  # not finalized, skip
        # Compare: if correct would have been lot-traced but current is fallback (or different lot)
        # or correct is fallback but current is lot-traced
        cogs_match = (r["cogs_correct"] == r["cogs_current"])
        lot_match = (r["lot_id_correct"] == r["lot_id_current"])
        if not cogs_match or not lot_match:
            wrong_cogs_orders.append(r)

    print(f"\n=== ORDERS WITH POTENTIALLY WRONG COGS (finalized, cogs mismatch) ===")
    print(f"Count: {len(wrong_cogs_orders)}")
    for r in wrong_cogs_orders[:30]:
        print(f"  {r['order_id']:<40s}  sku={r['sku_id']:<12s}  "
              f"cogs_correct={r['cogs_correct']}  cogs_current={r['cogs_current']}  "
              f"lot_correct={r['lot_id_correct']}  lot_current={r['lot_id_current']}")

    # --- 6. Summary ---
    print(f"\n=== SUMMARY ===")
    print(f"Damaged lots needing qty_remaining fix: {len(damaged_lots)}")
    for d in damaged_lots:
        print(f"  lot_id={d['lot_id']} ({d['sku_id']}): {d['current']} → {d['correct']} (delta {d['delta']:+d})")
    print(f"Orders with wrong COGS locked in: {len(wrong_cogs_orders)}")

    # --- 7. Day-by-day breakdown of what happened ---
    print(f"\n=== DAY-BY-DAY ORDER COUNTS (post-pivot, AZ FULFILLED, finalized) ===")
    from collections import Counter
    date_counts = Counter(r["order_date"] for r in order_results if r["lot_finalized_current"])
    for d in sorted(date_counts):
        print(f"  {d}: {date_counts[d]} finalized orders")


if __name__ == "__main__":
    main()
