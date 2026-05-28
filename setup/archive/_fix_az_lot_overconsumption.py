"""
Repair: restore Amazon lot qty_remaining over-consumed by the 3-day COGS bug.

Root cause: SP-API 10-day rolling window re-upserted already-finalized orders with
lot_cogs_finalized=False + cogs=None daily. finalize_az_cogs() then re-ran FIFO each
day (May 26, 27, 28), consuming lots multiple times for the same orders.

This script restores the correct qty_remaining for the 4 affected lots.
Existing order COGS values are NOT changed — they already reflect the latest
receipt/assembly cost and are acceptable.

Determined by FIFO simulation in _check_az_lot_damage.py (run 2026-05-28).
Fixed lots:
  lot_id=116  TCB005  qty_remaining: 0 -> 14
  lot_id=60   TCB006  qty_remaining: 0 -> 10
  lot_id=58   TCB008  qty_remaining: 0 -> 8
  lot_id=102  TCB009_2 qty_remaining: 70 -> 81

Run: python setup/archive/_fix_az_lot_overconsumption.py [--env prod] [--dry-run]
"""

from __future__ import annotations
import argparse, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

FIXES = [
    # correct_remaining: from FIFO simulation in _check_az_lot_damage.py
    # correct_unit_cogs: from latest ASSEMBLY txn (None = no change)
    {"lot_id": 116, "sku_id": "TCB005",   "correct_remaining": 14, "correct_unit_cogs": None},
    {"lot_id":  60, "sku_id": "TCB006",   "correct_remaining": 10, "correct_unit_cogs": None},
    {"lot_id":  58, "sku_id": "TCB008",   "correct_remaining":  8, "correct_unit_cogs": 370.81},
    {"lot_id": 102, "sku_id": "TCB009_2", "correct_remaining": 81, "correct_unit_cogs": None},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    os.environ["TCB_ENV"] = args.env
    mode = "[DRY RUN]" if args.dry_run else "[LIVE]"

    from tcb.db import get_client
    db = get_client()

    print(f"\n=== AZ Lot Overconsumption Repair {mode} ===\n")

    for fix in FIXES:
        lot_id          = fix["lot_id"]
        sku_id          = fix["sku_id"]
        correct         = fix["correct_remaining"]

        # Read current state
        row = (db.table("sku_cogs_lots")
                 .select("lot_id, sku_id, qty_assembled, qty_remaining, unit_cogs, assembled_at")
                 .eq("lot_id", lot_id)
                 .single()
                 .execute().data)

        if row is None:
            print(f"  lot_id={lot_id} ({sku_id}): NOT FOUND — skip")
            continue

        current = row["qty_remaining"]
        delta   = correct - current

        print(f"  lot_id={lot_id}  {sku_id:<12s}  "
              f"assembled_at={row['assembled_at']}  unit_cogs={row['unit_cogs']}  "
              f"qty_assembled={row['qty_assembled']}")
        print(f"    qty_remaining: {current} -> {correct}  (delta={delta:+d})")

        if delta == 0:
            print("    No change needed.\n")
            continue

        if correct > row["qty_assembled"]:
            print(f"    ERROR: correct_remaining ({correct}) > qty_assembled ({row['qty_assembled']}) — skip")
            continue

        new_unit_cogs = fix["correct_unit_cogs"]
        if new_unit_cogs is not None:
            print(f"    unit_cogs: {row['unit_cogs']} -> {new_unit_cogs}  (latest assembly cost)")
        else:
            print(f"    unit_cogs: {row['unit_cogs']}  (unchanged)")

        if args.dry_run:
            print("    Would update.\n")
            continue

        update_payload: dict = {"qty_remaining": correct}
        if new_unit_cogs is not None:
            update_payload["unit_cogs"] = new_unit_cogs

        db.table("sku_cogs_lots").update(update_payload).eq("lot_id", lot_id).execute()

        # Read back to verify
        verify = (db.table("sku_cogs_lots")
                    .select("qty_remaining, unit_cogs")
                    .eq("lot_id", lot_id)
                    .single()
                    .execute().data)
        actual_qty   = verify["qty_remaining"]
        actual_cogs  = verify["unit_cogs"]
        qty_ok  = actual_qty == correct
        cogs_ok = (new_unit_cogs is None) or (abs(float(actual_cogs) - new_unit_cogs) < 0.01)

        if qty_ok and cogs_ok:
            print(f"    OK — qty_remaining={actual_qty}, unit_cogs={actual_cogs} confirmed.\n")
        else:
            print(f"    ERROR — qty_remaining={actual_qty} (expected {correct}), "
                  f"unit_cogs={actual_cogs} (expected {new_unit_cogs})\n")

    print("=== Done ===")


if __name__ == "__main__":
    main()
