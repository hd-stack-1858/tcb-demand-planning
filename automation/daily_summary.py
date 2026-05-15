"""
Daily sales summary — queries yesterday's orders and formats the WhatsApp message.

Called by daily_runner.py after ingestion completes.

Message format:
    14-May Thurs  25 units overall:
    • Amazon: 1TCB005, 1TCB006, 1TCB008, 9TCB009
    • Blinkit: 1TCB001, 1TCB002, 2TCB004, 1TCB005, 2TCB009
    • First Cry: 1TCB006

Rules:
  - One line per channel, only channels with orders appear
  - Each entry = {qty}{sku_id} (no space), e.g. 9TCB009
  - Channels sorted by order volume descending
  - Only FULFILLED + DELIVERED orders (not returns/cancelled)
"""

from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

# channel_id (int) → WhatsApp display label
# Amazon FBM (3) is merged under "Amazon" — both are the same brand for reporting
CHANNEL_LABELS: dict[int, str] = {
    2:  "Amazon",
    3:  "Amazon",     # Amazon FBM — merged with Amazon in the briefing
    4:  "Blinkit",
    5:  "FnP",
    6:  "First Cry",
    7:  "Peeko",
    8:  "Ozi",
    9:  "Kiddo",
    10: "D2C",
}

# Statuses that count as a sale (exclude returns, cancellations, RTO)
SALE_STATUSES = {"FULFILLED", "DELIVERED", "SHIPPED"}


def _format_day(d: date) -> str:
    """'14-May Thu' from a date object."""
    return d.strftime("%d-%b %a").lstrip("0")


def build_summary(target_date: date | None = None) -> str:
    """
    Query orders for `target_date` (defaults to yesterday) and return
    the formatted WhatsApp message string.

    Returns an empty string if there were no orders that day.
    """
    from tcb.db import get_client

    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    db = get_client()

    # Fetch all orders for target_date with a sale status
    date_str = target_date.isoformat()  # YYYY-MM-DD
    resp = (
        db.table("orders")
        .select("channel_id, sku_id, quantity, status")
        .gte("order_date", date_str)
        .lt("order_date", (target_date + timedelta(days=1)).isoformat())
        .execute()
    )
    rows = resp.data or []

    if not rows:
        logger.info("No orders found for %s", date_str)
        return ""

    # Aggregate: channel → sku → total qty (sale statuses only)
    from collections import defaultdict

    channel_sku_qty: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_units = 0

    for row in rows:
        if row.get("status", "").upper() not in SALE_STATUSES:
            continue
        ch_id = int(row.get("channel_id") or 0)
        label = CHANNEL_LABELS.get(ch_id)
        if not label:
            continue  # skip internal / unknown channels
        sku = row.get("sku_id", "")
        qty = int(row.get("quantity") or 1)
        channel_sku_qty[label][sku] += qty
        total_units += qty

    if not channel_sku_qty:
        return ""

    # Sort channels by total units descending
    channel_totals = {ch: sum(skus.values()) for ch, skus in channel_sku_qty.items()}
    sorted_channels = sorted(channel_totals, key=lambda c: channel_totals[c], reverse=True)

    # Build the message
    day_label = _format_day(target_date)
    lines = [f"{day_label}  {total_units} units overall:"]

    for ch in sorted_channels:
        label = ch  # already the display label
        skus  = channel_sku_qty[ch]
        # Sort SKUs within each channel by qty descending, then sku_id
        sku_parts = sorted(skus.items(), key=lambda x: (-x[1], x[0]))
        sku_str   = ", ".join(f"{qty}{sku}" for sku, qty in sku_parts)
        lines.append(f"• {label}: {sku_str}")

    return "\n".join(lines)


def send_summary(target_date: date | None = None, dry_run: bool = False) -> str:
    """Build and send the daily WhatsApp summary. Returns the message text."""
    from automation.whatsapp import send_daily_brief

    message = build_summary(target_date)
    if not message:
        logger.info("No sales to report — skipping WhatsApp send.")
        return ""

    logger.info("Sending daily brief:\n%s", message)
    send_daily_brief(message, dry_run=dry_run)
    return message


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Build and send daily sales summary")
    parser.add_argument("--date", help="Date to summarise (YYYY-MM-DD, default: yesterday)")
    parser.add_argument("--dry-run", action="store_true", help="Print message, skip WhatsApp send")
    parser.add_argument("--print-only", action="store_true", help="Print message, do not send")
    args = parser.parse_args()

    target = date.fromisoformat(args.date) if args.date else None
    msg    = build_summary(target)

    if not msg:
        print("No orders found for that date.")
        sys.exit(0)

    print("\n" + msg + "\n")

    if not args.print_only:
        from automation.whatsapp import send_daily_brief
        try:
            send_daily_brief(msg, dry_run=args.dry_run)
            print("WhatsApp sent." if not args.dry_run else "[dry-run] Would have sent.")
        except EnvironmentError as e:
            print(f"WhatsApp not configured:\n{e}")
