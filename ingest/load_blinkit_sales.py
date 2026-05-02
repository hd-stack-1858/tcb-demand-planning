"""Load Blinkit daily / MTD sales Excel files into the orders table.

Sales report columns (row 1 header, row 2+ data):
  0  S.No.              10  Supply City        20  CESS(%)
  1  Order Id           11  Supply State       21  Quantity
  2  Order Date         12  Supply State GST   22  MRP (Rs)
  3  Item Id            13  Customer City      23  Selling Price (Rs)
  4  Product Name       14  Customer State     24  IGST Value
  5  Brand Name         15  Order Status       25  CGST Value
  6  UPC                16  HSN Code           26  SGST Value
  7  Variant Desc       17  IGST(%)            27  CESS Value
  8  App Mapping        18  CGST(%)            28  Total Tax
  9  Business Cat       19  SGST(%)            29  Total Gross Bill Amount

Usage:
  python ingest/load_blinkit_sales.py --file <path.xlsx> [--env dev|prod] [--dry-run]
  python ingest/load_blinkit_sales.py --folder <dir>     [--env dev|prod] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.utils import resolve_blinkit_sku, get_sku_cogs_at_date

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BLK_CHANNEL_ID = 4
_UPSERT_BATCH = 100


def _parse_date(val) -> date:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    for fmt in ("%d %B %Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date: {val!r}")


def _build_row(raw: tuple, source_file: str) -> dict | None:
    """Build an orders dict from one raw sales-report row. Returns None to skip."""
    if raw[0] is None:
        return None

    try:
        order_date = _parse_date(raw[2])
    except ValueError:
        return None

    if not raw[3]:
        return None

    sku_id = resolve_blinkit_sku(int(raw[3]), order_date)
    if sku_id is None:
        return None

    mrp = float(raw[22]) if raw[22] is not None else None
    sp  = float(raw[23]) if raw[23] is not None else None
    gv  = float(raw[29]) if raw[29] is not None else None
    qty = int(raw[21])   if raw[21] is not None else 1

    discount_pct = None
    if mrp and sp and mrp > 0:
        discount_pct = round((mrp - sp) / mrp * 100, 2)

    return {
        "order_id":          f"BLK-{raw[1]}-{sku_id}",
        "channel_id":        BLK_CHANNEL_ID,
        "order_date":        order_date.isoformat(),
        "sku_id":            sku_id,
        "quantity":          qty,
        "mrp":               mrp,
        "selling_price":     sp,
        "gross_value":       gv,
        "discount_pct":      discount_pct,
        "cogs":              get_sku_cogs_at_date(sku_id, order_date),
        "city":              raw[13],
        "state":             raw[14],
        "fulfillment_type":  "SOR",
        "status":            "FULFILLED",
        "platform_order_id": str(raw[1]),
        "source_file":       source_file,
    }


def load_file(filepath: Path, db, dry_run: bool = False) -> tuple[int, int, int]:
    """Load one sales Excel file. Returns (new, duplicate, skipped)."""
    wb = openpyxl.load_workbook(str(filepath), read_only=True, data_only=True)
    ws = wb.active

    to_upsert: list[dict] = []
    skipped = 0

    for raw in ws.iter_rows(min_row=2, values_only=True):
        row = _build_row(raw, filepath.name)
        if row is None:
            skipped += 1
        else:
            to_upsert.append(row)

    wb.close()

    if dry_run or not to_upsert:
        return len(to_upsert), 0, skipped

    new_count = 0
    for i in range(0, len(to_upsert), _UPSERT_BATCH):
        result = (
            db.table("orders")
            .upsert(to_upsert[i : i + _UPSERT_BATCH],
                    on_conflict="order_id,channel_id",
                    ignore_duplicates=True)
            .execute()
        )
        new_count += len(result.data) if result.data else 0

    return new_count, len(to_upsert) - new_count, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Blinkit sales Excel → orders table")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--file",   help="Single Excel file")
    grp.add_argument("--folder", help="Folder of Excel files (all *.xlsx)")
    parser.add_argument("--env",     choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("TCB_ENV", args.env)

    from tcb.db import get_client
    db = get_client()

    files = [Path(args.file)] if args.file else sorted(Path(args.folder).glob("*.xlsx"))
    if not files:
        logger.error("No .xlsx files found")
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
