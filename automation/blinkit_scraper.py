"""
Blinkit daily sales scraper — downloads MTD sales report and ingests into DB.

Run daily at 12:00 noon IST (after blinkit_auth.py has been run once):
    python automation/blinkit_scraper.py

Navigation flow (from seller portal):
  1. seller.blinkit.com → load saved session
  2. Left sidebar → click "Performance" icon (bar chart, 2nd icon)
  3. Period dropdown — leave at default "Last 7 days" (no click needed)
  4. Click "Reports" button (top-right, has download icon)
  5. File downloads to data/blinkit/auto/
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
DOWNLOAD_DIR  = Path(__file__).parent.parent / "data" / "blinkit" / "auto"  # scraper writes MTD sales reports here


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
        # Blinkit uses Cloudflare bot detection that blocks Playwright's bundled
        # Chromium in headless mode (hangs the TCP connection indefinitely).
        # Using the user's installed Chrome + stealth args bypasses this because:
        #   1. Real Chrome has a legit TLS/JA3 fingerprint
        #   2. --disable-blink-features=AutomationControlled removes the automation flag
        #   3. navigator.webdriver is patched to undefined via init_script
        # Falls back to bundled Chromium if Chrome isn't installed.
        try:
            browser = p.chromium.launch(
                channel="chrome",
                headless=not headed,
                slow_mo=100 if headed else 0,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            browser = p.chromium.launch(
                headless=not headed,
                slow_mo=100 if headed else 0,
                args=["--disable-blink-features=AutomationControlled"],
            )
        ctx = browser.new_context(
            storage_state=str(SESSION_FILE),
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
        )
        # Hide the webdriver flag that bot detectors probe for
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = ctx.new_page()

        # ── Step 1: Load portal, check session ───────────────────────────────
        # Use "domcontentloaded" — Blinkit's SPA keeps background requests alive
        # indefinitely, so "networkidle" never fires reliably.
        logger.info("Loading Blinkit seller portal...")
        page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
        # Wait for either the sidebar nav or the "Sell on Blinkit" login CTA to
        # appear — whichever comes first — instead of a fixed sleep.
        try:
            page.wait_for_selector(
                "nav, [class*='sidebar'], [class*='nav'], button:has-text('Sell on Blinkit')",
                timeout=30_000,
            )
        except PWTimeout:
            pass  # proceed anyway and let _is_login_page sort it out

        if _is_login_page(page):
            browser.close()
            raise BlinkitSessionExpired(
                "Blinkit session has expired. Run: python automation/blinkit_auth.py"
            )

        logger.info("Session valid. Current URL: %s", page.url)

        # ── Step 2: Navigate to Performance via sidebar ───────────────────────
        # The portal is an SPA — /performance 404s. Must click the sidebar icon.
        # Give the sidebar 30s to fully mount (it lazy-loads after the SPA boots).
        logger.info("Waiting for sidebar to mount, then clicking Performance...")
        perf_clicked = False

        # Strategy A: explicit attribute-based selectors (fast path)
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

        # Strategy B: wait up to 30s for any element with text "Performance"
        if not perf_clicked:
            try:
                el = page.get_by_text("Performance").first
                el.wait_for(state="visible", timeout=30_000)
                el.click()
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
                time.sleep(2)
                perf_clicked = True
                logger.info("Clicked Performance via text. URL: %s", page.url)
            except Exception:
                pass

        # Strategy C: JS click on any element whose text includes "Performance"
        if not perf_clicked:
            try:
                clicked = page.evaluate("""
                    () => {
                        const el = [...document.querySelectorAll('a, button, li, div, span')]
                            .find(e => (e.innerText || '').trim() === 'Performance'
                                    && e.offsetParent !== null);
                        if (!el) return false;
                        el.click();
                        return true;
                    }
                """)
                if clicked:
                    page.wait_for_load_state("domcontentloaded", timeout=15_000)
                    time.sleep(2)
                    perf_clicked = True
                    logger.info("Clicked Performance via JS. URL: %s", page.url)
            except Exception:
                pass

        if not perf_clicked:
            # Log visible links to help debug what the sidebar actually contains
            links = page.evaluate("""
                () => [...document.querySelectorAll('a, button')]
                    .filter(e => e.offsetParent !== null)
                    .map(e => ({tag: e.tagName, text: (e.innerText||'').trim().slice(0,40),
                                href: e.href||'', aria: e.getAttribute('aria-label')||''}))
                    .slice(0, 20)
            """)
            logger.error("Visible links/buttons on page: %s", links)
            browser.close()
            raise RuntimeError(
                "Could not find Performance icon in sidebar. "
                "Check log for visible links. Run with --headed to debug visually."
            )

        # ── Step 3: Period is already "Last 7 days" (portal default — no click needed) ───

        # ── Step 4: Click "Reports" button ────────────────────────────────────
        logger.info("Clicking Reports button...")
        try:
            reports_btn = page.get_by_role("button", name="Reports")
            reports_btn.wait_for(timeout=30_000)
        except PWTimeout:
            browser.close()
            raise RuntimeError(
                "Could not find the 'Reports' button on the Performance page. "
                "Run with --headed to debug."
            )

        # ── Step 5: Capture the download ─────────────────────────────────────
        # The Reports button may directly download OR open a panel with a
        # separate Download/Export button — handle both cases.
        logger.info("Clicking Reports and waiting for download...")
        today_str = date.today().strftime("%d-%m-%Y")
        expected_name = f"sales-report-7d-{today_str}.xlsx"

        with page.expect_download(timeout=90_000) as dl_info:
            reports_btn.first.click()
            # Wait briefly — if a download panel opened, find the trigger within it
            time.sleep(3)
            for dl_sel in [
                "button:has-text('Download')",
                "button:has-text('Export')",
                "a:has-text('Download')",
                "[aria-label*='download' i]",
                "[class*='download' i]",
            ]:
                try:
                    el = page.locator(dl_sel).first
                    if el.count() and el.is_visible():
                        logger.info("Reports opened a panel — clicking trigger: %s", dl_sel)
                        el.click()
                        break
                except Exception:
                    continue

        download = dl_info.value
        if download.failure():
            browser.close()
            raise RuntimeError(f"Download failed: {download.failure()}")

        # Save to data/blinkit/auto/ using the portal's original filename
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
    """Full pipeline: scrape → ingest → return summary dict.

    Retries once on PWTimeout — Blinkit's server can be slow at noon when
    the machine is busy, causing a transient navigation timeout that resolves
    on a second attempt.
    """
    for attempt in range(1, 3):
        try:
            xlsx = scrape(dry_run=dry_run, headed=headed)
            break
        except PWTimeout as exc:
            if attempt == 2:
                raise
            logger.warning("Scrape attempt %d/2 timed out — retrying in 20s...", attempt)
            time.sleep(20)

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
