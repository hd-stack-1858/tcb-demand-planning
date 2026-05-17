"""
WhatsApp sender via Meta Cloud API — for Vignesh daily briefings.

ONE-TIME SETUP (do this before the first run):
  1. Go to Meta Business Suite → WhatsApp → API Setup
  2. Register a spare phone number as a WhatsApp Business number
     (it cannot be the same as your personal WhatsApp number)
  3. Create a message template named "daily_sales_brief":
       Category: UTILITY
       Language: English
       Body text: {{1}}
       (One parameter slot for the full message text)
  4. Wait ~24 hours for Meta to approve the template
  5. Add to .env:
       META_WA_TOKEN=<your permanent token from Meta Business Suite>
       META_PHONE_NUMBER_ID=<phone number ID from Meta dashboard, NOT the number itself>
       WA_RECIPIENT_HIMANSHU=91XXXXXXXXXX   (country code + 10 digits, no + or spaces)
       WA_RECIPIENT_SHUBHRA=91XXXXXXXXXX

USAGE:
    from automation.whatsapp import send_daily_brief
    send_daily_brief("14-May Thurs  25 units overall:\\n• Amazon: 1TCB005")

API rate limits: Meta free tier allows 1,000 business-initiated conversations/month.
Each daily send to 2 recipients = 2 conversations/day ≈ 60/month — well within limit.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

_API_BASE   = "https://graph.facebook.com/v20.0"
_TEMPLATE   = "daily_sales_brief"   # must match Meta-approved template name
_LANG_CODE  = "en"


def _get_config() -> tuple[str, str, list[str]]:
    """Return (token, phone_number_id, recipient_numbers). Raises if not configured."""
    token    = os.environ.get("META_WA_TOKEN", "").strip()
    phone_id = os.environ.get("META_PHONE_NUMBER_ID", "").strip()
    r1       = os.environ.get("WA_RECIPIENT_HIMANSHU", "").strip()
    r2       = os.environ.get("WA_RECIPIENT_SHUBHRA", "").strip()

    missing = [k for k, v in [
        ("META_WA_TOKEN", token),
        ("META_PHONE_NUMBER_ID", phone_id),
        ("WA_RECIPIENT_HIMANSHU", r1),
    ] if not v]

    if missing:
        raise EnvironmentError(
            f"WhatsApp not configured. Missing in .env: {', '.join(missing)}\n"
            "See automation/whatsapp.py docstring for one-time setup instructions."
        )

    recipients = [r for r in [r1, r2] if r]
    return token, phone_id, recipients


def send_daily_brief(message_text: str, dry_run: bool = False) -> list[dict]:
    """
    Send `message_text` to Himanshu (+ Shubhra if configured) via WhatsApp template.

    The template "daily_sales_brief" must be pre-approved by Meta with a single body
    parameter {{1}} that receives the full message text.

    Returns list of API responses (one per recipient).
    Raises EnvironmentError if .env vars are missing.
    Raises requests.HTTPError if the Meta API call fails.
    """
    token, phone_id, recipients = _get_config()

    # Meta template params cannot contain newlines or more than 4 consecutive spaces
    flat_text = " | ".join(line.strip() for line in message_text.splitlines() if line.strip())

    if dry_run:
        logger.info("[dry-run] Would send WhatsApp to %s:\n%s", recipients, flat_text)
        return [{"dry_run": True, "to": r} for r in recipients]

    url     = f"{_API_BASE}/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    results = []
    for recipient in recipients:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {
                "name": _TEMPLATE,
                "language": {"code": _LANG_CODE},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": flat_text}
                        ],
                    }
                ],
            },
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("WhatsApp send failed for %s: %s — %s", recipient, exc, resp.text)
            raise
        result = resp.json()
        logger.info("WhatsApp sent to %s: message_id=%s | text=%r",
                    recipient, result.get("messages", [{}])[0].get("id"), flat_text[:80])
        results.append(result)

    return results


def _send_hello_world(dry_run: bool = False) -> list[dict]:
    """Send Meta's built-in hello_world template (no params) — for API connectivity testing only."""
    token, phone_id, recipients = _get_config()

    if dry_run:
        logger.info("[dry-run] Would send hello_world to %s", recipients)
        return [{"dry_run": True, "to": r} for r in recipients]

    url     = f"{_API_BASE}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    results = []
    for recipient in recipients:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "template",
            "template": {"name": "hello_world", "language": {"code": "en_US"}},
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        logger.info("hello_world sent to %s: %s", recipient, result)
        results.append(result)
    return results


if __name__ == "__main__":
    # Quick test — sends a test message to all configured recipients
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Test WhatsApp sender")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--hello-world", action="store_true",
                        help="Send built-in hello_world template (for API connectivity test)")
    args = parser.parse_args()

    if args.hello_world:
        try:
            results = _send_hello_world(dry_run=args.dry_run)
            print(f"hello_world sent to {len(results)} recipient(s). API connectivity OK.")
        except Exception as e:
            print(f"ERROR: {e}")
    else:
        test_msg = "15-May Thu  TEST message from Vignesh automation setup."
        try:
            results = send_daily_brief(test_msg, dry_run=args.dry_run)
            print(f"Sent to {len(results)} recipient(s). OK.")
        except EnvironmentError as e:
            print(f"SETUP REQUIRED:\n{e}")
