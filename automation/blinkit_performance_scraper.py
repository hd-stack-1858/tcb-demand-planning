"""
Blinkit Product Performance Detail Scraper
==========================================
Downloads the daily Product Performance detail CSV from the Blinkit seller portal.
Must run every day — Blinkit does NOT allow retroactive access to past performance data.

Saves to: data/blinkit/auto/product_performance/detail/

Usage:
    python automation/blinkit_performance_scraper.py
    python automation/blinkit_performance_scraper.py --headed       # visible browser (debug)
    python automation/blinkit_performance_scraper.py --dry-run      # download only, skip ingest

Session auth: relies on .blinkit_session/state.json saved by blinkit_auth.py.
If session is expired, raises BlinkitSessionExpired (exit code 2 → WhatsApp alert).

Navigation flow (Blinkit seller portal):
    1. seller.blinkit.com → load saved session
    2. Left sidebar → "Performance" icon
    3. Sub-nav → "Product Performance" (or "Item Performance")
    4. Tab → "Detail" (not Summary)
    5. Set date = today
    6. Click Download/Export
    7. Save CSV to data/blinkit/auto/product_performance/detail/

Note: Run with --headed on first use to verify selectors against the live portal.
Blinkit occasionally changes their UI — check DOWNLOAD_DIR after each release.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

if TYPE_CHECKING:
    from playwright.sync_api import Page, BrowserContext

load_dotenv(Path(__file__).parent.parent / '.env')
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

PORTAL_URL   = 'https://seller.blinkit.com'
SESSION_FILE = Path(__file__).parent.parent / '.blinkit_session' / 'state.json'
DOWNLOAD_DIR = Path(__file__).parent.parent / 'data' / 'blinkit' / 'auto' / 'product_performance' / 'detail'


class BlinkitSessionExpired(Exception):
    pass


def _is_login_page(page) -> bool:
    try:
        btn = page.get_by_role('button', name='Sell on Blinkit')
        if btn.count() and btn.first.is_visible():
            return True
        link = page.get_by_text('Sell on Blinkit', exact=True)
        return link.count() > 0 and link.first.is_visible()
    except Exception:
        return False


def _new_browser_context(playwright, headed: bool) -> tuple:
    try:
        browser = playwright.chromium.launch(
            channel='chrome',
            headless=not headed,
            slow_mo=150 if headed else 50,
            args=['--disable-blink-features=AutomationControlled'],
        )
    except Exception:
        browser = playwright.chromium.launch(
            headless=not headed,
            slow_mo=150 if headed else 50,
            args=['--disable-blink-features=AutomationControlled'],
        )
    ctx = browser.new_context(
        storage_state=str(SESSION_FILE),
        accept_downloads=True,
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/136.0.0.0 Safari/537.36'
        ),
    )
    ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, ctx


def _click_first_visible(page, selectors: list[str], description: str, timeout: int = 5_000) -> bool:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            el.wait_for(state='visible', timeout=timeout)
            el.click()
            time.sleep(1)
            logger.info('Clicked %s via: %s', description, sel)
            return True
        except Exception:
            continue
    return False


def _click_by_text(page, text: str, timeout: int = 15_000) -> bool:
    try:
        el = page.get_by_text(text, exact=True).first
        el.wait_for(state='visible', timeout=timeout)
        el.click()
        time.sleep(1)
        logger.info("Clicked '%s' via text match", text)
        return True
    except Exception:
        return False


def _click_by_text_partial(page, text: str, timeout: int = 15_000) -> bool:
    try:
        el = page.get_by_text(text).first
        el.wait_for(state='visible', timeout=timeout)
        el.click()
        time.sleep(1)
        logger.info("Clicked partial text '%s'", text)
        return True
    except Exception:
        return False


def _click_js(page, text: str) -> bool:
    try:
        clicked = page.evaluate(f"""
            () => {{
                const el = [...document.querySelectorAll('a, button, li, div, span, [role="tab"]')]
                    .find(e => (e.innerText || '').trim() === '{text}'
                            && e.offsetParent !== null);
                if (!el) return false;
                el.click();
                return true;
            }}
        """)
        if clicked:
            time.sleep(1)
            logger.info("JS-clicked '%s'", text)
            return True
    except Exception:
        pass
    return False


def _log_visible_links(page):
    try:
        links = page.evaluate("""
            () => [...document.querySelectorAll('a, button, [role="tab"], [role="menuitem"]')]
                .filter(e => e.offsetParent !== null)
                .map(e => ({
                    tag:  e.tagName,
                    text: (e.innerText||'').trim().slice(0,50),
                    href: e.href||'',
                    aria: e.getAttribute('aria-label')||''
                }))
                .slice(0, 30)
        """)
        logger.info('Visible interactive elements: %s', links)
    except Exception:
        pass


def scrape(headed: bool = False) -> Path:
    """
    Download today's Product Performance detail CSV.
    Returns Path to the saved CSV file.
    Raises BlinkitSessionExpired if session is stale.
    """
    if not SESSION_FILE.exists():
        raise FileNotFoundError(
            f'No saved session at {SESSION_FILE}.\n'
            'Run: python automation/blinkit_auth.py'
        )

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser, ctx = _new_browser_context(p, headed)
        page = ctx.new_page()

        # ── Step 1: Load portal, verify session ──────────────────────────────
        logger.info('Loading Blinkit seller portal...')
        page.goto(PORTAL_URL, wait_until='domcontentloaded', timeout=60_000)
        try:
            page.wait_for_selector(
                "nav, [class*='sidebar'], button:has-text('Sell on Blinkit')",
                timeout=30_000,
            )
        except PWTimeout:
            pass

        if _is_login_page(page):
            browser.close()
            raise BlinkitSessionExpired(
                'Blinkit session expired. Run: python automation/blinkit_auth.py'
            )
        logger.info('Session valid. URL: %s', page.url)

        # ── Step 2: Click Performance in sidebar ─────────────────────────────
        perf_selectors = [
            "[aria-label='Performance']",
            "[title='Performance']",
            "a[href*='performance']",
            "nav a:nth-child(2)",
            "[class*='nav'] a:nth-child(2)",
        ]
        if not _click_first_visible(page, perf_selectors, 'Performance', timeout=8_000):
            if not _click_by_text(page, 'Performance'):
                if not _click_js(page, 'Performance'):
                    _log_visible_links(page)
                    browser.close()
                    raise RuntimeError(
                        "Could not find Performance in sidebar. Run with --headed to debug."
                    )
        page.wait_for_load_state('domcontentloaded', timeout=15_000)
        time.sleep(2)

        # ── Step 3: Navigate to Product Performance / Item Performance ────────
        # Blinkit may call this section differently; try both names.
        product_perf_clicked = False
        for label in ['Product Performance', 'Item Performance', 'Item Wise', 'Product Wise']:
            if _click_by_text(page, label, timeout=5_000) or _click_js(page, label):
                product_perf_clicked = True
                break
            if _click_by_text_partial(page, label, timeout=5_000):
                product_perf_clicked = True
                break

        if not product_perf_clicked:
            # May already be on product performance after clicking Performance
            logger.warning("Could not find 'Product Performance' sub-nav — proceeding on current page")

        page.wait_for_load_state('domcontentloaded', timeout=15_000)
        time.sleep(2)
        logger.info('URL after navigation: %s', page.url)

        # ── Step 4: Click Detail tab (not Summary) ────────────────────────────
        detail_clicked = False
        for label in ['Detail', 'Detailed', 'Item Level', 'SKU Level']:
            if _click_by_text(page, label, timeout=5_000) or _click_js(page, label):
                detail_clicked = True
                logger.info("Clicked Detail tab: '%s'", label)
                break

        if not detail_clicked:
            logger.warning("Could not find Detail tab — proceeding (may already be on Detail view)")

        page.wait_for_load_state('domcontentloaded', timeout=10_000)
        time.sleep(2)

        # ── Step 5: Set date to today ─────────────────────────────────────────
        # Blinkit performance detail typically defaults to today or yesterday.
        # Try to set date picker to today if visible.
        today_str = date.today().strftime('%d %b %Y')  # e.g. "21 May 2026"
        date_selectors = [
            "[class*='datepicker']",
            "[class*='date-picker']",
            "input[type='date']",
            "[class*='DatePicker']",
        ]
        for sel in date_selectors:
            try:
                el = page.locator(sel).first
                if el.count() and el.is_visible():
                    # Fill if it's an input, otherwise click and type
                    el.click()
                    time.sleep(1)
                    logger.info('Date picker opened via: %s', sel)
                    break
            except Exception:
                continue
        # Don't fail if date picker isn't found — today is usually the default

        time.sleep(2)

        # ── Step 6: Download the CSV ──────────────────────────────────────────
        logger.info('Waiting for download button...')
        download_selectors = [
            "button:has-text('Download')",
            "button:has-text('Export')",
            "button:has-text('Export CSV')",
            "button:has-text('Download CSV')",
            "[aria-label*='download' i]",
            "[aria-label*='export' i]",
            "[class*='download' i] button",
            "a:has-text('Download')",
            "a:has-text('Export')",
        ]

        # Wait for any download button to appear
        download_el = None
        for sel in download_selectors:
            try:
                el = page.locator(sel).first
                el.wait_for(state='visible', timeout=10_000)
                download_el = el
                logger.info('Found download button: %s', sel)
                break
            except Exception:
                continue

        if download_el is None:
            _log_visible_links(page)
            browser.close()
            raise RuntimeError(
                'Could not find Download/Export button on Product Performance Detail page. '
                'Run with --headed to debug. The UI may have changed.'
            )

        today_prefix = date.today().strftime('%Y%m%d')
        expected_name = f'blinkit_performance_detail_{today_prefix}.csv'

        logger.info('Clicking download and capturing file...')
        with page.expect_download(timeout=90_000) as dl_info:
            download_el.click()
            time.sleep(3)
            # If clicking opened a panel, look for a secondary trigger
            for secondary in [
                "button:has-text('Download')",
                "button:has-text('Confirm')",
                "button:has-text('Export')",
                "[class*='modal'] button:has-text('Download')",
            ]:
                try:
                    el2 = page.locator(secondary).first
                    if el2.count() and el2.is_visible():
                        logger.info('Secondary trigger: %s', secondary)
                        el2.click()
                        break
                except Exception:
                    continue

        download = dl_info.value
        if download.failure():
            browser.close()
            raise RuntimeError(f'Download failed: {download.failure()}')

        # Use Blinkit's suggested filename (has embedded timestamp/IDs)
        final_name = download.suggested_filename or expected_name
        dest = DOWNLOAD_DIR / final_name
        download.save_as(str(dest))
        logger.info('Saved: %s', dest)

        browser.close()

    return dest


def ingest(csv_path: Path, dry_run: bool = False):
    """Run blinkit_performance_loader on the downloaded file."""
    from ingest.blinkit_performance_loader import (
        build_sku_lookup, build_ds_location_lookup, build_wh_location_lookup,
        process_file
    )
    print(f'\nIngesting: {csv_path.name}')
    sku_lookup = build_sku_lookup()
    ds_lookup  = build_ds_location_lookup()
    wh_lookup  = build_wh_location_lookup()
    if not dry_run:
        process_file(csv_path, sku_lookup, ds_lookup, wh_lookup)
    else:
        print('  DRY RUN — no DB writes')


def run(headed: bool = False, dry_run: bool = False) -> dict:
    for attempt in range(1, 3):
        try:
            csv_path = scrape(headed=headed)
            break
        except PWTimeout as exc:
            if attempt == 2:
                raise
            logger.warning('Attempt %d/2 timed out — retrying in 20s...', attempt)
            time.sleep(20)

    ingest(csv_path, dry_run=dry_run)
    return {'file': csv_path.name}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Blinkit performance detail scraper')
    parser.add_argument('--headed',  action='store_true', help='Show browser (debug)')
    parser.add_argument('--dry-run', action='store_true', help='Download only, skip ingest')
    args = parser.parse_args()

    os.environ.setdefault('TCB_ENV', 'prod')

    try:
        result = run(headed=args.headed, dry_run=args.dry_run)
        print(f'\nDone: {result["file"]}')
    except BlinkitSessionExpired as e:
        print(f'SESSION EXPIRED: {e}')
        sys.exit(2)
    except Exception as e:
        logger.exception('Scraper failed')
        print(f'ERROR: {e}')
        sys.exit(1)
