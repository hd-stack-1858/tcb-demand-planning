"""Load Blinkit daily / MTD sales Excel files into the orders table.

Columns are looked up by header name (row 1), not fixed position — Blinkit
has changed the export at least once already (2026-07-23: the 'S.No.' column
was dropped, shifting every other column left by one, which silently broke
a hardcoded-position parser). Column order/count is not something we control.

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

from ingest.utils import resolve_blinkit_sku

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


_REQUIRED_COLS = [
    "Order Id", "Order Date", "Item Id", "Quantity",
    "MRP (Rs)", "Selling Price (Rs)", "Total Gross Bill Amount",
    "Supply State", "Customer City", "Customer State",
]


def _header_index(header_row: tuple) -> dict[str, int]:
    """Map column name -> position from the header row (row 1)."""
    idx = {str(v).strip(): i for i, v in enumerate(header_row) if v is not None}
    missing = [c for c in _REQUIRED_COLS if c not in idx]
    if missing:
        raise RuntimeError(
            f"Blinkit sales report is missing expected column(s): {missing}. "
            f"Header found: {header_row}"
        )
    return idx


def _build_row(raw: tuple, col: dict[str, int], source_file: str) -> dict | None:
    """Build an orders dict from one raw sales-report row. Returns None to skip."""
    order_id_val = raw[col["Order Id"]]
    if order_id_val is None:
        return None

    try:
        order_date = _parse_date(raw[col["Order Date"]])
    except ValueError:
        return None

    item_id = raw[col["Item Id"]]
    if not item_id:
        return None

    sku_id = resolve_blinkit_sku(int(item_id), order_date)
    if sku_id is None:
        return None

    mrp_raw = raw[col["MRP (Rs)"]]
    sp_raw  = raw[col["Selling Price (Rs)"]]
    gv_raw  = raw[col["Total Gross Bill Amount"]]
    qty_raw = raw[col["Quantity"]]

    mrp = float(mrp_raw) if mrp_raw is not None else None
    sp  = float(sp_raw)  if sp_raw  is not None else None
    gv  = float(gv_raw)  if gv_raw  is not None else None
    qty = int(qty_raw)   if qty_raw is not None else 1

    discount_pct = None
    if mrp and sp and mrp > 0:
        discount_pct = round((mrp - sp) / mrp * 100, 2)

    supply_state = raw[col["Supply State"]]

    return {
        "order_id":          f"BLK-{order_id_val}-{sku_id}",
        "channel_id":        BLK_CHANNEL_ID,
        "order_date":        order_date.isoformat(),
        "sku_id":            sku_id,
        "quantity":          qty,
        "mrp":               mrp,
        "selling_price":     sp,
        "gross_value":       gv,
        "discount_pct":      discount_pct,
        "supply_state":      str(supply_state).strip() if supply_state else None,
        "city":              raw[col["Customer City"]],
        "state":             raw[col["Customer State"]],
        "fulfillment_type":  "SOR",
        "status":            "FULFILLED",
        "platform_order_id": str(order_id_val),
        "source_file":       source_file,
    }


def load_file(filepath: Path, db, dry_run: bool = False) -> tuple[int, int]:
    """Load one sales Excel file. Returns (upserted, skipped).

    Uses ignore_duplicates=False so any field changes on re-load propagate.
    lot_cogs_finalized is not in the Blinkit row dict and is therefore not
    touched by the upsert.

    Loaded with read_only=False: a read-only load trusts the file's <dimension>
    tag to bound row/column iteration, and a Blinkit export on 2026-07-23
    ("sales_summary.xlsx") had a corrupted dimension tag (declared 1x1) despite
    holding 233 real rows — read-only mode silently returned 0 rows with no
    error. Full parsing reads actual row/cell data regardless of that tag.
    """
    wb = openpyxl.load_workbook(str(filepath), data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(min_row=1, values_only=True)
    header = next(rows_iter, None)
    if header is None:
        wb.close()
        return 0, 0
    col = _header_index(header)

    to_upsert: list[dict] = []
    skipped = 0
    total_rows = 0

    for raw in rows_iter:
        total_rows += 1
        row = _build_row(raw, col, filepath.name)
        if row is None:
            skipped += 1
        else:
            to_upsert.append(row)

    wb.close()

    if total_rows > 0 and not to_upsert:
        raise RuntimeError(
            f"{filepath.name}: all {total_rows} row(s) were skipped by the parser — "
            f"the file's format likely doesn't match what this loader expects "
            f"(wrong report downloaded, columns reordered, etc). Refusing to silently "
            f"report 0 sales."
        )

    if dry_run or not to_upsert:
        return len(to_upsert), skipped

    upserted = 0
    for i in range(0, len(to_upsert), _UPSERT_BATCH):
        result = (
            db.table("orders")
            .upsert(to_upsert[i : i + _UPSERT_BATCH],
                    on_conflict="order_id,channel_id",
                    ignore_duplicates=False)
            .execute()
        )
        upserted += len(result.data) if result.data else 0

    return upserted, skipped


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
