"""Load Amazon FBA sell-out TSV report files into the orders table.

Filter logic
  sales-channel = Amazon.in  AND  order-status = Shipped  (FBA only)
  Excluded:
    Cancelled              — no shipment, no sale
    Pending                — not yet shipped; will appear in next month's file
    Shipped - Delivered to Buyer — FBM (fulfilled via own WH), already in App

ASIN -> sku_id  via  sku_channel_ids.platform_pid  (channel_code = AZ)
Do NOT use the sku column in the Amazon report — Amazon SKU codes do not match
our internal sku_id values.

Dedup key  : order_id = "AZ-{amazon-order-id}-{sku_id}"  (unique per order×SKU)
platform_order_id = raw amazon-order-id  (stored for reference)

selling_price = item-price  (GST-inclusive, as Amazon reports it)
lot_cogs_finalized:
  TRUE  for orders before AZ_LOT_PIVOT (2026-05-02) — pre-seed, no lots to consume
  FALSE for orders on/after pivot — lot consumption handled as a separate step

Usage:
  python ingest/load_amazon_sales.py --file <path.txt> [--env dev|prod] [--dry-run]
  python ingest/load_amazon_sales.py --folder <dir>    [--env dev|prod] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.utils import (
    resolve_amazon_sku,
    get_sku_cogs_at_date,
    get_sku_mrp_at_date,
    normalise_state,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AZ_FBA_CHANNEL_ID = 2

# AZ seed lots were created on this date. Orders before it are pre-seed:
# COGS already accounted for in opening inventory, lot_cogs_finalized=TRUE.
AZ_LOT_PIVOT = date(2026, 5, 2)

_FULFILLED_STATUS  = "Shipped"
_CANCELLED_STATUS  = "Cancelled"
_LOAD_ORDER_STATUSES = {_FULFILLED_STATUS, _CANCELLED_STATUS}
_INCLUDE_SALES_CHANNEL = "Amazon.in"
_UPSERT_BATCH = 100


def _parse_date(val: str) -> date:
    """Parse ISO-8601 datetime string from Amazon report to date."""
    s = val.strip()
    if not s:
        raise ValueError("Empty date")
    # Format: 2025-11-24T06:34:56+00:00
    return datetime.fromisoformat(s).date()


def _flt(val: str) -> float | None:
    s = val.strip()
    return float(s) if s else None


def _build_row(row: dict, source_file: str) -> dict | None:
    """Build an orders dict from one TSV row. Returns None to skip."""
    # Channel filter
    if row.get("sales-channel", "").strip() != _INCLUDE_SALES_CHANNEL:
        return None

    # Status filter — load Shipped (FBA fulfilled) and Cancelled only.
    # Skip Pending/Shipping (not final) and "Shipped - Delivered to Buyer" (FBM,
    # already captured via App dispatch to avoid double-counting).
    order_status = row.get("order-status", "").strip()
    if order_status not in _LOAD_ORDER_STATUSES:
        return None

    is_cancelled = order_status == _CANCELLED_STATUS

    # ASIN → sku_id
    asin = row.get("asin", "").strip()
    if not asin:
        logger.warning("Row with no ASIN in %s — skipped", source_file)
        return None
    sku_id = resolve_amazon_sku(asin)
    if sku_id is None:
        return None

    # Date
    try:
        order_date = _parse_date(row.get("purchase-date", ""))
    except (ValueError, KeyError):
        logger.warning("Unparseable date in %s — skipped", source_file)
        return None

    amazon_order_id = row.get("amazon-order-id", "").strip()

    if is_cancelled:
        return {
            "order_id":           f"AZ-{amazon_order_id}-{sku_id}",
            "channel_id":         AZ_FBA_CHANNEL_ID,
            "order_date":         order_date.isoformat(),
            "sku_id":             sku_id,
            "quantity":           0,
            "mrp":                get_sku_mrp_at_date(sku_id, order_date),
            "selling_price":      0.0,
            "gross_value":        0.0,
            "discount_pct":       None,
            "cogs":               0.0,
            "city":               None,
            "state":              None,
            "fulfillment_type":   "SOR",
            "status":             "CANCELLED",
            "platform_order_id":  amazon_order_id,
            "source_file":        source_file,
            "lot_cogs_finalized": True,
        }

    # Fulfilled path (Shipped)
    qty_raw = row.get("quantity", "").strip()
    qty = int(qty_raw) if qty_raw else 1
    if qty <= 0:
        return None

    sp = _flt(row.get("item-price", ""))
    if sp is None or sp <= 0:
        return None

    mrp = get_sku_mrp_at_date(sku_id, order_date)
    gross_value = round(sp * qty, 2)

    discount_pct = None
    if mrp and mrp > 0 and sp < mrp:
        discount_pct = round((mrp - sp) / mrp * 100, 2)

    city  = (row.get("ship-city",  "") or "").strip().title() or None
    state = normalise_state(row.get("ship-state", ""))

    pre_pivot = order_date < AZ_LOT_PIVOT
    cogs = get_sku_cogs_at_date(sku_id, order_date) if pre_pivot else None
    lot_cogs_finalized = pre_pivot

    return {
        "order_id":           f"AZ-{amazon_order_id}-{sku_id}",
        "channel_id":         AZ_FBA_CHANNEL_ID,
        "order_date":         order_date.isoformat(),
        "sku_id":             sku_id,
        "quantity":           qty,
        "mrp":                mrp,
        "selling_price":      sp,
        "gross_value":        gross_value,
        "discount_pct":       discount_pct,
        "cogs":               cogs,
        "city":               city,
        "state":              state,
        "fulfillment_type":   "SOR",
        "status":             "FULFILLED",
        "platform_order_id":  amazon_order_id,
        "source_file":        source_file,
        "lot_cogs_finalized": lot_cogs_finalized,
    }


def load_file(filepath: Path, db, dry_run: bool = False) -> tuple[int, int, int]:
    """Load one Amazon sales TSV. Returns (new, duplicate, skipped)."""
    to_upsert: list[dict] = []
    skipped = 0

    with open(filepath, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for raw in reader:
            row = _build_row(raw, filepath.name)
            if row is None:
                skipped += 1
            else:
                to_upsert.append(row)

    if dry_run or not to_upsert:
        return len(to_upsert), 0, skipped

    new_count = 0
    for i in range(0, len(to_upsert), _UPSERT_BATCH):
        result = (
            db.table("orders")
            .upsert(
                to_upsert[i : i + _UPSERT_BATCH],
                on_conflict="order_id,channel_id",
                ignore_duplicates=True,
            )
            .execute()
        )
        new_count += len(result.data) if result.data else 0

    return new_count, len(to_upsert) - new_count, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Amazon FBA sales TSV -> orders table")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--file",   help="Single TSV file")
    grp.add_argument("--folder", help="Folder of TSV files (all *.txt)")
    parser.add_argument("--env",     choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("TCB_ENV", args.env)

    from tcb.db import get_client
    db = get_client()

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(Path(args.folder).glob("*.txt"))
    if not files:
        logger.error("No .txt files found")
        sys.exit(1)

    total_new = total_dup = total_skip = 0
    for f in files:
        new, dup, skip = load_file(f, db, dry_run=args.dry_run)
        tag = " [DRY RUN]" if args.dry_run else ""
        print(f"{f.name}{tag}: {new} new | {dup} duplicate | {skip} skipped")
        total_new += new
        total_dup += dup
        total_skip += skip

    if len(files) > 1:
        print(f"\nTotal: {total_new} new | {total_dup} duplicate | {total_skip} skipped")


if __name__ == "__main__":
    main()
