"""Load First Cry drop-ship Excel reports into the orders table.

FC report contains all delivered orders (Shipment Status = delivered always).
  Is SR = No  → FULFILLED    (normal delivered order)
  Is SR = Yes → SALE_RETURN  (delivered then returned by customer)

RTO orders (returned to origin before delivery) are NOT in the FC report.
For past data, RTOs must be provided manually. For future, they come via the App.

Matching logic (run once per month):
  For each row in the FC report, look up an existing DB order for channel_id=6 by:
    platform_order_id == OrderID  OR  platform_order_id == Shipping Ref. No.
  Found in DB → UPDATE that row with corrected data from the report
               (corrects manual App-entry errors: date, sku, qty, price, status)
  Not found   → INSERT as new (historical pre-App orders)

Key decisions:
  order_id        = "FC-{OrderID}-{sku_id}" for new inserts
  order_date      = Order Date column (when customer placed the order / sale date)
  selling_price   = sku_pricing.sp at order_date (FC customer selling price)
  transfer_price  = sku_channel_tp (FC channel) at order_date (what FC pays us)
  cogs            = BOM × batch cost at order_date
  lot_cogs_finalized = True — FC dispatches from OWN_WH assembled stock; no
                        SOR-style lot reconciliation needed
  platform_order_id = OrderID (canonical FC order number, not Shipping Ref)

Usage:
  python ingest/load_fc_sales.py --file <path.xlsx>   [--env dev|prod] [--dry-run]
  python ingest/load_fc_sales.py --folder <dir>        [--env dev|prod] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.utils import (
    get_channel_tp_at_date,
    get_sku_cogs_at_date,
    get_sku_mrp_at_date,
    get_sku_sp_at_date,
    resolve_fc_sku,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FC_CHANNEL_ID   = 6
FC_CHANNEL_CODE = "FC"
_UPSERT_BATCH   = 100


def _parse_date(val) -> "date":
    if isinstance(val, str):
        return pd.to_datetime(val).date()
    if hasattr(val, "date"):
        return val.date()
    return pd.Timestamp(val).date()


def _build_row(r: dict, source_file: str) -> dict | None:
    """Build an orders dict from one report row. Returns None to skip."""
    product_id = str(r.get("Product ID", "")).strip()
    sku_id = resolve_fc_sku(product_id)
    if sku_id is None:
        return None

    try:
        order_date = _parse_date(r["Order Date"])
    except Exception:
        logger.warning("Unparseable Order Date in %s — skipped", source_file)
        return None

    order_id_raw  = str(r.get("OrderID", "")).strip()
    shipping_ref  = str(r.get("Shipping Ref. No.", "") or "").strip() or None
    qty           = int(r.get("Order Qty", 1))
    is_sr         = str(r.get("Is SR", "No")).strip().lower() == "yes"
    status        = "SALE_RETURN" if is_sr else "FULFILLED"

    sp    = get_sku_sp_at_date(sku_id, order_date)
    mrp   = get_sku_mrp_at_date(sku_id, order_date)
    tp    = get_channel_tp_at_date(sku_id, FC_CHANNEL_CODE, order_date)
    cogs  = get_sku_cogs_at_date(sku_id, order_date)

    gross_value  = round(sp * qty, 2) if sp is not None else None
    discount_pct = None
    if mrp and mrp > 0 and sp is not None and sp < mrp:
        discount_pct = round((mrp - sp) / mrp * 100, 2)

    return {
        "order_id":           f"FC-{order_id_raw}-{sku_id}",
        "channel_id":         FC_CHANNEL_ID,
        "order_date":         order_date.isoformat(),
        "sku_id":             sku_id,
        "quantity":           qty,
        "mrp":                mrp,
        "selling_price":      sp,
        "gross_value":        gross_value,
        "discount_pct":       discount_pct,
        "cogs":               cogs,
        "transfer_price":     tp,
        "city":               None,
        "state":              None,
        "fulfillment_type":   "DROP_SHIP",
        "status":             status,
        "platform_order_id":  order_id_raw,
        "source_file":        source_file,
        "lot_cogs_finalized": True,
        "_shipping_ref":      shipping_ref,   # match-only, stripped before DB write
    }


def load_file(filepath: Path, db, dry_run: bool = False) -> tuple[int, int, int]:
    """Load one FC Excel report. Returns (new, updated, skipped)."""
    df = pd.read_excel(filepath)
    source_file = filepath.name

    report_rows: list[dict] = []
    skipped = 0
    for _, r in df.iterrows():
        row = _build_row(r.to_dict(), source_file)
        if row is None:
            skipped += 1
        else:
            report_rows.append(row)

    if dry_run or not report_rows:
        return len(report_rows), 0, skipped

    # Fetch all existing FC orders keyed by platform_order_id for fast lookup
    existing_raw = (
        db.table("orders")
        .select("order_id, platform_order_id, lot_cogs_finalized")
        .eq("channel_id", FC_CHANNEL_ID)
        .execute()
        .data
    ) or []
    existing: dict[str, str] = {
        r["platform_order_id"]: r["order_id"]
        for r in existing_raw
        if r.get("platform_order_id")
    }

    to_insert: list[dict] = []
    to_update: list[tuple[str, dict]] = []  # (db_order_id, update_payload)

    for row in report_rows:
        shipping_ref = row.pop("_shipping_ref")
        order_id_raw = row["platform_order_id"]

        db_order_id = existing.get(order_id_raw)
        if db_order_id is None and shipping_ref:
            db_order_id = existing.get(shipping_ref)

        if db_order_id is None:
            to_insert.append(row)
        else:
            # Update everything except order_id, channel_id, lot_cogs_finalized
            # lot_cogs_finalized is preserved from DB (App may have already dispatched)
            payload = {
                k: v for k, v in row.items()
                if k not in ("order_id", "channel_id", "lot_cogs_finalized")
            }
            # Canonicalise platform_order_id to the FC OrderID (not Shipping Ref)
            payload["platform_order_id"] = order_id_raw
            to_update.append((db_order_id, payload))

    new_count = 0
    for i in range(0, len(to_insert), _UPSERT_BATCH):
        res = db.table("orders").upsert(
            to_insert[i : i + _UPSERT_BATCH],
            on_conflict="order_id,channel_id",
            ignore_duplicates=False,
        ).execute()
        new_count += len(res.data) if res.data else 0

    updated_count = 0
    for db_order_id, payload in to_update:
        res = db.table("orders").update(payload).eq("order_id", db_order_id).execute()
        if res.data:
            updated_count += 1

    return new_count, updated_count, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load First Cry drop-ship Excel reports → orders table"
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--file",   help="Single .xlsx file")
    grp.add_argument("--folder", help="Folder of .xlsx files")
    parser.add_argument("--env",     choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("TCB_ENV", args.env)
    from tcb.db import get_client
    db = get_client()

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(Path(args.folder).glob("*.xlsx"))
    if not files:
        logger.error("No .xlsx files found")
        sys.exit(1)

    total_new = total_upd = total_skip = 0
    for f in files:
        new, upd, skip = load_file(f, db, dry_run=args.dry_run)
        tag = " [DRY RUN]" if args.dry_run else ""
        print(f"{f.name}{tag}: {new} new | {upd} updated | {skip} skipped")
        total_new += new
        total_upd += upd
        total_skip += skip

    if len(files) > 1:
        print(f"\nTotal: {total_new} new | {total_upd} updated | {total_skip} skipped")


if __name__ == "__main__":
    main()
