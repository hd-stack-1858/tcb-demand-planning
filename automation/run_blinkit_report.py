"""
Runs the Blinkit sales scraper, then posts the resulting report to Slack.

This is the shape the real Cloud Run Job entrypoint will take once
daily_runner.py is fully containerized (#35) — for now, a standalone script
proving the full pipeline (scrape -> Slack) from the cloud.

Usage:
    python automation/run_blinkit_report.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from automation.blinkit_scraper import scrape, BlinkitSessionExpired
from automation.slack_sender import send_with_attachments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Download only, skip DB write")
    parser.add_argument("--headed", action="store_true", help="Show browser window (debug)")
    args = parser.parse_args()

    try:
        xlsx_path = scrape(dry_run=args.dry_run, headed=args.headed)
    except BlinkitSessionExpired as exc:
        send_with_attachments(f"*Blinkit report failed — session expired*\n{exc}", attachments=[])
        print(f"SESSION EXPIRED: {exc}")
        return 2
    except Exception as exc:
        send_with_attachments(f"*Blinkit report failed*\n{exc}", attachments=[])
        print(f"ERROR: {exc}")
        return 1

    comment = f"Blinkit MTD sales report — {date.today().isoformat()}"
    send_with_attachments(comment, [xlsx_path])
    print(f"Posted {xlsx_path.name} to Slack.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
