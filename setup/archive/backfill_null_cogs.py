"""
One-off: backfill cogs=NULL for orders with lot_cogs_finalized=True.

These are pre-pivot orders where get_sku_cogs_at_date() returned None at load
time (no item batch existed before the order date). Uses _get_sku_cogs_fallback()
which looks up the latest ASSEMBLY txn unit_cogs for the SKU.

Current gap (8 orders, all TCB009_1, March 2026):
  AZ FULFILLED x4, AZ RTO x2, AZ SALE_RETURN x1, BLK FULFILLED x1

Usage:
    python setup/archive/backfill_null_cogs.py --dry-run
    python setup/archive/backfill_null_cogs.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from tcb.db import get_client
from tcb.inventory import _get_sku_cogs_fallback


def run(dry_run: bool) -> None:
    db = get_client()

    rows = (db.table("orders")
              .select("order_id, platform_order_id, sku_id, channel_id, order_date, status, quantity")
              .is_("cogs", "null")
              .eq("lot_cogs_finalized", True)
              .execute().data)

    print(f"{'DRY RUN -- ' if dry_run else ''}Orders with lot_cogs_finalized=True and cogs=NULL: {len(rows)}")
    if not rows:
        print("Nothing to do.")
        return

    updated = no_cogs = 0

    for r in rows:
        sku_id = r["sku_id"]
        cogs   = _get_sku_cogs_fallback(sku_id, db)
        print(f"  {r['platform_order_id']}  {sku_id}  {r['order_date']}  "
              f"status={r['status']}  fallback_cogs={cogs}")

        if not dry_run:
            if cogs is not None:
                db.table("orders").update({"cogs": cogs}).eq("order_id", r["order_id"]).execute()
                updated += 1
            else:
                print(f"    WARNING: no fallback COGS found for {sku_id} -- skipped")
                no_cogs += 1

    if dry_run:
        print("\nDry run complete -- no changes written.")
    else:
        print(f"\nUpdated: {updated}  |  No COGS found: {no_cogs}")
        # Verify
        remaining = (db.table("orders")
                       .select("order_id", count="exact")
                       .is_("cogs", "null")
                       .eq("lot_cogs_finalized", True)
                       .execute().count)
        print(f"Remaining lot_cogs_finalized=True + cogs=NULL: {remaining}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
