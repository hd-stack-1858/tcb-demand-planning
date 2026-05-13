"""Populate return_reason, return_responsible, return_customer_verbatim for Amazon orders
from the Az Reco List & Status Google Sheet.

Sheet columns used:
  B = Order ID (platform_order_id)
  D = ASIN — resolved via sku_channel_ids (channel_code='AZ') to sku_id
  H = Customer Verbatim
  I = Reason
  J = Responsible

ASIN is always the authoritative key for Amazon SKU resolution — the sheet's SKU column
(col C) is unreliable (wrong values for TCB001/TCB002, TCB009 vs TCB009_1 variants).

Multi-ASIN rows (comma-separated in col D) are expanded to one DB update per SKU.

Blanks in H/I/J are stored as 'Unknown'. Safe to re-run to refresh Unknowns.

Usage:
  python setup/_populate_az_return_reasons.py [--env dev|prod] [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SHEET_ID  = "1_rwqWJJt0aOuLwJnxNyKlCYy21C8RO0rNXI4U1MYKYc"
GID       = "0"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"


def _fetch_sheet_csv() -> list[dict]:
    resp = requests.get(SHEET_URL, allow_redirects=True, timeout=30)
    resp.raise_for_status()
    return list(csv.DictReader(io.StringIO(resp.text)))


def _load_asin_map(db) -> dict[str, str]:
    """Return {asin: sku_id} from sku_channel_ids for channel_code='AZ'."""
    rows = db.table("sku_channel_ids").select("platform_pid,sku_id").eq("channel_code", "AZ").execute().data
    return {r["platform_pid"]: r["sku_id"] for r in rows}


def _clean(val: str | None) -> str:
    s = (val or "").strip()
    return s if s else "Unknown"


def _parse_asins(raw: str) -> list[str]:
    """Handle single ASIN or comma-separated multi-ASIN."""
    return [s.strip() for s in raw.split(",") if s.strip()]


def run(dry_run: bool = False) -> None:
    from tcb.db import get_client
    db = get_client()

    logger.info("Loading ASIN map from DB…")
    asin_map = _load_asin_map(db)

    logger.info("Fetching sheet…")
    rows = _fetch_sheet_csv()
    logger.info("Sheet rows: %d", len(rows))

    updated = 0
    no_match = 0
    asin_unknown = 0
    skipped = 0

    for row in rows:
        platform_order_id = row.get("Order ID", "").strip()
        asin_raw          = row.get("ASIN", "").strip()

        if not platform_order_id or not asin_raw:
            skipped += 1
            continue

        reason      = _clean(row.get("Reason"))
        responsible = _clean(row.get("Responsible"))
        verbatim    = _clean(row.get("Customer Verbatim"))

        asins = _parse_asins(asin_raw)

        for asin in asins:
            sku_id = asin_map.get(asin)
            if sku_id is None:
                logger.warning("ASIN not in sku_channel_ids — order=%s asin=%s", platform_order_id, asin)
                asin_unknown += 1
                continue

            r = (
                db.table("orders")
                .select("order_id, channel_id, status")
                .eq("platform_order_id", platform_order_id)
                .eq("sku_id", sku_id)
                .execute()
            )
            if not r.data:
                logger.warning("NO MATCH — order=%s asin=%s sku=%s", platform_order_id, asin, sku_id)
                no_match += 1
                continue

            for db_row in r.data:
                payload = {
                    "return_reason":           reason,
                    "return_responsible":       responsible,
                    "return_customer_verbatim": verbatim,
                }
                if dry_run:
                    logger.info("[DRY-RUN] %s / %s → %s", platform_order_id, sku_id, payload)
                else:
                    db.table("orders").update(payload).eq(
                        "order_id", db_row["order_id"]
                    ).eq(
                        "channel_id", db_row["channel_id"]
                    ).execute()
                    logger.info("Updated %s / %s → reason=%s responsible=%s", platform_order_id, sku_id, reason, responsible)
                updated += 1

    logger.info(
        "Done. updated=%d  no_match=%d  asin_unknown=%d  skipped=%d%s",
        updated, no_match, asin_unknown, skipped,
        "  [DRY-RUN — nothing written]" if dry_run else "",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.environ["TCB_ENV"] = args.env
    run(dry_run=args.dry_run)
