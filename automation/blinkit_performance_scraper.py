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

Navigation flow (Blinkit seller portal — verified against live UI):
    1. seller.blinkit.com → load saved session
    2. Left sidebar → "Performance" icon
    3. Top tab → "Product Expansion" (NOT "Sales Performance")
    4. Click header checkbox to select ALL products
    5. Hover "Reports" dropdown (top-right) → click "Detailed Report"
    6. Wait 7–8 minutes for CSV generation and auto-download
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


def _click_js_normalized(page, text: str) -> bool:
    """
    JS click without offsetParent check — more reliable for dropdown menus.
    offsetParent is null for position:absolute children in headless Chromium even
    when the element is visually open; this function skips that check.
    Also normalises inner whitespace so 'Detailed\\nReport' matches 'Detailed Report'.
    """
    try:
        clicked = page.evaluate(f"""
            () => {{
                const target = '{text}';
                const el = [...document.querySelectorAll(
                    'a, button, li, div, span, [role="menuitem"], [role="option"]'
                )].find(e => (e.innerText || '').replace(/\\s+/g, ' ').trim() === target);
                if (!el) return false;
                el.click();
                return true;
            }}
        """)
        if clicked:
            time.sleep(0.5)
            logger.info("JS-normalized-clicked '%s'", text)
            return True
    except Exception:
        pass
    return False


def _log_visible_links(page):
    try:
        links = page.evaluate("""
            () => [...document.querySelectorAll(
                'a, button, li, [role="tab"], [role="menuitem"], [role="option"]'
            )]
                .filter(e => {
                    // getBoundingClientRect is more reliable than offsetParent for
                    // position:absolute dropdown children in headless Chromium.
                    const r = e.getBoundingClientRect();
                    return r.width > 0 || r.height > 0;
                })
                .map(e => ({
                    tag:  e.tagName,
                    text: (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,60),
                    href: e.href||'',
                    aria: e.getAttribute('aria-label')||''
                }))
                .filter(e => e.text.length > 0)
                .slice(0, 40)
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

        # ── Step 3: Click "Product Expansion" tab ────────────────────────────
        # The Performance page has multiple top-level tabs. We need "Product Expansion"
        # (NOT "Sales Performance"). Try exact match first, then partial.
        pe_clicked = False
        for label in ['Product Expansion', 'Expansion']:
            if _click_by_text(page, label, timeout=8_000) or _click_js(page, label):
                pe_clicked = True
                logger.info("Clicked Product Expansion tab: '%s'", label)
                break
            if _click_by_text_partial(page, label, timeout=5_000):
                pe_clicked = True
                logger.info("Clicked Product Expansion tab (partial): '%s'", label)
                break

        if not pe_clicked:
            logger.warning("Could not find 'Product Expansion' tab — proceeding on current page")
            _log_visible_links(page)

        page.wait_for_load_state('domcontentloaded', timeout=15_000)
        time.sleep(3)
        logger.info('URL after Product Expansion click: %s', page.url)

        # ── Step 4: Click header checkbox to select ALL products ──────────────
        # There is a checkbox in the table header row that selects all items.
        header_cb_selectors = [
            "thead input[type='checkbox']",
            "th input[type='checkbox']",
            "[class*='header'] input[type='checkbox']",
            "table input[type='checkbox']:first-of-type",
            "input[type='checkbox']:first-of-type",
        ]
        cb_clicked = False
        for sel in header_cb_selectors:
            try:
                el = page.locator(sel).first
                el.wait_for(state='visible', timeout=8_000)
                el.click()
                time.sleep(1)
                logger.info('Clicked header checkbox via: %s', sel)
                cb_clicked = True
                break
            except Exception:
                continue

        if not cb_clicked:
            # Fallback: click via JS looking for any unchecked header checkbox
            try:
                clicked = page.evaluate("""
                    () => {
                        const cb = document.querySelector(
                            'thead input[type="checkbox"], th input[type="checkbox"]'
                        );
                        if (cb && !cb.checked) { cb.click(); return true; }
                        if (cb) { return true; }  // already checked
                        return false;
                    }
                """)
                if clicked:
                    time.sleep(1)
                    logger.info('Header checkbox clicked via JS fallback')
                    cb_clicked = True
            except Exception:
                pass

        if not cb_clicked:
            _log_visible_links(page)
            browser.close()
            raise RuntimeError(
                'Could not find header checkbox on Product Expansion tab. '
                'Run with --headed to debug.'
            )

        time.sleep(2)

        # ── Step 5: Open "Reports" dropdown → click "Detailed Report" ─────────
        # The Reports dropdown is on the top-right of the page.
        reports_clicked = False
        for label in ['Reports', 'Report']:
            if _click_by_text(page, label, timeout=8_000) or _click_js(page, label):
                reports_clicked = True
                logger.info("Opened Reports dropdown: '%s'", label)
                break

        if not reports_clicked:
            # Try aria/class selectors for a dropdown button
            for sel in [
                "button:has-text('Reports')",
                "[class*='report' i] button",
                "[aria-label*='report' i]",
            ]:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state='visible', timeout=5_000)
                    el.click()
                    time.sleep(1)
                    reports_clicked = True
                    logger.info('Opened Reports dropdown via selector: %s', sel)
                    break
                except Exception:
                    continue

        if not reports_clicked:
            _log_visible_links(page)
            browser.close()
            raise RuntimeError(
                'Could not find Reports dropdown on Product Expansion tab. '
                'Run with --headed to debug.'
            )

        time.sleep(1)

        # Log dropdown contents NOW (before expect_download) so any future label
        # change is diagnosable without needing --headed.
        _log_visible_links(page)

        # ── Step 6: Click "Detailed Report" — this triggers the download ─────
        # Must be inside expect_download() so Playwright captures the file event.
        today_prefix = date.today().strftime('%Y%m%d')
        expected_name = f'blinkit_performance_detail_{today_prefix}.csv'
        logger.info('Clicking Detailed Report and waiting for CSV (up to 10 min)...')

        with page.expect_download(timeout=900_000) as dl_info:  # 15-minute timeout (file is ~85K rows now)
            detailed_clicked = False
            for label in ['Detailed Report', 'Detailed', 'Detail Report']:
                # Try JS click FIRST — it's instant and avoids the dropdown auto-closing
                # during a long Playwright wait. Also normalises whitespace so innerText
                # with a newline ("Detailed\nReport") still matches.
                if _click_js_normalized(page, label) or _click_by_text(page, label, timeout=2_000):
                    detailed_clicked = True
                    logger.info("Clicked dropdown item: '%s'", label)
                    break

            if not detailed_clicked:
                # Last resort: click the first visible menuitem / li in the open dropdown
                logger.info("Exact label not found — trying first visible dropdown item")
                for sel in [
                    '[role="menuitem"]',
                    '[role="option"]',
                    'ul[class*="dropdown"] li',
                    'ul[class*="menu"] li',
                    'div[class*="dropdown"] li',
                ]:
                    try:
                        el = page.locator(sel).first
                        if el.count() and el.is_visible(timeout=2_000):
                            text = el.inner_text()
                            el.click()
                            detailed_clicked = True
                            logger.info("Clicked first dropdown item via '%s': text=%r", sel, text)
                            break
                    except Exception:
                        continue

            if not detailed_clicked:
                browser.close()
                raise RuntimeError(
                    'Could not find "Detailed Report" in Reports dropdown. '
                    'Check log for "Visible interactive elements" to see current labels. '
                    'Run with --headed to debug.'
                )

            # If a confirmation modal appears before the download begins
            time.sleep(5)
            for secondary in [
                "button:has-text('Download')",
                "button:has-text('Confirm')",
                "button:has-text('Export')",
                "[class*='modal'] button:has-text('Download')",
                "[class*='modal'] button:has-text('Confirm')",
            ]:
                try:
                    el2 = page.locator(secondary).first
                    if el2.count() and el2.is_visible():
                        logger.info('Modal confirm button found: %s', secondary)
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

        ctx.storage_state(path=str(SESSION_FILE))
        logger.info('Session refreshed: %s', SESSION_FILE)
        browser.close()

    return dest


def ingest(csv_path: Path, dry_run: bool = False):
    """Run blinkit_performance_loader on the downloaded file."""
    from ingest.blinkit_performance_loader import (
        build_sku_lookup, build_ds_location_lookup, build_wh_location_lookup,
        build_ds_parent_lookup, process_file,
        scan_ds_from_files, refresh_ds_master, update_ds_cities,
    )
    print(f'\nIngesting: {csv_path.name}')
    sku_lookup       = build_sku_lookup()
    ds_lookup        = build_ds_location_lookup()
    wh_lookup        = build_wh_location_lookup()
    ds_parent_lookup = build_ds_parent_lookup()
    if not dry_run:
        # Pass 0a: seed any DS that are new in this file before processing
        ds_to_wh_name, ds_to_city, _ = scan_ds_from_files([csv_path])
        new_ds = refresh_ds_master(ds_to_wh_name, wh_lookup, ds_lookup, ds_to_city=ds_to_city)
        if new_ds:
            print(f'  Pass 0a: inserted {new_ds} new DS into partner_locations')
            ds_lookup        = build_ds_location_lookup()
            ds_parent_lookup = build_ds_parent_lookup()
        city_updated = update_ds_cities(ds_to_city, ds_lookup)
        if city_updated:
            print(f'  Pass 0a: {city_updated} DS city values updated')
        process_file(csv_path, sku_lookup, ds_lookup, wh_lookup, ds_parent_lookup)
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
