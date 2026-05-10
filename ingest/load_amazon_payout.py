"""Tag Amazon returned orders (RTO / SALE_RETURN) from the payout transactions CSV.

Download from Seller Central → Payments → Transaction View → Download.

How it works:
  1. Group every row in the CSV by Order ID.
  2. Orders that have at least one 'Refund' transaction are returns.
  3. Net total = sum of 'Total (INR)' across ALL transaction rows for that order.
     |net_total| ≤ RTO_THRESHOLD (₹10)  → RTO
       Fulfillment fee was reimbursed; we barely lose anything.
       Typical pattern: Refund + Fulfillment Fee Refund + Order Payment ≈ 0.
     |net_total| > RTO_THRESHOLD         → SALE_RETURN
       Customer received the product then returned it; we absorb fees.
  4. return_date = Date of the first Refund row for that order.
  5. Updates status + return_date on all FULFILLED DB rows for that platform_order_id
     across AZ FBA (channel 2) and AZ FBM (channel 3).

Deferred transactions are processed — the physical return occurred even if
Amazon has not finalised the financial settlement yet.

Return reason enrichment (optional --reasons flag):
  Pass a CSV export of the Amazon returns tracking Google Sheet.
  The sheet URL: https://docs.google.com/spreadsheets/d/1_rwqWJJt0aOuLwJnxNyKlCYy21C8RO0rNXI4U1MYKYc
  Download: curl -sL "<export_url>" -o reasons.csv
  Only rows where 'Status with Amazon' starts with 'Solved' are used.
  'Reason Bucket' (col I) is stored in orders.return_reason.
  Re-running with a newer reasons file will enrich already-tagged orders
  that still have return_reason = NULL.

Usage:
  python ingest/load_amazon_payout.py --file <path.csv> [--env dev|prod] [--dry-run]
  python ingest/load_amazon_payout.py --file <path.csv> --reasons <reasons.csv> [--env dev|prod] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AZ_FBA_CHANNEL_ID = 2
AZ_FBM_CHANNEL_ID = 3
RTO_THRESHOLD = 10.0  # ₹ — |net_total| at or below this is treated as RTO
_AZ_CHANNELS = [AZ_FBA_CHANNEL_ID, AZ_FBM_CHANNEL_ID]


def _flt(val: str) -> float:
    s = val.strip()
    return float(s) if s else 0.0


def _parse_date(val: str) -> date:
    return datetime.strptime(val.strip(), "%d-%m-%Y").date()


def _build_return_map(rows: list[dict]) -> dict[str, tuple[str, date | None]]:
    """Return {amazon_order_id: (status, return_date)} for every order
    that has at least one Refund transaction row."""
    order_net: dict[str, float] = defaultdict(float)
    order_refund_date: dict[str, date | None] = {}

    for row in rows:
        oid = (row.get("Order ID") or "").strip()
        if not oid:
            continue
        order_net[oid] += _flt(row.get("Total (INR)", ""))
        if row.get("Transaction type") == "Refund" and oid not in order_refund_date:
            try:
                order_refund_date[oid] = _parse_date(row.get("Date", ""))
            except ValueError:
                order_refund_date[oid] = None

    result: dict[str, tuple[str, date | None]] = {}
    for oid, return_date in order_refund_date.items():
        net = order_net[oid]
        status = "RTO" if abs(net) <= RTO_THRESHOLD else "SALE_RETURN"
        result[oid] = (status, return_date)
        logger.debug("%s  net=%.2f  → %s", oid, net, status)

    return result


def _load_reasons(reasons_path: Path) -> dict[str, str]:
    """Load return reason buckets from the tracking sheet CSV.

    Only rows where 'Status with Amazon' starts with 'Solved' and
    'Reason Bucket' is non-empty are included.
    Returns {amazon_order_id: reason_bucket}.
    """
    result: dict[str, str] = {}
    with open(reasons_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            oid = (row.get("Order ID") or "").strip()
            if not oid:
                continue
            az_status = (row.get("Status with Amazon") or "").strip()
            if not az_status.startswith("Solved"):
                continue
            bucket = (row.get("Reason Bucket") or "").strip()
            if bucket:
                result[oid] = bucket
    logger.info(
        "Reasons file: %d order(s) with Solved status and a Reason Bucket", len(result)
    )
    return result


def load_payout_file(
    filepath: Path,
    db,
    reasons_map: dict[str, str] | None = None,
    dry_run: bool = False,
) -> tuple[int, int, int, int, int]:
    """Process one payout CSV.

    Returns (rto_marked, sale_return_marked, already_tagged, not_in_db, reasons_enriched).
    """
    with open(filepath, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    return_map = _build_return_map(rows)

    rto_total = sum(1 for s, _ in return_map.values() if s == "RTO")
    sr_total  = sum(1 for s, _ in return_map.values() if s == "SALE_RETURN")
    logger.info(
        "Payout file: %d rows | %d orders with Refund (%d RTO candidates, %d SALE_RETURN candidates)",
        len(rows), len(return_map), rto_total, sr_total,
    )

    rto_marked = sr_marked = already_tagged = not_in_db = reasons_enriched = 0

    for oid, (status, return_date) in return_map.items():
        reason = (reasons_map or {}).get(oid)

        res = (
            db.table("orders")
            .select("order_id,status,return_reason")
            .eq("platform_order_id", oid)
            .in_("channel_id", _AZ_CHANNELS)
            .execute()
        )
        db_rows = res.data

        if not db_rows:
            logger.warning("Order %s has Refund in payout but is not in DB — skipped", oid)
            not_in_db += 1
            continue

        fulfilled     = [r for r in db_rows if r["status"] == "FULFILLED"]
        already_ret   = [r for r in db_rows if r["status"] in ("RTO", "SALE_RETURN")]

        if fulfilled:
            update: dict = {
                "status":      status,
                "return_date": return_date.isoformat() if return_date else None,
            }
            if reason:
                update["return_reason"] = reason

            if dry_run:
                logger.info(
                    "[DRY RUN] %s → %s  return_date=%s  reason=%r  (%d row(s))",
                    oid, status, return_date, reason, len(fulfilled),
                )
            else:
                db.table("orders").update(update).eq(
                    "platform_order_id", oid
                ).in_("channel_id", _AZ_CHANNELS).eq(
                    "status", "FULFILLED"
                ).execute()
                logger.info(
                    "Marked %s → %s  return_date=%s  reason=%r  (%d DB row(s))",
                    oid, status, return_date, reason, len(fulfilled),
                )

            if status == "RTO":
                rto_marked += 1
            else:
                sr_marked += 1

        elif already_ret:
            # Order already tagged — check if we can now fill in return_reason
            needs_reason = reason and any(not r.get("return_reason") for r in already_ret)
            if needs_reason:
                if dry_run:
                    logger.info(
                        "[DRY RUN] Enrich return_reason for %s → %r", oid, reason
                    )
                else:
                    db.table("orders").update({"return_reason": reason}).eq(
                        "platform_order_id", oid
                    ).in_("channel_id", _AZ_CHANNELS).execute()
                    logger.info("Enriched return_reason for %s → %r", oid, reason)
                reasons_enriched += 1
            else:
                logger.info("Order %s already fully tagged — skipped", oid)
                already_tagged += 1

    return rto_marked, sr_marked, already_tagged, not_in_db, reasons_enriched


def _verify(db, return_map: dict[str, tuple[str, date | None]]) -> None:
    """Read back marked orders and confirm status matches expectation."""
    all_ids = list(return_map.keys())
    mismatches = 0

    for i in range(0, len(all_ids), 200):
        batch = all_ids[i : i + 200]
        rows = (
            db.table("orders")
            .select("platform_order_id,status")
            .in_("platform_order_id", batch)
            .in_("channel_id", _AZ_CHANNELS)
            .execute()
            .data
        )
        for row in rows:
            oid    = row["platform_order_id"]
            actual = row["status"]
            exp    = return_map[oid][0]
            if actual not in (exp, "CANCELLED", "PENDING"):
                logger.warning(
                    "VERIFY MISMATCH: order %s — expected %s, got %s", oid, exp, actual
                )
                mismatches += 1

    if mismatches == 0:
        logger.info("Verification passed — all return statuses correct in DB")
    else:
        logger.error("Verification: %d mismatch(es) — review logs above", mismatches)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tag Amazon returned orders (RTO/SALE_RETURN) from payout CSV"
    )
    parser.add_argument("--file",    required=True, help="Amazon payout transactions CSV")
    parser.add_argument("--reasons", help="Returns tracking sheet CSV (optional)")
    parser.add_argument("--env",     choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("TCB_ENV", args.env)

    reasons_map: dict[str, str] | None = None
    if args.reasons:
        reasons_map = _load_reasons(Path(args.reasons))

    from tcb.db import get_client
    db = get_client()

    with open(args.file, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return_map = _build_return_map(rows)

    rto, sr, done, missing, enriched = load_payout_file(
        Path(args.file), db, reasons_map=reasons_map, dry_run=args.dry_run
    )

    tag = " [DRY RUN]" if args.dry_run else ""
    print(
        f"\n{args.file}{tag}\n"
        f"  RTO marked         : {rto}\n"
        f"  SALE_RETURN marked : {sr}\n"
        f"  Reasons enriched   : {enriched}\n"
        f"  Already tagged     : {done}\n"
        f"  Not in DB          : {missing}\n"
    )

    if not args.dry_run:
        _verify(db, return_map)


if __name__ == "__main__":
    main()
