"""Enrich return_reason, return_responsible, return_customer_verbatim for Amazon orders.

Reads directly from the Amazon Returns Google Sheet (Tab: Amazon).
Sheet: https://docs.google.com/spreadsheets/d/1_rwqWJJt0aOuLwJnxNyKlCYy21C8RO0rNXI4U1MYKYc

Run monthly after the payout loader to enrich return reason data.

Date window: rolling 3 full calendar months prior to the current month.
  e.g. run on 4-Jun-2026 -> window = 1-Mar-2026 to 31-May-2026.

The sheet is the master list of ALL returned/replaced orders. The 'Order Status' column
distinguishes how each order was resolved:

  'Refunded'  -- customer returned product, Amazon refunded.
                 Original order should be RTO or SALE_RETURN in DB.

  'Replaced'  -- customer got a free replacement, no refund issued.
                 Original order stays FULFILLED in DB (P&L correct; Amazon bears
                 the replacement cost). We still capture Reason/Responsible/Verbatim
                 on the FULFILLED order for quality tracking.

Enrichment (writing the 3 return fields) only runs for rows where
'Status with Amazon' starts with 'Solved':
  Refunded + Solved -> write to the RTO/SALE_RETURN order in DB
  Replaced + Solved -> write to the FULFILLED order in DB

Cross-checks use ALL sheet rows in window (not just Solved):
  A. DB RTO/SALE_RETURN in window NOT in sheet at all
     -> return is tagged in DB but missing from your tracking sheet
  B. Sheet entry whose DB status does not match expectation:
       Refunded  -> expects RTO/SALE_RETURN in DB
       Replaced  -> expects FULFILLED in DB
                    (REPLACEMENT status also suppressed -- replacement order row)
  C. Sheet entry not found in DB at all

Sheet columns used:
  'Order Date'          -- scope to window
  'Order ID'            -- platform_order_id
  'ASIN'                -- resolved to sku_id (authoritative; SKU col unreliable)
  'Order Status'        -- 'Refunded' vs 'Replaced'
  'Customer Verbatim'   -- return_customer_verbatim
  'Reason'              -- return_reason
  'Responsible'         -- return_responsible
  'Status with Amazon'  -- Solved check for enrichment

Blanks in Verbatim / Reason / Responsible are stored as 'Unknown'.
Safe to re-run -- always overwrites with latest sheet values.

Usage:
  python ingest/enrich_az_return_reasons.py [--env dev|prod] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AZ_CHANNELS = [2, 3]  # FBA, FBM

SHEET_ID  = "1_rwqWJJt0aOuLwJnxNyKlCYy21C8RO0rNXI4U1MYKYc"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&sheet=Amazon"


def _rolling_window() -> tuple[date, date]:
    """Return (window_start, window_end) covering 3 full calendar months before today."""
    today = date.today()
    first_current = today.replace(day=1)
    last_prev = first_current - timedelta(days=1)  # last day of prev month
    m = first_current
    for _ in range(3):
        m = (m - timedelta(days=1)).replace(day=1)
    return m, last_prev


def _clean(val) -> str:
    s = str(val).strip() if val else ""
    return s if s else "Unknown"


def _parse_order_date(val: str | None) -> date | None:
    if not val or not str(val).strip():
        return None
    s = str(val).strip()
    for fmt in ("%d-%b %Y", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d",
                "%d-%m-%Y", "%d %B %Y", "%d-%b-%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    logger.warning("Cannot parse order date: %r — row skipped", s)
    return None


def _fetch_sheet_rows() -> list[dict]:
    logger.info("Fetching sheet from Google Sheets...")
    resp = requests.get(SHEET_URL, allow_redirects=True, timeout=30)
    resp.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    logger.info("Sheet rows fetched: %d", len(rows))
    return rows


def _load_asin_map(db) -> dict[str, str]:
    rows = (db.table("sku_channel_ids")
              .select("platform_pid, sku_id")
              .eq("channel_code", "AZ")
              .execute().data)
    return {r["platform_pid"]: r["sku_id"] for r in rows if r.get("platform_pid")}


def _parse_entries(
    rows: list[dict], window_start: date, window_end: date
) -> tuple[list[dict], list[dict], int]:
    """Parse sheet rows into all_entries and solved_entries within the window.

    Returns (all_entries, solved_entries, total_in_sheet).
    all_entries    -- every row with Order ID + ASIN + Order Date in window (any status)
    solved_entries -- subset of all_entries where Status with Amazon starts with 'Solved'
    total_in_sheet -- all non-blank rows in sheet regardless of date
    """
    total_in_sheet = 0
    all_entries: list[dict] = []
    solved_entries: list[dict] = []

    for row in rows:
        order_id = (row.get("Order ID") or "").strip()
        asin_raw = (row.get("ASIN") or "").strip()
        if not order_id or not asin_raw:
            continue

        total_in_sheet += 1
        az_status    = (row.get("Status with Amazon") or "").strip()
        order_status = (row.get("Order Status") or "").strip()
        is_solved    = az_status.startswith("Solved")
        is_replaced  = order_status.lower() == "replaced"

        order_date = _parse_order_date(row.get("Order Date"))
        if order_date is None or not (window_start <= order_date <= window_end):
            continue

        entry = {
            "order_id":     order_id,
            "order_date":   order_date,
            "asins":        [a.strip() for a in asin_raw.split(",") if a.strip()],
            "verbatim":     _clean(row.get("Customer Verbatim")),
            "reason":       _clean(row.get("Reason")),
            "responsible":  _clean(row.get("Responsible")),
            "az_status":    az_status,
            "order_status": order_status,
            "is_replaced":  is_replaced,
        }
        all_entries.append(entry)
        if is_solved:
            solved_entries.append(entry)

    return all_entries, solved_entries, total_in_sheet


def run(dry_run: bool = False) -> None:
    from tcb.db import get_client
    db = get_client()

    window_start, window_end = _rolling_window()
    logger.info("Window: %s to %s", window_start, window_end)

    asin_map = _load_asin_map(db)
    logger.info("ASIN map: %d entries", len(asin_map))

    sheet_rows = _fetch_sheet_rows()
    all_entries, solved_entries, total_in_sheet = _parse_entries(
        sheet_rows, window_start, window_end
    )
    logger.info(
        "Sheet: %d total rows | %d in window | %d Solved in window",
        total_in_sheet, len(all_entries), len(solved_entries),
    )

    # Query DB: all AZ RTO/SALE_RETURN in window
    db_returns: list[dict] = []
    for ch in AZ_CHANNELS:
        rows = (db.table("orders")
                  .select("order_id, platform_order_id, sku_id, status, channel_id")
                  .eq("channel_id", ch)
                  .in_("status", ["RTO", "SALE_RETURN"])
                  .gte("order_date", str(window_start))
                  .lte("order_date", str(window_end))
                  .execute().data)
        db_returns.extend(rows)

    db_return_keys = {(r["platform_order_id"], r["sku_id"]): r for r in db_returns}
    logger.info("DB: %d RTO/SALE_RETURN orders in window", len(db_return_keys))

    # ── Enrichment (Solved entries only) ──────────────────────────────────────
    enriched = 0
    asin_unknown = 0

    for entry in solved_entries:
        oid = entry["order_id"]
        for asin in entry["asins"]:
            sku_id = asin_map.get(asin)
            if sku_id is None:
                logger.warning("Unknown ASIN %s — order %s skipped", asin, oid)
                asin_unknown += 1
                continue

            payload = {
                "return_reason":           entry["reason"],
                "return_responsible":      entry["responsible"],
                "return_customer_verbatim": entry["verbatim"],
            }

            if entry["is_replaced"]:
                # Replaced: enrich the FULFILLED original order
                db_rows = (db.table("orders")
                             .select("order_id, channel_id, status")
                             .eq("platform_order_id", oid)
                             .eq("sku_id", sku_id)
                             .in_("channel_id", AZ_CHANNELS)
                             .eq("status", "FULFILLED")
                             .execute().data)
                if not db_rows:
                    continue  # cross-checks will surface this
                for db_row in db_rows:
                    if dry_run:
                        logger.info(
                            "[DRY-RUN REPLACED] %s / %s -> reason=%s responsible=%s verbatim=%.50s",
                            oid, sku_id, entry["reason"], entry["responsible"], entry["verbatim"],
                        )
                    else:
                        db.table("orders").update(payload).eq(
                            "order_id", db_row["order_id"]
                        ).eq("channel_id", db_row["channel_id"]).execute()
                        logger.info(
                            "Enriched [REPLACED] %s / %s -> reason=%s responsible=%s",
                            oid, sku_id, entry["reason"], entry["responsible"],
                        )
                    enriched += 1
            else:
                # Refunded: enrich the RTO/SALE_RETURN order
                db_row = db_return_keys.get((oid, sku_id))
                if not db_row:
                    continue  # cross-checks will surface this
                if dry_run:
                    logger.info(
                        "[DRY-RUN] %s / %s -> reason=%s responsible=%s verbatim=%.50s",
                        oid, sku_id, entry["reason"], entry["responsible"], entry["verbatim"],
                    )
                else:
                    db.table("orders").update(payload).eq(
                        "order_id", db_row["order_id"]
                    ).eq("channel_id", db_row["channel_id"]).execute()
                    logger.info(
                        "Enriched %s / %s -> reason=%s responsible=%s",
                        oid, sku_id, entry["reason"], entry["responsible"],
                    )
                enriched += 1

    # ── Cross-checks (all entries in window) ──────────────────────────────────
    sheet_keys: set[tuple[str, str]] = set()
    status_mismatch_list: list[tuple] = []   # (order_id, sku_id, db_status, az_status, order_status)
    not_in_db_list: list[tuple] = []         # (order_id, asin, az_status, order_status)

    for entry in all_entries:
        oid = entry["order_id"]
        for asin in entry["asins"]:
            sku_id = asin_map.get(asin)
            if sku_id is None:
                continue  # already warned

            sheet_keys.add((oid, sku_id))

            # Check what DB actually has for this order
            any_db = (db.table("orders")
                        .select("status")
                        .eq("platform_order_id", oid)
                        .eq("sku_id", sku_id)
                        .in_("channel_id", AZ_CHANNELS)
                        .execute().data)

            if not any_db:
                not_in_db_list.append((oid, asin, entry["az_status"], entry["order_status"]))
                continue

            actual_status = any_db[0]["status"]

            if entry["is_replaced"]:
                # Expect FULFILLED or REPLACEMENT (evolving) — both are OK
                if actual_status not in ("FULFILLED", "REPLACEMENT"):
                    status_mismatch_list.append(
                        (oid, sku_id, actual_status, entry["az_status"], entry["order_status"])
                    )
            else:
                # Expect RTO or SALE_RETURN
                if actual_status not in ("RTO", "SALE_RETURN"):
                    status_mismatch_list.append(
                        (oid, sku_id, actual_status, entry["az_status"], entry["order_status"])
                    )

    # [A] DB returns in window not in sheet at all
    no_in_sheet_list = [
        (r["platform_order_id"], r["sku_id"], r["status"])
        for (pid, sku), r in db_return_keys.items()
        if (pid, sku) not in sheet_keys
    ]

    # ── Print cross-check results ─────────────────────────────────────────────
    if no_in_sheet_list:
        logger.warning(
            "\n[A] %d order(s) are RTO/SALE_RETURN in DB (%s to %s) but NOT in your sheet:",
            len(no_in_sheet_list), window_start, window_end,
        )
        for oid, sku, status in sorted(no_in_sheet_list):
            logger.warning("    %s / %s  (%s)", oid, sku, status)

    if status_mismatch_list:
        logger.warning(
            "\n[B] %d order(s) are in your sheet but DB status does not match expectation:",
            len(status_mismatch_list),
        )
        for oid, sku, db_status, az_status, order_status in sorted(status_mismatch_list):
            expected = "FULFILLED" if order_status.lower() == "replaced" else "RTO/SALE_RETURN"
            logger.warning(
                "    %s / %s  (expected=%s  DB=%s  sheet-az-status=%r)",
                oid, sku, expected, db_status, az_status,
            )

    if not_in_db_list:
        logger.warning(
            "\n[C] %d order(s) are in your sheet but not found in DB at all:",
            len(not_in_db_list),
        )
        for oid, asin, az_status, order_status in sorted(not_in_db_list):
            logger.warning(
                "    %s  (ASIN=%s  order-status=%r  az-status=%r)",
                oid, asin, order_status, az_status,
            )

    # ── Summary ───────────────────────────────────────────────────────────────
    tag = "  [DRY-RUN -- nothing written]" if dry_run else ""
    print(
        f"\nWindow: {window_start} to {window_end}{tag}\n"
        f"  Enriched               : {enriched}  "
        f"(Refunded: RTO/SALE_RETURN enriched | Replaced: FULFILLED enriched)\n"
        f"  Unknown ASIN           : {asin_unknown}\n"
        f"  [A] Not in sheet       : {len(no_in_sheet_list)}  "
        f"(RTO/SALE_RETURN in DB, missing from your sheet)\n"
        f"  [B] Status mismatch    : {len(status_mismatch_list)}  "
        f"(In sheet, DB status does not match expected)\n"
        f"  [C] Not in DB          : {len(not_in_db_list)}  "
        f"(In sheet, order not found in DB at all)\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich Amazon return reason/responsible/verbatim from Google Sheet"
    )
    parser.add_argument("--env",     choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("TCB_ENV", args.env)
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
