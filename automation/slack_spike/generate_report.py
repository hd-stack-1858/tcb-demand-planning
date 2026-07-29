"""
Stage 1 of the Slack-delivery spike: a synthetic report generator.

Proves the Docker mechanics (build, run, volume mount, file written and
readable from the host) before anything touches Slack or a real scraper.
Deliberately has no dependency on tcb/, automation/, or any real report —
just enough content to later prove a file upload actually carries data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

OUTPUT_DIR = Path("/output")


def generate() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    dest = OUTPUT_DIR / f"synthetic_report_{now.strftime('%Y%m%d_%H%M%S')}.txt"

    dest.write_text(
        "Synthetic Test Report\n"
        f"Generated (UTC): {now.isoformat()}\n"
        "Rows: 42\n"
        "Status: OK\n"
    )
    print(f"Wrote: {dest}")
    return dest


if __name__ == "__main__":
    generate()
