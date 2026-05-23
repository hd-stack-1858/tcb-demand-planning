"""
Blinkit SOH (Stock on Hand) scraper
=====================================
Downloads the daily inventory SOH report from the Blinkit seller portal
and ingests it into the blinkit_inventory_snapshots DB table.

Saves to: data/blinkit/auto/inventory/SOH/InventoryData_{day}{Mon}{year}.xlsx

Usage:
    python automation/blinkit_soh_scraper.py
    python automation/blinkit_soh_scraper.py --headed       # visible browser (debug)
    python automation/blinkit_soh_scraper.py --dry-run      # download only, skip DB ingest

Navigation flow (verified against live UI):
    1. seller.blinkit.com → load saved session
    2. Navigate to seller.blinkit.com/dashboard/inventory (Stock on hand tab by default)
    3. Click "Bulk reports" dropdown (top-right, above the product table)
    4. Click "Download Stock on Hand" (1st option) → file downloads immediately
    5. Rename with today's date and save to data/blinkit/auto/inventory/SOH/

Note: Download is immediate — no async generation wait needed (unlike performance CSVs).
Run with --headed on first use to verify selectors against the live portal.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv(Path(__file__).parent.parent / '.env')
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

PORTAL_URL     = 'https://seller.blinkit.com'
INVENTORY_URL  = 'https://seller.blinkit.com/dashboard/inventory'  # no query param = Stock on hand tab
SESSION_FILE   = Path(__file__).parent.parent / '.blinkit_session' / 'state.json'
DOWNLOAD_DIR  = Path(__file__).parent.parent / 'data' / 'blinkit' / 'auto' / 'inventory' / 'SOH'


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


def _click_by_text(page, text: str, timeout: int = 10_000) -> bool:
    try:
        el = page.get_by_text(text, exact=True).first
        el.wait_for(state='visible', timeout=timeout)
        el.click()
        time.sleep(1)
        logger.info("Clicked '%s'", text)
        return True
    except Exception:
        return False


def _click_by_text_partial(page, text: str, timeout: int = 10_000) -> bool:
    try:
        el = page.get_by_text(text).first
        el.wait_for(state='visible', timeout=timeout)
        el.click()
        time.sleep(1)
        logger.info("Clicked partial text '%s'", text)
        return True
    except Exception:
        return False


def _click_first_visible(page, selectors: list[str], description: str, timeout: int = 8_000) -> bool:
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


def _click_js(page, text: str) -> bool:
    try:
        clicked = page.evaluate(f"""
            () => {{
                const el = [...document.querySelectorAll('a, button, li, div, span')]
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


def _log_visible(page):
    try:
        els = page.evaluate("""
            () => [...document.querySelectorAll('a, button, [role="menuitem"]')]
                .filter(e => e.offsetParent !== null)
                .map(e => (e.innerText||'').trim().slice(0,60))
                .filter(Boolean).slice(0, 20)
        """)
        logger.info('Visible interactive elements: %s', els)
    except Exception:
        pass


def _today_filename() -> str:
    today = date.today()
    return f'InventoryData_{today.day}{today.strftime("%b")}{today.year}.xlsx'


def scrape(headed: bool = False) -> Path:
    """
    Download today's SOH report from the Blinkit Inventory page.
    Returns Path to the saved file.
    Raises BlinkitSessionExpired if session is stale.
    """
    if not SESSION_FILE.exists():
        raise FileNotFoundError(
            f'No saved session at {SESSION_FILE}.\n'
            'Run: python automation/blinkit_auth.py'
        )

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest_name = _today_filename()
    dest_path = DOWNLOAD_DIR / dest_name

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
        logger.info('Session valid.')

        # ── Step 2: Navigate to Inventory → Stock on hand ────────────────────
        # The sidebar 'Inventory' link lands on Scheduled Inventory (?inventory=scheduled_inventory).
        # Direct URL to the dashboard inventory page lands on Stock on hand by default.
        logger.info('Navigating to Inventory / Stock on hand...')
        page.goto(INVENTORY_URL, wait_until='domcontentloaded', timeout=30_000)
        time.sleep(3)
        logger.info('URL: %s', page.url)

        # Safety: explicitly click "Stock on hand" tab in case the page opened on another tab
        for label in ['Stock on hand', 'Stock On Hand']:
            if _click_by_text(page, label, timeout=6_000) or _click_js(page, label):
                logger.info("Clicked 'Stock on hand' tab")
                time.sleep(2)
                break

        # ── Step 3: Open "Bulk reports" Ant Design Select ───────────────────────
        # This is an ant-select component (not a <button>). Must use Playwright's
        # real click() so React's synthetic event fires and the dropdown opens.
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)

        bulk_clicked = False

        # Primary: Playwright click on the ant-select wrapper that has "Bulk reports"
        # as its placeholder. filter(has=...) narrows to the right select component.
        try:
            el = page.locator('.ant-select').filter(
                has=page.locator('.ant-select-selection-placeholder', has_text='Bulk reports')
            ).first
            el.wait_for(state='visible', timeout=8_000)
            el.click()
            time.sleep(1.5)
            bulk_clicked = True
            logger.info("Opened 'Bulk reports' ant-select")
        except Exception as exc:
            logger.info("ant-select click failed: %s", exc)

        # Fallback: click the selector div directly
        if not bulk_clicked:
            try:
                el = page.locator('.ant-select-selector').filter(
                    has_text='Bulk reports'
                ).first
                el.wait_for(state='visible', timeout=5_000)
                el.click()
                time.sleep(1.5)
                bulk_clicked = True
                logger.info("Opened 'Bulk reports' via ant-select-selector")
            except Exception:
                pass

        if not bulk_clicked:
            _log_visible(page)
            browser.close()
            raise RuntimeError(
                'Could not open "Bulk reports" ant-select. Run with --headed to debug.'
            )

        # Wait for Ant Design dropdown panel to appear
        try:
            page.wait_for_selector(
                '.ant-select-dropdown:not(.ant-select-dropdown-hidden)',
                timeout=5_000,
            )
            logger.info("Bulk reports dropdown panel opened")
        except Exception:
            logger.warning("Dropdown panel not detected — proceeding anyway")
        time.sleep(0.5)

        # ── Step 4: Click "Download Stock on Hand" option → immediate download ───
        # Ant Design options are appended to <body> in a portal (.ant-select-dropdown).
        logger.info('Clicking "Download Stock on Hand" and capturing download...')
        with page.expect_download(timeout=60_000) as dl_info:
            soh_clicked = False

            for sel in [
                ".ant-select-item-option:has-text('Download Stock on Hand')",
                ".ant-select-item:has-text('Download Stock on Hand')",
                "[role='option']:has-text('Download Stock on Hand')",
                ".ant-select-dropdown .ant-select-item-option-content:has-text('Download Stock on Hand')",
                "li:has-text('Download Stock on Hand')",
            ]:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state='visible', timeout=4_000)
                    el.click()
                    soh_clicked = True
                    logger.info("Clicked 'Download Stock on Hand' via: %s", sel)
                    break
                except Exception:
                    continue

            # JS fallback (searches full DOM including portal)
            if not soh_clicked:
                try:
                    clicked = page.evaluate("""
                        () => {
                            const el = [...document.querySelectorAll('div, span, li')]
                                .find(e => {
                                    const t = (e.innerText || '').trim();
                                    return t.startsWith('Download Stock on Hand')
                                        && e.offsetParent !== null;
                                });
                            if (!el) return false;
                            el.click();
                            return true;
                        }
                    """)
                    if clicked:
                        soh_clicked = True
                        logger.info("JS-clicked 'Download Stock on Hand'")
                except Exception:
                    pass

            if not soh_clicked:
                _log_visible(page)
                browser.close()
                raise RuntimeError(
                    'Could not find "Download Stock on Hand" in dropdown. '
                    'Run with --headed to debug.'
                )

        download = dl_info.value
        if download.failure():
            browser.close()
            raise RuntimeError(f'Download failed: {download.failure()}')

        download.save_as(str(dest_path))
        logger.info('Saved: %s', dest_path)

        browser.close()

    return dest_path


def ingest(xlsx_path: Path, dry_run: bool = False):
    """Ingest downloaded SOH file into blinkit_inventory_snapshots."""
    from ingest.blinkit_inventory_loader import load_file
    logger.info('Ingesting: %s', xlsx_path.name)
    load_file(xlsx_path, dry_run=dry_run)


def run(headed: bool = False, dry_run: bool = False) -> dict:
    xlsx_path = scrape(headed=headed)
    ingest(xlsx_path, dry_run=dry_run)
    return {'file': xlsx_path.name}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Blinkit SOH inventory scraper')
    parser.add_argument('--headed',  action='store_true', help='Show browser (debug)')
    parser.add_argument('--dry-run', action='store_true', help='Download only, skip DB ingest')
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
