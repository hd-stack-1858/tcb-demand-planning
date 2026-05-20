"""Populate return_reason, return_responsible, return_customer_verbatim for First Cry orders
from the 'First Cry SR & RTO' tab of the reconciliation Google Sheet.

Sheet columns used:
  A = Order No (platform_order_id)
  G = SKU (our internal sku_id — direct match, no ASIN translation needed)
  H = Customer Verbatim
  I = Reason
  J = Responsible

Blanks in H/I/J are stored as 'Unknown'. Safe to re-run to refresh Unknowns.

Usage:
  python setup/_populate_fc_return_reasons.py [--env dev|prod] [--dry-run]
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
GID       = "438667527"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

FC_CHANNEL_ID = 6


def _fetch_sheet_csv() -> list[dict]:
    resp = requests.get(SHEET_URL, allow_redirects=True, timeout=30)
    resp.raise_for_status()
    return list(csv.DictReader(io.StringIO(resp.text)))


def _clean(val: str | None) -> str:
    s = (val or "").strip()
    return s if s else "Unknown"


def run(dry_run: bool = False) -> None:
    from tcb.db import get_client
    db = get_client()

    logger.info("Fetching sheet…")
    rows = _fetch_sheet_csv()
    logger.info("Sheet rows: %d", len(rows))

    updated = 0
    no_match = 0
    skipped = 0

    for row in rows:
        platform_order_id = row.get("Order No", "").strip()
        sku_id            = row.get("SKU", "").strip()

        if not platform_order_id or not sku_id:
            skipped += 1
            continue

        reason      = _clean(row.get("Reason"))
        responsible = _clean(row.get("Responsible"))
        verbatim    = _clean(row.get("Customer Verbatim"))

        r = (
            db.table("orders")
            .select("order_id, channel_id, status")
            .eq("platform_order_id", platform_order_id)
            .eq("sku_id", sku_id)
            .eq("channel_id", FC_CHANNEL_ID)
            .execute()
        )
        if not r.data:
            logger.warning("NO MATCH — order=%s sku=%s", platform_order_id, sku_id)
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
        "Done. updated=%d  no_match=%d  skipped=%d%s",
        updated, no_match, skipped,
        "  [DRY-RUN — nothing written]" if dry_run else "",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    os.environ["TCB_ENV"] = args.env
    run(dry_run=args.dry_run)
