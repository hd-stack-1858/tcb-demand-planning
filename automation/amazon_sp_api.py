"""Amazon SP-API client — automated order and financial data ingestion.

Authentication: LWA (Login with Amazon) refresh-token grant → access_token.
All SP-API requests carry the access_token in the x-amz-access-token header.
No AWS Signature V4 or IAM role required for Private Developer self-authorization.

Flows implemented:
  1. Orders Report  → request → poll → download → temp TSV file
                     → feeds directly into ingest/load_amazon_sales.py
  2. Finances API   → fetch financial events (settlements/payouts) → temp CSV
                     → feeds directly into ingest/load_amazon_payout.py

Required env vars (.env or GitHub Actions secrets):
  SP_API_CLIENT_ID       LWA app client ID
  SP_API_CLIENT_SECRET   LWA app client secret
  SP_API_REFRESH_TOKEN   Self-authorization refresh token (from Developer Console)
  SP_API_MARKETPLACE_ID  Optional — defaults to A21TJRUUN4KGV (Amazon.in)

Usage:
  python automation/amazon_sp_api.py orders   --start 2026-05-01 --end 2026-05-14
  python automation/amazon_sp_api.py finances --start 2026-05-01 --end 2026-05-14
  python automation/amazon_sp_api.py orders   --start 2026-05-01 --end 2026-05-14 --dry-run

NOTE on Finances transformation:
  financial_events_to_csv() maps SP-API FinancialEvents JSON to the Transaction View
  CSV format that load_amazon_payout.py expects. Verify the field mapping against a
  real API response before relying on it in production — SP-API Finances schema:
  https://developer-docs.amazon.com/sp-api/docs/finances-api-reference
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import logging
import os
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

_env_file = ".env.dev" if os.environ.get("TCB_ENV") == "dev" else ".env"
load_dotenv(Path(__file__).parent.parent / _env_file)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

LWA_TOKEN_URL      = "https://api.amazon.com/auth/o2/token"
SP_API_ENDPOINT    = os.environ.get("SP_API_ENDPOINT", "https://sellingpartnerapi-eu.amazon.com")
MARKETPLACE_ID     = os.environ.get("SP_API_MARKETPLACE_ID", "A21TJRUUN4KGV")  # Amazon.in

ORDERS_REPORT_TYPE = "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL"

POLL_INITIAL_WAIT  = 30   # seconds — first poll after report is requested
POLL_MAX_WAIT      = 120  # seconds — cap on exponential backoff
POLL_TIMEOUT       = 600  # seconds — give up after 10 minutes


# ── LWA Token ─────────────────────────────────────────────────────────────────

_token_cache: dict = {}


def _get_access_token() -> str:
    """Exchange LWA refresh token for access token. Cached until 60s before expiry."""
    now = time.time()
    if _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["access_token"]

    resp = requests.post(
        LWA_TOKEN_URL,
        data={
            "grant_type":    "refresh_token",
            "refresh_token": _require_env("SP_API_REFRESH_TOKEN"),
            "client_id":     _require_env("SP_API_CLIENT_ID"),
            "client_secret": _require_env("SP_API_CLIENT_SECRET"),
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    _token_cache["access_token"] = payload["access_token"]
    _token_cache["expires_at"]   = now + payload.get("expires_in", 3600)
    logger.info("LWA token refreshed (expires in %ds)", payload.get("expires_in", 3600))
    return _token_cache["access_token"]


def _require_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise EnvironmentError(f"{key} is not set — add it to .env or CI secrets")
    return val


def _headers() -> dict[str, str]:
    return {
        "x-amz-access-token": _get_access_token(),
        "x-amz-date":         datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "Content-Type":       "application/json",
    }


# ── Reports API — Orders ──────────────────────────────────────────────────────

def request_orders_report(start_date: date, end_date: date) -> str:
    """Request an orders report. Returns reportId."""
    url  = f"{SP_API_ENDPOINT}/reports/2021-06-30/reports"
    body = {
        "reportType":    ORDERS_REPORT_TYPE,
        "marketplaceIds": [MARKETPLACE_ID],
        "dataStartTime":  start_date.strftime("%Y-%m-%dT00:00:00Z"),
        "dataEndTime":    end_date.strftime("%Y-%m-%dT23:59:59Z"),
    }
    resp = requests.post(url, json=body, headers=_headers(), timeout=30)
    resp.raise_for_status()
    report_id = resp.json()["reportId"]
    logger.info("Report requested: %s (%s to %s)", report_id, start_date, end_date)
    return report_id


def poll_report(report_id: str) -> str:
    """Poll until report is DONE. Returns reportDocumentId."""
    url      = f"{SP_API_ENDPOINT}/reports/2021-06-30/reports/{report_id}"
    wait     = POLL_INITIAL_WAIT
    deadline = time.time() + POLL_TIMEOUT

    while time.time() < deadline:
        resp   = requests.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        data   = resp.json()
        status = data.get("processingStatus")
        logger.info("Report %s status: %s", report_id, status)

        if status == "DONE":
            doc_id = data.get("reportDocumentId")
            if not doc_id:
                raise RuntimeError(f"Report {report_id} DONE but no reportDocumentId in response")
            return doc_id

        if status in ("CANCELLED", "FATAL"):
            raise RuntimeError(f"Report {report_id} ended with status={status}")

        logger.info("Waiting %ds...", wait)
        time.sleep(wait)
        wait = min(wait * 2, POLL_MAX_WAIT)

    raise TimeoutError(f"Report {report_id} did not complete within {POLL_TIMEOUT}s")


def download_report(document_id: str) -> bytes:
    """Fetch document URL and download content. Handles GZIP decompression."""
    url  = f"{SP_API_ENDPOINT}/reports/2021-06-30/documents/{document_id}"
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    doc = resp.json()

    download_url = doc["url"]
    compression  = doc.get("compressionAlgorithm")  # "GZIP" or absent

    logger.info("Downloading document %s (compression=%s)...", document_id, compression)
    dl = requests.get(download_url, timeout=120)  # pre-signed S3 URL — no auth header needed
    dl.raise_for_status()

    return gzip.decompress(dl.content) if compression == "GZIP" else dl.content


def fetch_orders_report(start_date: date, end_date: date) -> Path:
    """Request → poll → download → save to temp TSV file.

    Returns Path to temp file. The TSV format matches load_amazon_sales.py exactly
    — pass the path directly to load_file(). Caller should unlink after use.
    """
    report_id   = request_orders_report(start_date, end_date)
    document_id = poll_report(report_id)
    content     = download_report(document_id)

    tmp = tempfile.NamedTemporaryFile(
        suffix=".txt",
        prefix=f"az_orders_{start_date}_{end_date}_",
        delete=False,
    )
    tmp.write(content)
    tmp.close()
    logger.info("Orders report saved: %s (%d bytes)", tmp.name, len(content))
    return Path(tmp.name)


# ── Finances API — Payouts ────────────────────────────────────────────────────

def fetch_financial_events(start_date: date, end_date: date) -> list[dict]:
    """Fetch all FinancialEvents pages for the date range. Handles NextToken pagination."""
    url    = f"{SP_API_ENDPOINT}/finances/v0/financialEvents"
    params: dict = {
        "PostedAfter":       start_date.strftime("%Y-%m-%dT00:00:00Z"),
        "PostedBefore":      end_date.strftime("%Y-%m-%dT23:59:59Z"),
        "MaxResultsPerPage": 100,
    }

    pages: list[dict] = []
    while True:
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json().get("payload", {})
        pages.append(payload.get("FinancialEvents", {}))

        next_token = payload.get("NextToken")
        if not next_token:
            break
        params = {"NextToken": next_token}
        logger.info("Fetching next page of financial events...")

    return pages


def financial_events_to_csv(pages: list[dict]) -> bytes:
    """Transform FinancialEvents API response to Transaction View CSV format.

    Produces columns: Order ID | Transaction type | Date | Total (INR) | Total product charges
    This matches the format load_amazon_payout.py reads from manual Seller Central downloads.

    VERIFY field mapping against a real API response before first production run.
    """
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["Order ID", "Transaction type", "Date", "Total (INR)", "Total product charges"],
    )
    writer.writeheader()

    for page in pages:
        # Shipment events → Order Payment rows
        for evt in page.get("ShipmentEventList", []):
            oid    = evt.get("AmazonOrderId", "")
            posted = _api_date_to_ist(evt.get("PostedDate", ""))
            for item in evt.get("ShipmentItemList", []):
                charges       = _sum_money_list(item.get("ItemChargeList", []))
                fees          = _sum_money_list(item.get("ItemFeeList", []))
                promos        = _sum_money_list(item.get("PromotionList", []))
                net_total     = charges - fees - promos
                product_charge = _find_charge(item.get("ItemChargeList", []), "Principal")
                writer.writerow({
                    "Order ID":              oid,
                    "Transaction type":      "Order Payment",
                    "Date":                  posted,
                    "Total (INR)":           round(net_total, 2),
                    "Total product charges": round(product_charge, 2),
                })

        # Refund events → Refund rows
        for evt in page.get("RefundEventList", []):
            oid    = evt.get("AmazonOrderId", "")
            posted = _api_date_to_ist(evt.get("PostedDate", ""))
            for item in evt.get("ShipmentItemAdjustmentList", []):
                charges       = _sum_money_list(item.get("ItemChargeAdjustmentList", []))
                fees          = _sum_money_list(item.get("ItemFeeAdjustmentList", []))
                net_total     = charges - fees
                product_charge = _find_charge(item.get("ItemChargeAdjustmentList", []), "Principal")
                writer.writerow({
                    "Order ID":              oid,
                    "Transaction type":      "Refund",
                    "Date":                  posted,
                    "Total (INR)":           round(net_total, 2),
                    "Total product charges": round(product_charge, 2),
                })

    return output.getvalue().encode("utf-8")


def _api_date_to_ist(val: str) -> str:
    """Convert SP-API UTC datetime string to DD-MM-YYYY IST (load_amazon_payout.py format)."""
    if not val:
        return ""
    try:
        dt  = datetime.fromisoformat(val.replace("Z", "+00:00"))
        ist = dt + timedelta(hours=5, minutes=30)
        return ist.strftime("%d-%m-%Y")
    except ValueError:
        return val


def _sum_money_list(items: list[dict]) -> float:
    """Sum CurrencyAmount across a list of charge/fee/promo dicts."""
    total = 0.0
    for item in items:
        amt = item.get("ChargeAmount") or item.get("FeeAmount") or item.get("PromotionAmount") or {}
        total += float(amt.get("CurrencyAmount", 0) or 0)
    return total


def _find_charge(charge_list: list[dict], charge_type: str) -> float:
    """Extract CurrencyAmount for a specific ChargeType from a charge list."""
    for c in charge_list:
        if c.get("ChargeType") == charge_type:
            return float((c.get("ChargeAmount") or {}).get("CurrencyAmount", 0) or 0)
    return 0.0


def fetch_payout_csv(start_date: date, end_date: date) -> Path:
    """Fetch financial events → transform → save to temp CSV file.

    Returns Path to temp file. Feed into load_amazon_payout.py. Caller should unlink after use.
    """
    pages   = fetch_financial_events(start_date, end_date)
    content = financial_events_to_csv(pages)

    tmp = tempfile.NamedTemporaryFile(
        suffix=".csv",
        prefix=f"az_payout_{start_date}_{end_date}_",
        delete=False,
    )
    tmp.write(content)
    tmp.close()
    logger.info("Payout CSV saved: %s (%d bytes)", tmp.name, len(content))
    return Path(tmp.name)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _default_window() -> tuple[date, date]:
    """Default fetch window: last 10 days (today-9 to today).

    10 days covers: Pending→Shipped transitions, late cancellations, and any
    orders whose status may have changed since last run. Safe to re-run
    because the upsert uses ignore_duplicates=False — status changes propagate,
    no duplicate rows are created.
    """
    today = date.today()
    return today - timedelta(days=9), today


def _run_orders(args) -> None:
    start = date.fromisoformat(args.start) if args.start else _default_window()[0]
    end   = date.fromisoformat(args.end)   if args.end   else _default_window()[1]
    logger.info("Fetching orders %s to %s", start, end)
    tsv   = fetch_orders_report(start, end)

    if args.dry_run:
        logger.info("[DRY RUN] Report at %s — skipping DB load", tsv)
        return

    sys.path.insert(0, str(Path(__file__).parent.parent))
    os.environ.setdefault("TCB_ENV", args.env)
    from tcb.db import get_client
    from ingest.load_amazon_sales import load_file
    upserted, skipped = load_file(tsv, get_client())
    print(f"Orders: {upserted} upserted | {skipped} skipped")
    tsv.unlink(missing_ok=True)


def _run_finances(args) -> None:
    start = date.fromisoformat(args.start) if args.start else _default_window()[0]
    end   = date.fromisoformat(args.end)   if args.end   else _default_window()[1]
    logger.info("Fetching finances %s to %s", start, end)
    csv_path = fetch_payout_csv(start, end)

    if args.dry_run:
        logger.info("[DRY RUN] Payout CSV at %s — skipping DB load", csv_path)
        return

    sys.path.insert(0, str(Path(__file__).parent.parent))
    os.environ.setdefault("TCB_ENV", args.env)
    from tcb.db import get_client
    from ingest.load_amazon_payout import load_payout_file
    rto, sr, done, missing, enriched, replaced = load_payout_file(csv_path, get_client())
    print(
        f"Payouts: {rto} RTO | {sr} SALE_RETURN | {replaced} REPLACEMENT"
        f" | {enriched} reasons enriched | {done} already tagged | {missing} not in DB"
    )
    csv_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Amazon SP-API data ingestion")
    parser.add_argument("command", choices=["orders", "finances"])
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD (default: today-9)")
    parser.add_argument("--end",   default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--env",     choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.command == "orders":
        _run_orders(args)
    else:
        _run_finances(args)


if __name__ == "__main__":
    main()
