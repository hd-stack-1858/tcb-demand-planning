"""Load FnP historical orders and reconcile delivery status.

Two source files (both required for historical load):
  --extracted : FnP_Extracted.xlsx   — one row per order×SKU, with city/state/order-date
  --report    : FnP delivery report  — confirmed-delivered orders only (cda-export *.xls)

Status assignment:
  Order No in delivery report                → FULFILLED
  Order No not in report, Order Month May-26 → FULFILLED  (report not yet available)
  Order No not in report, Dec-25 to Apr-26   → SALE_RETURN

TP validation (logged, not fatal):
  GRAND_TOTAL in delivery report = what FnP pays us (sum of TPs for all SKUs in order).
  Compared against sum of sku_channel_tp (FNP) for each SKU in the same order.
  Any mismatch > ₹1 is flagged.

Reconciliation of App-entered orders:
  Existing DB orders for channel_id=5 matched by platform_order_id.
  If found → UPDATE with corrected data. If not → INSERT as FNP-{OrderNo}-{sku_id}.

Usage:
  python ingest/load_fnp_sales.py \\
      --extracted <FnP_Extracted.xlsx> \\
      --report    <cda-export.xls> \\
      [--env dev|prod] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.utils import (
    get_channel_tp_at_date,
    get_sku_cogs_at_date,
    get_sku_mrp_at_date,
    get_sku_sp_at_date,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FNP_CHANNEL_ID   = 5
FNP_CHANNEL_CODE = "FNP"
_UPSERT_BATCH    = 100
_NO_REPORT_MONTHS = {"May-26"}   # months where delivery report is not yet available


def _parse_date(val) -> "date":
    """Parse DD-MM-YYYY strings or Timestamp objects to date."""
    if pd.isna(val):
        raise ValueError("Empty date")
    if isinstance(val, str):
        return pd.to_datetime(val, dayfirst=True).date()
    if hasattr(val, "date"):
        return val.date()
    return pd.Timestamp(val).date()


def _load_extracted(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    df["Order No"] = df["Order No"].astype(str).str.strip()
    df["SKU"]      = df["SKU"].astype(str).str.strip()
    return df


def _load_delivery_report(path: Path) -> tuple[set[str], dict[str, float]]:
    """Return (delivered_order_nos, {order_no: grand_total})."""
    df = pd.read_excel(path)
    df["ORDER NO"] = df["ORDER NO"].astype(str).str.strip()
    delivered = set(df["ORDER NO"].unique())
    totals    = dict(zip(df["ORDER NO"], df["GRAND_TOTAL"].astype(float)))
    return delivered, totals


def _determine_status(order_no: str, order_month: str, delivered: set[str]) -> str:
    if order_no in delivered:
        return "FULFILLED"
    if order_month in _NO_REPORT_MONTHS:
        return "FULFILLED"
    return "SALE_RETURN"


def _validate_tp(extracted_df: pd.DataFrame, delivered: set[str],
                 delivery_totals: dict[str, float]) -> None:
    """Compare sum of system TPs per delivered order against GRAND_TOTAL. Log mismatches."""
    fulfilled_df = extracted_df[extracted_df["Order No"].isin(delivered)].copy()
    order_tp_sums: dict[str, float] = defaultdict(float)

    for _, row in fulfilled_df.iterrows():
        try:
            order_date = _parse_date(row["Order Date"])
        except Exception:
            continue
        tp = get_channel_tp_at_date(row["SKU"], FNP_CHANNEL_CODE, order_date)
        if tp is None:
            logger.warning("No FNP TP found for %s on %s — skipping TP validation for order %s",
                           row["SKU"], order_date, row["Order No"])
            continue
        order_tp_sums[row["Order No"]] += tp

    mismatches = 0
    for order_no, system_total in order_tp_sums.items():
        report_total = delivery_totals.get(order_no)
        if report_total is None:
            continue
        if abs(system_total - report_total) > 1.0:
            logger.warning("TP MISMATCH order %s: system=%.2f  report=%.2f  diff=%.2f",
                           order_no, system_total, report_total,
                           report_total - system_total)
            mismatches += 1

    if mismatches == 0:
        logger.info("TP validation: all %d delivered orders match GRAND_TOTAL ✓",
                    len(order_tp_sums))
    else:
        logger.warning("TP validation: %d mismatch(es) found", mismatches)


def _build_rows(extracted_df: pd.DataFrame, delivered: set[str],
                source_file: str) -> tuple[list[dict], int]:
    """Build order dicts from FnP_Extracted rows. Returns (rows, skipped)."""
    rows: list[dict] = []
    skipped = 0

    for _, r in extracted_df.iterrows():
        order_no   = str(r["Order No"]).strip()
        sku_id     = str(r["SKU"]).strip()
        order_month = str(r.get("Order Month", "")).strip()

        try:
            order_date = _parse_date(r["Order Date"])
        except Exception:
            logger.warning("Unparseable date for order %s — skipped", order_no)
            skipped += 1
            continue

        city  = str(r.get("City", "") or "").strip().title() or None
        state = str(r.get("State", "") or "").strip().title() or None
        if state == "Nan":
            state = None
        if city == "Nan":
            city = None

        status = _determine_status(order_no, order_month, delivered)

        sp    = get_sku_sp_at_date(sku_id, order_date)
        mrp   = get_sku_mrp_at_date(sku_id, order_date)
        tp    = get_channel_tp_at_date(sku_id, FNP_CHANNEL_CODE, order_date)
        cogs  = get_sku_cogs_at_date(sku_id, order_date)

        gross_value  = round(sp, 2) if sp is not None else None  # qty always 1
        discount_pct = round((mrp - sp) / mrp * 100, 2) if mrp and sp and sp < mrp else None

        rows.append({
            "order_id":           f"FNP-{order_no}-{sku_id}",
            "channel_id":         FNP_CHANNEL_ID,
            "order_date":         order_date.isoformat(),
            "sku_id":             sku_id,
            "quantity":           1,
            "mrp":                mrp,
            "selling_price":      sp,
            "gross_value":        gross_value,
            "discount_pct":       discount_pct,
            "cogs":               cogs,
            "transfer_price":     tp,
            "city":               city,
            "state":              state,
            "fulfillment_type":   "DROP_SHIP",
            "status":             status,
            "platform_order_id":  order_no,
            "source_file":        source_file,
            "lot_cogs_finalized": True,
        })

    return rows, skipped


def _missing_order_row() -> dict:
    """Order 7044576301 — in delivery report but not in FnP_Extracted.
    TCB005, Hyderabad, Telangana; ACCEPTED_DATE 21-Feb-2026 used as order_date."""
    from datetime import date as date_
    sku_id     = "TCB005"
    order_date = date_(2026, 2, 21)
    sp   = get_sku_sp_at_date(sku_id, order_date)
    mrp  = get_sku_mrp_at_date(sku_id, order_date)
    tp   = get_channel_tp_at_date(sku_id, FNP_CHANNEL_CODE, order_date)
    cogs = get_sku_cogs_at_date(sku_id, order_date)
    return {
        "order_id":           "FNP-7044576301-TCB005",
        "channel_id":         FNP_CHANNEL_ID,
        "order_date":         order_date.isoformat(),
        "sku_id":             sku_id,
        "quantity":           1,
        "mrp":                mrp,
        "selling_price":      sp,
        "gross_value":        round(sp, 2) if sp else None,
        "discount_pct":       round((mrp - sp) / mrp * 100, 2) if mrp and sp and sp < mrp else None,
        "cogs":               cogs,
        "transfer_price":     tp,
        "city":               "Hyderabad",
        "state":              "Telangana",
        "fulfillment_type":   "DROP_SHIP",
        "status":             "FULFILLED",
        "platform_order_id":  "7044576301",
        "source_file":        "manual",
        "lot_cogs_finalized": True,
    }


def load_files(extracted_path: Path, report_path: Path,
               db, dry_run: bool = False) -> tuple[int, int, int]:
    """Load FnP historical data. Returns (new, updated, skipped)."""
    extracted_df        = _load_extracted(extracted_path)
    delivered, totals   = _load_delivery_report(report_path)

    # TP validation (log only, never fatal)
    _validate_tp(extracted_df, delivered, totals)

    all_rows, skipped = _build_rows(extracted_df, delivered, extracted_path.name)

    # Add the missing order not in Extracted
    all_rows.append(_missing_order_row())
    logger.info("Added missing order FNP-7044576301-TCB005 (in delivery report, not in Extracted)")

    if dry_run:
        by_status: dict[str, int] = defaultdict(int)
        for r in all_rows:
            by_status[r["status"]] += 1
        print(f"[DRY RUN] Would process {len(all_rows)} rows ({skipped} skipped):")
        for s, cnt in sorted(by_status.items()):
            print(f"  {s}: {cnt}")
        return len(all_rows), 0, skipped

    # Fetch existing FnP orders keyed by (platform_order_id, sku_id).
    # Multi-SKU FnP orders share a platform_order_id — keying by sku_id too
    # ensures each SKU row is matched to the correct DB record.
    existing_raw = (
        db.table("orders")
        .select("order_id, platform_order_id, sku_id, lot_cogs_finalized")
        .eq("channel_id", FNP_CHANNEL_ID)
        .execute()
        .data
    ) or []
    existing: dict[tuple[str, str], str] = {
        (r["platform_order_id"], r["sku_id"]): r["order_id"]
        for r in existing_raw
        if r.get("platform_order_id") and r.get("sku_id")
    }

    to_insert: list[dict] = []
    to_update: list[tuple[str, dict]] = []

    for row in all_rows:
        order_no = row["platform_order_id"]
        sku_id   = row["sku_id"]
        db_order_id = existing.get((order_no, sku_id))

        if db_order_id is None:
            to_insert.append(row)
        else:
            payload = {k: v for k, v in row.items()
                       if k not in ("order_id", "channel_id", "lot_cogs_finalized")}
            payload["platform_order_id"] = order_no
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
    parser = argparse.ArgumentParser(description="Load FnP historical orders → orders table")
    parser.add_argument("--extracted", required=True, help="FnP_Extracted.xlsx path")
    parser.add_argument("--report",    required=True, help="FnP delivery report (cda-export .xls)")
    parser.add_argument("--env",       choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run",   action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("TCB_ENV", args.env)
    from tcb.db import get_client
    db = get_client()

    new, upd, skip = load_files(
        Path(args.extracted), Path(args.report), db, dry_run=args.dry_run
    )
    tag = " [DRY RUN]" if args.dry_run else ""
    print(f"{tag} {new} new | {upd} updated | {skip} skipped")


if __name__ == "__main__":
    main()
