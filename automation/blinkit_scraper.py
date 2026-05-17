"""
Blinkit daily sales scraper — downloads MTD sales report and ingests into DB.

Run daily at 12:00 noon IST (after blinkit_auth.py has been run once):
    python automation/blinkit_scraper.py

Navigation flow (from seller portal):
  1. seller.blinkit.com → load saved session
  2. Left sidebar → click "Performance" icon (bar chart, 2nd icon)
  3. Period dropdown — leave at default "Last 7 days" (no click needed)
  4. Click "Reports" button (top-right, has download icon)
  5. File downloads to blinkit_reports/sales/
  6. Ingest via ingest/load_blinkit_sales.py

Why "Last 7 days" not "Current Month":
  - One fewer click (default, no interaction needed)
  - Status changes after 7 days are extremely rare in quick commerce
  - Handles month-end correctly: on Jun 1, "Last 7 days" still includes May 31

If session expires, daily_runner.py catches BlinkitSessionExpired and sends
a WhatsApp alert to Himanshu asking him to run blinkit_auth.py.

Required env vars:
  BLINKIT_USERNAME   Phone number (for logging only — auth uses saved session)
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PORTAL_URL    = "https://seller.blinkit.com"
SESSION_FILE  = Path(__file__).parent.parent / ".blinkit_session" / "state.json"
DOWNLOAD_DIR  = Path(__file__).parent.parent / "blinkit_reports" / "sales"


class BlinkitSessionExpired(Exception):
    """Raised when the saved session has expired and re-auth is needed."""
    pass


def _is_login_page(page) -> bool:
    """True if the page is the Blinkit landing/login page (session expired or not logged in).

    Only checks for the actual login CTA — not the URL — because the dashboard
    can legitimately sit at the root URL after the SPA finishes loading.
    """
    try:
        # "Sell on Blinkit" button is only present when NOT logged in
        btn = page.get_by_role("button", name="Sell on Blinkit")
        if btn.count() and btn.first.is_visible():
            return True
        # Also catch plain text link variant
        link = page.get_by_text("Sell on Blinkit", exact=True)
        return link.count() > 0 and link.first.is_visible()
    except Exception:
        return False


def scrape(dry_run: bool = False, headed: bool = False) -> Path:
    """
    Download today's MTD sales report from Blinkit seller portal.

    Returns Path to the downloaded .xlsx file in blinkit_reports/sales/.
    Raises BlinkitSessionExpired if the saved session is no longer valid.
    """
    if not SESSION_FILE.exists():
        raise FileNotFoundError(
            f"No saved session at {SESSION_FILE}.\n"
            "Run: python automation/blinkit_auth.py"
        )

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, slow_mo=100 if headed else 0)
        ctx = browser.new_context(
            storage_state=str(SESSION_FILE),
            accept_downloads=True,
        )
        page = ctx.new_page()

        # ── Step 1: Load portal, check session ───────────────────────────────
        # Use "domcontentloaded" — Blinkit's SPA keeps background requests alive
        # indefinitely, so "networkidle" never fires reliably.
        logger.info("Loading Blinkit seller portal...")
        page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(4)   # let SPA finish rendering sidebar

        if _is_login_page(page):
            browser.close()
            raise BlinkitSessionExpired(
                "Blinkit session has expired. Run: python automation/blinkit_auth.py"
            )

        logger.info("Session valid. Current URL: %s", page.url)

        # ── Step 2: Navigate to Performance via sidebar ───────────────────────
        # The portal is an SPA — /performance 404s. Must click the sidebar icon.
        # Wait explicitly for at least one selector rather than checking count() immediately.
        logger.info("Clicking Performance icon in sidebar...")
        perf_clicked = False
        perf_selectors = [
            "[aria-label='Performance']",
            "[title='Performance']",
            "a[href*='performance']",
            "nav a:nth-child(2)",
            "[class*='nav'] a:nth-child(2)",
        ]
        for sel in perf_selectors:
            try:
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=5_000)
                el.click()
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
                time.sleep(2)
                logger.info("Clicked Performance via: %s — URL: %s", sel, page.url)
                perf_clicked = True
                break
            except Exception:
                continue

        if not perf_clicked:
            # Last resort: any visible element whose text is "Performance"
            try:
                el = page.get_by_text("Performance").first
                el.wait_for(state="visible", timeout=20_000)
                el.click()
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
                time.sleep(2)
                perf_clicked = True
                logger.info("Clicked Performance via text. URL: %s", page.url)
            except Exception as exc:
                browser.close()
                raise RuntimeError(
                    "Could not find Performance icon in sidebar. "
                    "Run with --headed to debug visually."
                ) from exc

        # ── Step 3: Period is already "Last 7 days" (portal default — no click needed) ───

        # ── Step 4: Click "Reports" button ────────────────────────────────────
        # Confirmed: <button class="relative flex items-center...">Reports</button>
        logger.info("Clicking Reports button...")
        try:
            reports_btn = page.get_by_role("button", name="Reports")
            reports_btn.wait_for(timeout=15_000)
        except PWTimeout:
            browser.close()
            raise RuntimeError(
                "Could not find the 'Reports' button on the Performance page. "
                "Run with --headed to debug."
            )

        # ── Step 5: Capture the download ─────────────────────────────────────
        logger.info("Waiting for download...")
        today_str = date.today().strftime("%d-%m-%Y")
        expected_name = f"sales-report-7d-{today_str}.xlsx"

        with page.expect_download(timeout=60_000) as dl_info:
            reports_btn.first.click()

        download = dl_info.value
        if download.failure():
            browser.close()
            raise RuntimeError(f"Download failed: {download.failure()}")

        # Save to blinkit_reports/sales/ using the portal's original filename
        final_name = download.suggested_filename or expected_name
        dest = DOWNLOAD_DIR / final_name
        download.save_as(str(dest))
        logger.info("Saved: %s", dest)

        browser.close()

    return dest


def ingest(xlsx_path: Path, dry_run: bool = False) -> tuple[int, int]:
    """Run load_blinkit_sales on the downloaded file. Returns (upserted, skipped)."""
    from tcb.db import get_client
    from ingest.load_blinkit_sales import load_file

    db = get_client()
    upserted, skipped = load_file(xlsx_path, db, dry_run=dry_run)
    logger.info("Ingest: %d upserted | %d skipped", upserted, skipped)
    return upserted, skipped


def run(dry_run: bool = False, headed: bool = False) -> dict:
    """Full pipeline: scrape → ingest → return summary dict."""
    xlsx = scrape(dry_run=dry_run, headed=headed)
    upserted, skipped = ingest(xlsx, dry_run=dry_run)
    return {"upserted": upserted, "skipped": skipped, "file": xlsx.name}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Blinkit daily sales scraper")
    parser.add_argument("--dry-run", action="store_true", help="Download only, skip DB write")
    parser.add_argument("--headed",  action="store_true", help="Show browser window (for debugging)")
    args = parser.parse_args()

    os.environ.setdefault("TCB_ENV", "prod")

    try:
        result = run(dry_run=args.dry_run, headed=args.headed)
        print(f"Blinkit: {result['upserted']} upserted | {result['skipped']} skipped | {result['file']}")
    except BlinkitSessionExpired as e:
        print(f"SESSION EXPIRED: {e}")
        sys.exit(2)   # daily_runner.py checks exit code 2 → sends WhatsApp alert
    except Exception as e:
        logger.exception("Scraper failed")
        print(f"ERROR: {e}")
        sys.exit(1)
