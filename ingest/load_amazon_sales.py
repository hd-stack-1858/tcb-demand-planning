"""Load Amazon sell-out TSV report files into the orders table.

Loads all sales-channel = Amazon.in rows across four order statuses:
  Shipped                    → FULFILLED, channel_id=2 (FBA)
  Shipped - Delivered to Buyer → FULFILLED, channel_id=3 (FBM, own-WH dispatch)
  Cancelled                  → CANCELLED,  channel_id=2 (FBA)
  Pending                    → PENDING,    channel_id=2 (FBA, end-of-month snapshot)

Excluded (sales-channel = Non-Amazon):
  Removal orders — stock Amazon sends back to own WH; handled via App inward.

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
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.utils import (
    resolve_amazon_sku,
    get_sku_cogs_at_date,
    get_sku_mrp_at_date,
    normalise_city,
    normalise_state,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))

AZ_FBA_CHANNEL_ID = 2
AZ_FBM_CHANNEL_ID = 3

# AZ seed lots were created on this date. Orders before it are pre-seed:
# COGS already accounted for in opening inventory, lot_cogs_finalized=TRUE.
AZ_LOT_PIVOT = date(2026, 5, 2)

_STATUS_SHIPPED    = "Shipped"
_STATUS_FBM        = "Shipped - Delivered to Buyer"
_STATUS_FBM_PICKUP = "Shipped - Picked Up"   # FBM via pickup point; treat as FBM
_STATUS_CANCELLED  = "Cancelled"
_STATUS_PENDING    = "Pending"
_LOAD_ORDER_STATUSES = {_STATUS_SHIPPED, _STATUS_FBM, _STATUS_FBM_PICKUP, _STATUS_CANCELLED, _STATUS_PENDING}
_INCLUDE_SALES_CHANNEL = "Amazon.in"
_UPSERT_BATCH = 100


def _parse_date(val: str) -> date:
    """Parse ISO-8601 datetime string from Amazon report to IST date.

    Amazon reports purchase-date in UTC. Convert to IST (+5:30) before
    extracting the date so late-evening UTC orders land on the correct
    Indian calendar date.
    """
    s = val.strip()
    if not s:
        raise ValueError("Empty date")
    return datetime.fromisoformat(s).astimezone(_IST).date()


def _flt(val: str) -> float | None:
    s = val.strip()
    return float(s) if s else None


def _build_row(row: dict, source_file: str) -> dict | None:
    """Build an orders dict from one TSV row. Returns None to skip."""
    # Exclude Non-Amazon channel (removal orders — stock sent back from AZ WH to own WH)
    if row.get("sales-channel", "").strip() != _INCLUDE_SALES_CHANNEL:
        return None

    order_status = row.get("order-status", "").strip()
    if order_status not in _LOAD_ORDER_STATUSES:
        return None

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

    # Cancelled — zero-value placeholder for MIS visibility
    if order_status == _STATUS_CANCELLED:
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

    # Pending — end-of-month snapshot; will become Shipped or Cancelled in next file
    if order_status == _STATUS_PENDING:
        return {
            "order_id":           f"AZ-{amazon_order_id}-{sku_id}",
            "channel_id":         AZ_FBA_CHANNEL_ID,
            "order_date":         order_date.isoformat(),
            "sku_id":             sku_id,
            "quantity":           int(row.get("quantity", "") or 0),
            "mrp":                get_sku_mrp_at_date(sku_id, order_date),
            "selling_price":      _flt(row.get("item-price", "")) or 0.0,
            "gross_value":        0.0,
            "discount_pct":       None,
            "cogs":               None,
            "city":               None,
            "state":              None,
            "fulfillment_type":   "SOR",
            "status":             "PENDING",
            "platform_order_id":  amazon_order_id,
            "source_file":        source_file,
            "lot_cogs_finalized": False,
        }

    # Fulfilled path — both FBA (Shipped) and FBM (Shipped - Delivered to Buyer)
    is_fbm = order_status in {_STATUS_FBM, _STATUS_FBM_PICKUP}
    channel_id = AZ_FBM_CHANNEL_ID if is_fbm else AZ_FBA_CHANNEL_ID
    fulfillment_type = "DROP_SHIP" if is_fbm else "SOR"

    qty_raw = row.get("quantity", "").strip()
    qty = int(qty_raw) if qty_raw else 1
    if qty <= 0:
        return None

    # item-price is the line-item total (all units combined), NOT per-unit.
    # gross_value = item-price as-is; selling_price = per-unit = item-price / qty.
    item_price = _flt(row.get("item-price", ""))
    if item_price is None:
        return None
    # item_price=0.0 is valid — promotional / replacement order; load it

    gross_value  = round(item_price, 2)
    sp           = round(item_price / qty, 2)  # per-unit selling price

    mrp = get_sku_mrp_at_date(sku_id, order_date)

    discount_pct = None
    if mrp and mrp > 0 and sp < mrp:
        discount_pct = round((mrp - sp) / mrp * 100, 2)

    city  = normalise_city(row.get("ship-city", "") or "")
    state = normalise_state(row.get("ship-state", ""))

    pre_pivot = order_date < AZ_LOT_PIVOT
    cogs = get_sku_cogs_at_date(sku_id, order_date) if pre_pivot else None
    lot_cogs_finalized = pre_pivot

    return {
        "order_id":           f"AZ-{amazon_order_id}-{sku_id}",
        "channel_id":         channel_id,
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
        "fulfillment_type":   fulfillment_type,
        "status":             "FULFILLED",
        "platform_order_id":  amazon_order_id,
        "source_file":        source_file,
        "lot_cogs_finalized": lot_cogs_finalized,
    }


def load_file(filepath: Path, db, dry_run: bool = False) -> tuple[int, int]:
    """Load one Amazon sales TSV. Returns (upserted, skipped).

    Uses ignore_duplicates=False so status changes (e.g. PENDING→FULFILLED)
    are applied on re-load.

    Already-finalized orders (lot_cogs_finalized=True) are skipped entirely —
    their cogs, lot_id, and lot_cogs_finalized must never be overwritten.
    The SP-API 10-day rolling window would otherwise silently reset finalized
    COGS on every daily run, replacing accurate lot-traced values with fallback.
    """
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
        return len(to_upsert), skipped

    # Fetch already-finalized order_ids and exclude them from the upsert.
    order_ids = [r["order_id"] for r in to_upsert]
    finalized_ids: set[str] = set()
    for i in range(0, len(order_ids), _UPSERT_BATCH):
        rows = (db.table("orders")
                  .select("order_id")
                  .in_("order_id", order_ids[i:i + _UPSERT_BATCH])
                  .eq("lot_cogs_finalized", True)
                  .execute().data)
        finalized_ids.update(r["order_id"] for r in rows)

    if finalized_ids:
        logger.info("Skipping %d already-finalized orders (COGS locked)", len(finalized_ids))
    to_upsert = [r for r in to_upsert if r["order_id"] not in finalized_ids]
    skipped += len(finalized_ids)

    if not to_upsert:
        return 0, skipped

    upserted = 0
    for i in range(0, len(to_upsert), _UPSERT_BATCH):
        result = (
            db.table("orders")
            .upsert(
                to_upsert[i : i + _UPSERT_BATCH],
                on_conflict="order_id,channel_id",
                ignore_duplicates=False,
            )
            .execute()
        )
        upserted += len(result.data) if result.data else 0

    return upserted, skipped


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

    total_upserted = total_skip = 0
    for f in files:
        upserted, skip = load_file(f, db, dry_run=args.dry_run)
        tag = " [DRY RUN]" if args.dry_run else ""
        print(f"{f.name}{tag}: {upserted} upserted | {skip} skipped")
        total_upserted += upserted
        total_skip += skip

    if len(files) > 1:
        print(f"\nTotal: {total_upserted} upserted | {total_skip} skipped")


if __name__ == "__main__":
    main()
