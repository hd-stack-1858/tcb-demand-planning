"""
FnP order processor.
Runs at 11:00, 14:00, 16:00 IST via Windows Task Scheduler.

Flow each run:
  1. Login to partner.fnp.com
  2. Navigate to Allocated orders:
       - If any: select all → ACCEPT → orders move to "Orders to be shipped"
  3. Navigate to Orders to be Shipped:
       - If any: select all → BRANDING CHALLAN → PDF downloads
  4. Email PDF to Himanshu + Dilwar

Clean no-op if no orders found. Self-healing: orders stuck in "Orders to be
shipped" from a failed run are picked up on the next run automatically.

Required .env vars:
  FNP_USERNAME      vendor portal email (shubhra@thecradlebox.com)
  FNP_PASSWORD      vendor portal password
  SMTP_SENDER       sending email address (hd@thecradlebox.com)
  SMTP_PASSWORD     Gmail App Password for SMTP_SENDER
  EMAIL_HIMANSHU    Himanshu's email
  EMAIL_DILWAR      Dilwar's email

Usage:
  python automation/fnp_scraper.py              # normal run
  python automation/fnp_scraper.py --dry-run    # download PDF, skip email
  python automation/fnp_scraper.py --headed     # show browser window (debug)

Logs: automation/logs/fnp_YYYYMMDD.log

DEBUGGING FIRST RUN:
  Run with --headed to watch the browser. If it fails mid-flow, check the log
  for the URL it's stuck on and adjust selectors in _click_section() below.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_DIR  = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"fnp_{date.today().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(str(log_file), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

PORTAL_URL   = "https://partner.fnp.com/vendorapp/templates/index.html#/login/"
DOWNLOAD_DIR = Path(__file__).parent.parent / "data" / "fnp" / "auto"  # scraper writes challans here
LOCK_FILE    = LOG_DIR / "fnp_scraper.lock"

# FnP may show product names instead of TCB codes — map common names to SKU IDs.
# Keys are lowercase. Update when new SKUs are listed on FnP.
_FNP_PRODUCT_TO_SKU: dict[str, str] = {
    "tiny splash hamper pink":     "TCB001",
    "tiny splash hamper blue":     "TCB002",
    "little looker hamper 6pcs":   "TCB003",
    "little looker (6pcs)":        "TCB003",
    "cosy cub hamper":             "TCB004",
    "growing joy 0-6 months":      "TCB005",
    "growing joy 0-6m":            "TCB005",
    "growing joy 7-12 months":     "TCB006",
    "growing joy 7-12m":           "TCB006",
    "welcome to us hamper":        "TCB007",
    "just arrived hamper bunny":   "TCB008",
    "just arrived bunny":          "TCB008",
    "hello parenthood hamper":     "TCB009",
    "growing joy 0-12 months":     "TCB010",
    "growing joy 0-12m":           "TCB010",
    "just arrived hamper bear":    "TCB011",
    "just arrived bear":           "TCB011",
    "little looker hamper 4pcs":   "TCB012",
    "little looker (4pcs)":        "TCB012",
}


def _parse_sku(raw: str | None) -> str | None:
    """Resolve a raw portal string to a TCB SKU ID. Returns None if unresolvable."""
    if not raw:
        return None
    s = raw.strip()
    if re.match(r"^TCB\d{3}$", s, re.IGNORECASE):
        return s.upper()
    return _FNP_PRODUCT_TO_SKU.get(s.lower())


# ── Login ──────────────────────────────────────────────────────────────────────

def _login(page) -> None:
    username = os.environ.get("FNP_USERNAME", "").strip()
    password = os.environ.get("FNP_PASSWORD", "").strip()
    if not username or not password:
        raise EnvironmentError("FNP_USERNAME and FNP_PASSWORD must be set in .env")

    logger.info("Opening FnP portal...")
    # "commit" fires as soon as HTTP response headers arrive — much earlier than
    # "domcontentloaded" on slow connections where Angular bundles take a long time.
    # We wait for the actual page content with wait_for_selector below instead.
    page.goto(PORTAL_URL, wait_until="commit", timeout=60_000)
    time.sleep(2)

    # If portal redirected away from the login URL, session is still active — skip login
    logger.info("Post-navigation URL: %s", page.url)
    if "#/login" not in page.url:
        logger.info("Session active — already on dashboard. Skipping login.")
        return

    # Still on login page — fill credentials
    # Use visible inputs only to avoid matching hidden dashboard elements
    email_input = page.locator("input[type='email']").first
    if not email_input.count() or not email_input.is_visible():
        email_input = page.locator("input[type='text']:visible").first
    email_input.fill(username)
    page.locator("input[type='password']").first.fill(password)
    page.get_by_role("button", name="Login").click()

    # Wait for Angular SPA to navigate away from login
    # "text=Allocated" is NOT safe: the login page has "An order has been allocated to you."
    page.wait_for_url(lambda url: "#/login" not in url, timeout=30_000)
    page.wait_for_load_state("load", timeout=30_000)
    # Wait for the dashboard grid to actually render — Angular fires backend API calls
    # after the load event, so we need to wait for the date-cell content to appear.
    page.wait_for_selector("text=TODAY", timeout=30_000)
    time.sleep(1)
    logger.info("Logged in. Dashboard loaded. URL: %s", page.url)


# ── Dashboard navigation ───────────────────────────────────────────────────────

def _scan_section(page, label: str, retries: int = 6) -> list[tuple[int, int]]:
    """
    Scan the dashboard section for label.
    Returns list of (child_index, count) for every non-zero date column.

    DOM structure (div-based Angular app, not a table):
      DIV (parent)
        H2  "Allocated"  (or similar for "Orders to be shipped")
        DIV.ng-scope     <- direct children are date cells (TODAY/TOMORROW/FUTURE)

    Retries up to `retries` times with 3s gaps because Angular fetches order counts
    via XHR after the load event — the DOM may be present but cells unpopulated.
    """
    for attempt in range(retries):
        result = page.evaluate(f"""
            () => {{
                // Match label element across common tags.
                // Use startsWith (not ===) because the element may contain icon
                // child nodes that add extra text to innerText (e.g. export button).
                let labelEl = null;
                for (const tag of ['h2', 'h3', 'div', 'span', 'p']) {{
                    for (const el of document.querySelectorAll(tag)) {{
                        const t = (el.innerText || el.textContent || '').trim();
                        if (t === '{label}' || t.startsWith('{label}\\n') || t.startsWith('{label} ')) {{
                            labelEl = el;
                            break;
                        }}
                    }}
                    if (labelEl) break;
                }}
                if (!labelEl) return {{found_label: false, found_container: false, cells: []}};

                const p1 = labelEl.parentElement;
                const dateContainer = Array.from(p1.children).find(c => c !== labelEl);
                if (!dateContainer) return {{found_label: true, found_container: false, cells: []}};

                // Scan direct children for (N) count pattern
                const cells = [];
                Array.from(dateContainer.children).forEach((child, idx) => {{
                    const text = (child.innerText || '').trim();
                    const m = text.match(/\\((\\d+)\\)/);
                    if (m) {{
                        cells.push({{idx: idx, count: parseInt(m[1]), text: text.replace(/\\n/g, ' ')}});
                    }}
                }});
                return {{found_label: true, found_container: true, cells: cells}};
            }}
        """)

        found_label     = result.get("found_label", False)
        found_container = result.get("found_container", False)
        cells           = result.get("cells", [])

        logger.info("'%s' scan (attempt %d/%d): label=%s container=%s cells=%s",
                    label, attempt + 1, retries, found_label, found_container, cells)

        if found_label and found_container and len(cells) > 0:
            # Angular has rendered the date cells — trust the counts
            nonzero = [(c["idx"], c["count"]) for c in cells if c["count"] > 0]
            if not nonzero:
                logger.info("'%s': all columns are zero — nothing to process.", label)
            return nonzero

        # Not fully rendered yet — wait and retry
        if attempt < retries - 1:
            logger.info(
                "'%s': not ready (label=%s, container=%s, cells=%d) — waiting 3s...",
                label, found_label, found_container, len(cells),
            )
            time.sleep(3)

    logger.warning("'%s': section never fully rendered after %d attempts.", label, retries)
    return []


def _click_column(page, label: str, child_idx: int) -> None:
    """
    Click the date cell at child_idx inside the section's DIV.ng-scope container.
    """
    page.evaluate(f"""
        () => {{
            let labelEl = null;
            for (const el of document.querySelectorAll('h2, h3')) {{
                if ((el.innerText || '').trim() === '{label}') {{
                    labelEl = el;
                    break;
                }}
            }}
            if (!labelEl) return;
            const p1 = labelEl.parentElement;
            const dateContainer = Array.from(p1.children).find(c => c !== labelEl);
            if (!dateContainer) return;
            const child = dateContainer.children[{child_idx}];
            if (child) child.click();
        }}
    """)
    page.wait_for_load_state("load", timeout=20_000)
    time.sleep(2)
    logger.info("Clicked '%s' child[%d]. URL: %s", label, child_idx, page.url)


def _return_to_dashboard(page) -> None:
    """
    Navigate back to the main dashboard after processing a section.
    Tries go_back() first; falls back to reloading the portal base URL.
    """
    page.go_back()
    page.wait_for_load_state("load", timeout=15_000)
    time.sleep(2)

    if page.locator("text=Orders to be shipped").count():
        logger.info("Back on dashboard.")
        return

    # Fallback: reload portal base (session still active, redirects to dashboard)
    base = PORTAL_URL.replace("#/login/", "")
    logger.info("go_back() didn't land on dashboard — trying %s", base)
    page.goto(base, wait_until="domcontentloaded", timeout=60_000)
    # Wait for the date-cell grid (same signal used in _login).
    # "text=Allocated" is NOT safe — matches the hero-text paragraph too.
    page.wait_for_selector("text=TODAY", timeout=30_000)
    time.sleep(2)
    logger.info("Dashboard loaded via base URL.")


# ── Order list page helpers ────────────────────────────────────────────────────

def _read_order_count(page) -> int:
    """
    Extract order count from the page heading.
    Headings like 'Allocated LastTenDays Orders (5)' → 5.
    Returns -1 if count cannot be determined (treat as "proceed anyway").
    """
    for sel in ["h1", "h2", "h3", "[class*='heading']", "[class*='title']", "[class*='page-title']"]:
        el = page.locator(sel).first
        if el.count() and el.is_visible():
            text = el.inner_text().strip()
            nums = re.findall(r'\((\d+)\)', text)
            if nums:
                count = int(nums[0])
                logger.info("Order count from heading '%s': %d", text, count)
                return count
    logger.warning("Could not read order count from page heading — proceeding with unknown count.")
    return -1


def _select_all(page) -> None:
    """Select all orders on the current list page."""
    # Prefer the header checkbox (checks everything at once)
    # The checkbox has id="selectall" and ng-model="selectall".
    # Use JS click — Playwright's .check() fails because the SPA scroll container
    # is an inner div, not window, so scrollIntoView leaves it "outside viewport".
    result = page.evaluate("""
        () => {
            const cb = document.getElementById('selectall')
                    || document.querySelector('input[ng-model="selectall"]')
                    || document.querySelector('input[type="checkbox"]');
            if (!cb) return {found: false};
            cb.scrollIntoView({behavior: 'instant', block: 'center'});
            cb.click();
            return {found: true, id: cb.id, checked: cb.checked};
        }
    """)
    logger.info("Select All result: %s", result)
    if result and result.get("found"):
        time.sleep(1)
        return
    logger.warning("No 'Select All' checkbox found.")


def _click_accept(page) -> None:
    """Click the Accept button on the Allocated orders page."""
    # ng-disabled until Select All is checked. Wait up to 5s for Angular to enable it,
    # then JS-click (scrollIntoView + click) to handle the SPA scroll container.
    # There are TWO bulkAccept buttons: ng-show="!selectall" and ng-show="selectall".
    # After Select All, the !selectall button gets ng-hide; the selectall button becomes visible.
    # Use getComputedStyle (not offsetParent — that's null for position:fixed bottom ribbons).
    find_js = """
        () => {
            const all = [...document.querySelectorAll('button')].map(b => ({
                text: (b.innerText || '').trim().substring(0, 40),
                cls: b.className,
                disabled: b.disabled,
                display: window.getComputedStyle(b).display,
                visibility: window.getComputedStyle(b).visibility,
            }));
            const btn = [...document.querySelectorAll('button')].find(b =>
                (b.innerText || '').trim().toLowerCase().startsWith('accept') &&
                !b.classList.contains('ng-hide') &&
                window.getComputedStyle(b).display !== 'none' &&
                window.getComputedStyle(b).visibility !== 'hidden'
            );
            if (!btn) return {found: false, all_buttons: all};
            return {found: true, disabled: btn.disabled, cls: btn.className};
        }
    """
    for attempt in range(10):
        state = page.evaluate(find_js)
        if state and state.get("found") and not state.get("disabled"):
            break
        if attempt == 0:
            logger.info("Accept button scan: %s", state)
        else:
            logger.info("Accept button not ready (attempt %d/10): found=%s", attempt + 1, state.get("found"))
        time.sleep(0.5)

    clicked = page.evaluate("""
        () => {
            const btn = [...document.querySelectorAll('button')].find(b =>
                (b.innerText || '').trim().toLowerCase().startsWith('accept') &&
                !b.classList.contains('ng-hide') &&
                window.getComputedStyle(b).display !== 'none' &&
                window.getComputedStyle(b).visibility !== 'hidden'
            );
            if (!btn) return {found: false};
            btn.scrollIntoView({behavior: 'instant', block: 'center'});
            btn.click();
            return {found: true, disabled: btn.disabled, cls: btn.className};
        }
    """)
    logger.info("Accept click result: %s", clicked)
    if not clicked or not clicked.get("found"):
        raise RuntimeError("Accept button not found on allocated orders page.")
    time.sleep(3)
    time.sleep(5)  # Accept triggers a server-side status update, not a new page load
    logger.info("ACCEPT clicked.")


def _click_branding_challan(page) -> Path:
    """
    Click BRANDING CHALLAN and save the challan PDF.

    FnP uses window.open() → the challan renders in a NEW TAB at /courierPrintChallans.
    We capture the popup tab and save via page.pdf() (works headless).
    Headed debug runs: page.pdf() is unsupported; a descriptive error is raised.

    If the new tab shows "Failed to load PDF document", orders were not selected —
    the table did not load before the button was clicked.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    challan_btn = None
    for sel in [
        "button:has-text('BRANDING CHALLAN')",
        "a:has-text('BRANDING CHALLAN')",
        "[class*='branding']",
    ]:
        el = page.locator(sel).first
        if el.count() and el.is_visible():
            challan_btn = el
            break

    if challan_btn is None:
        raise RuntimeError(
            "BRANDING CHALLAN button not found. "
            "Run with --headed to debug. Check if orders are selected."
        )

    today_str = date.today().strftime("%Y%m%d")
    run_time  = time.strftime("%H%M")
    dest      = DOWNLOAD_DIR / f"fnp_challan_{today_str}_{run_time}.pdf"

    # Normal case (orders selected): BRANDING CHALLAN triggers a direct file download.
    # Error case (nothing selected): button opens /courierPrintChallans in a new tab.
    # Try download first; if it times out, check for a popup tab (error path).
    logger.info("Clicking BRANDING CHALLAN — waiting for direct download (30s)...")
    try:
        with page.expect_download(timeout=30_000) as dl:
            challan_btn.click()
        download = dl.value
        if download.failure():
            raise RuntimeError(f"Download failed: {download.failure()}")
        filename = download.suggested_filename or dest.name
        dest = DOWNLOAD_DIR / filename
        download.save_as(str(dest))
        logger.info("Challan saved: %s (%d bytes)", dest, dest.stat().st_size)
        return dest

    except PWTimeout:
        # Download didn't fire — the portal may have opened a new tab (error path).
        # Check if a popup was opened (no re-click needed — button was already clicked).
        logger.warning("Download did not fire in 30s — checking for error popup tab...")
        pages_after = page.context.pages
        challan_page = next(
            (p for p in pages_after if "courierPrint" in p.url or "PrintChallan" in p.url),
            None,
        )
        if challan_page:
            challan_page.wait_for_load_state("domcontentloaded", timeout=10_000)
            cur_url = challan_page.url
            challan_page.close()
            raise RuntimeError(
                f"BRANDING CHALLAN opened an error tab ({cur_url}) instead of downloading. "
                "Orders were likely not selected — portal table rows did not load. "
                "Check 'No table row selector matched' warnings above."
            )
        raise RuntimeError(
            "BRANDING CHALLAN did not trigger a download after 30s and no error tab found. "
            "Orders may not have been selected — check table loading warnings above."
        )


# ── Order extraction + DB recording ───────────────────────────────────────────

def _read_order_rows(page) -> list[dict]:
    """
    Scrape order rows from the FnP 'Orders to be shipped' list page.
    Returns list of {order_no, sku_raw, qty, order_date, city, cells}.
    order_date is a YYYY-MM-DD string if found, else None.
    city is the first alpha-only cell that looks like a place name, else None.
    Logs all cells to help debug extraction on first run.
    Returns [] on any failure — never raises.
    """
    try:
        # Angular fetches order data via XHR after load — wait for at least one row.
        # FnP may use non-standard table structure (no <tbody>) so try multiple selectors.
        _waited = False
        for _wait_sel in ["tbody tr", "table tr", "[ng-repeat]", "tr td", ".grid-body"]:
            try:
                page.wait_for_selector(_wait_sel, timeout=5_000)
                time.sleep(1)
                _waited = True
                logger.info("Table rows found via selector '%s'.", _wait_sel)
                break
            except PWTimeout:
                continue
        if not _waited:
            logger.warning("No table row selector matched after 25s — proceeding anyway. "
                           "DOM structure dump follows.")
            dom_debug = page.evaluate("""
                () => ({
                    tables:    document.querySelectorAll('table').length,
                    tbodys:    document.querySelectorAll('tbody').length,
                    trs:       document.querySelectorAll('tr').length,
                    tds:       document.querySelectorAll('td').length,
                    ngRepeats: document.querySelectorAll('[ng-repeat]').length,
                    liItems:   document.querySelectorAll('li').length,
                    divRows:   document.querySelectorAll('[class*="row"]').length,
                    bodyHtml:  document.body.innerHTML.substring(0, 2000),
                })
            """)
            logger.info("DOM debug: tables=%s tbodys=%s trs=%s tds=%s ngRepeats=%s "
                        "liItems=%s divRows=%s",
                        dom_debug.get('tables'), dom_debug.get('tbodys'),
                        dom_debug.get('trs'), dom_debug.get('tds'),
                        dom_debug.get('ngRepeats'), dom_debug.get('liItems'),
                        dom_debug.get('divRows'))
            logger.info("Body HTML (first 2000 chars): %s", dom_debug.get('bodyHtml', ''))

        rows = page.evaluate(r"""
            () => {
                const MONTHS = {
                    jan:'01', feb:'02', mar:'03', apr:'04', may:'05', jun:'06',
                    jul:'07', aug:'08', sep:'09', oct:'10', nov:'11', dec:'12'
                };

                function parseDate(cell) {
                    // DD-MM-YYYY or DD/MM/YYYY
                    let m = cell.match(/\b(\d{2})[-\/](\d{2})[-\/](\d{4})\b/);
                    if (m) return `${m[3]}-${m[2]}-${m[1]}`;
                    // YYYY-MM-DD
                    m = cell.match(/\b(\d{4})-(\d{2})-(\d{2})\b/);
                    if (m) return m[0];
                    // "18 May 2026" or "18-May-2026"
                    m = cell.match(/\b(\d{1,2})[\s\-]([A-Za-z]{3,9})[\s\-](\d{4})\b/);
                    if (m) {
                        const mo = MONTHS[m[2].toLowerCase().substring(0, 3)];
                        if (mo) return `${m[3]}-${mo}-${m[1].padStart(2, '0')}`;
                    }
                    return null;
                }

                // Words that appear in status/action columns — skip these for city
                const SKIP_RE = /^(pending|active|shipped|delivered|cancelled|accept|ship|processing|branding|standard|express|online|payment|cod|prepaid|n\/a|na|yes|no)$/i;

                function extractCity(cells, orderNo) {
                    for (const cell of cells) {
                        if (!cell || cell.length < 2 || cell.length > 50) continue;
                        if (cell === orderNo) continue;
                        if (/^\d+$/.test(cell)) continue;           // pure number
                        if (/TCB\d{3}/i.test(cell)) continue;       // SKU code
                        if (/\d{2}[-\/]\d{2}[-\/]\d{4}/.test(cell)) continue; // date
                        if (/\d{4}-\d{2}-\d{2}/.test(cell)) continue;
                        if (SKIP_RE.test(cell.trim())) continue;
                        // City names are alphabetic (may include spaces, hyphens, dots)
                        if (/^[A-Za-z][A-Za-z\s\-\.]*$/.test(cell) && cell.length >= 3) {
                            return cell;
                        }
                    }
                    return null;
                }

                // Collect candidate <tr> elements.
                // FnP uses ng-repeat on <tr> directly inside <table> (no explicit <tbody>).
                // querySelectorAll('table tr') finds those; 'tbody tr' finds standard tables.
                // Deduplicate via a Set so tbody rows aren't processed twice.
                const seenTrs = new Set();
                const trList = [];
                document.querySelectorAll('tbody tr, table tr').forEach(tr => {
                    if (!seenTrs.has(tr)) { seenTrs.add(tr); trList.push(tr); }
                });

                const orders = [];
                trList.forEach(tr => {
                        const cells = [...tr.querySelectorAll('td')].map(td =>
                            (td.innerText || td.textContent || '').replace(/\s+/g, ' ').trim()
                        );
                        if (cells.length < 2) return;
                        const rowText = cells.join('|');
                        const orderNoMatch = rowText.match(/\b(\d{10})\b/);
                        if (!orderNoMatch) return;

                        const skuMatch = rowText.match(/\b(TCB\d{3})\b/i);

                        let qty = 1;
                        for (const cell of cells) {
                            const n = parseInt(cell, 10);
                            if (!isNaN(n) && n >= 1 && n <= 50 && cell.trim() === String(n)) {
                                qty = n;
                                break;
                            }
                        }

                        let orderDate = null;
                        for (const cell of cells) {
                            orderDate = parseDate(cell);
                            if (orderDate) break;
                        }

                        const city = extractCity(cells, orderNoMatch[1]);

                        orders.push({
                            order_no:   orderNoMatch[1],
                            sku_raw:    skuMatch ? skuMatch[1].toUpperCase() : null,
                            qty:        qty,
                            order_date: orderDate,
                            city:       city,
                            cells:      cells,
                        });
                });
                return orders;
            }
        """)
        logger.info("Order row extraction: %d row(s) found.", len(rows))
        for row in rows:
            logger.info(
                "  Row — order_no=%s sku_raw=%s qty=%d order_date=%s city=%s cells=%s",
                row.get("order_no"), row.get("sku_raw"), row.get("qty", 1),
                row.get("order_date"), row.get("city"), row.get("cells", []),
            )
        return rows
    except Exception as exc:
        logger.warning("_read_order_rows failed: %s", exc)
        return []


def _parse_challan_pdf(pdf_path: Path) -> list[dict]:
    """
    Extract order details from a downloaded FnP branding challan PDF.
    Returns one dict per page (each page = one order):
      {order_no, sku_raw, qty, order_date (date|None), city (str|None)}

    Patterns confirmed on real challans:
      Order No   : 7267211901            → 10-digit
      Order Date : 19-05-2026            → DD-MM-YYYY
      SKU        : GIFTS-TCB003_OP_NB25  → TCBxxx embedded
      City       : last city-like word before 6-digit pincode in address
    """
    import pdfplumber
    import re as _re
    from datetime import datetime as _dt

    results: list[dict] = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""

                m = _re.search(r'Order No\s*:\s*(\d{10})', text)
                if not m:
                    logger.warning("PDF page %d: no Order No found — skipping.", page_num)
                    continue
                order_no = m.group(1)

                m = _re.search(r'Order Date\s*:\s*(\d{2}-\d{2}-\d{4})', text)
                order_date = None
                if m:
                    try:
                        order_date = _dt.strptime(m.group(1), "%d-%m-%Y").date()
                    except ValueError:
                        logger.warning("PDF page %d: could not parse date %r", page_num, m.group(1))

                # TCB SKU: no trailing \b — "GIFTS-TCB003_OP_NB25" has _ after digits (word char)
                m = _re.search(r'\bTCB(\d{3})', text, _re.IGNORECASE)
                sku_raw = f"TCB{m.group(1).upper()}" if m else None

                # City: last city-like word before a 6-digit Indian pincode.
                # Pattern 1: standard "City, - PINCODE" on same line.
                city_raw = None
                city_matches = _re.findall(
                    r'([A-Za-z][A-Za-z\s]{1,25}),\s*[-–]?\s*\d{6}', text
                )
                if city_matches:
                    city_raw = city_matches[-1].strip()
                else:
                    # Pattern 2 (PDF column-merge fallback): pincode starts a new line.
                    # Scan backwards from that line start to find the last alpha-only token.
                    pm = _re.search(r'(?:^|\n)(\d{6})\b', text)
                    if pm:
                        before = text[:pm.start()].strip()
                        for token in reversed(_re.split(r'[,\n]+', before)):
                            token = token.strip()
                            if _re.match(r'^[A-Za-z][A-Za-z ]+$', token) and 3 <= len(token) <= 30:
                                city_raw = token
                                break

                logger.info(
                    "PDF page %d: order_no=%s sku=%s date=%s city=%s",
                    page_num, order_no, sku_raw, order_date, city_raw,
                )
                results.append({
                    "order_no":   order_no,
                    "sku_raw":    sku_raw,
                    "qty":        1,
                    "order_date": order_date,
                    "city":       city_raw,
                })
    except Exception as exc:
        logger.error("_parse_challan_pdf failed on %s: %s", pdf_path.name, exc)
    return results


def _record_fnp_order(order_no: str, sku_id: str, qty: int,
                      city: str | None, order_date: date, dry_run: bool) -> str:
    """
    Write one FnP order to the orders table + decrement OWN_WH inventory.
    Checks for duplicates first (safe to call on retry runs).
    Returns: 'recorded', 'already_recorded', 'dry-run', or 'failed: <reason>'.
    Never raises.
    """
    if dry_run:
        return "dry-run"
    try:
        from tcb.db import get_client
        from tcb.inventory import record_dropship_sale
        from ingest.utils import get_sku_sp_at_date

        db = get_client()
        existing = (
            db.table("orders")
            .select("order_id")
            .eq("channel_id", 5)
            .eq("platform_order_id", order_no)
            .eq("sku_id", sku_id)
            .execute()
        )
        if existing.data:
            logger.info("FnP %s/%s already in DB — skipping.", order_no, sku_id)
            return "already_recorded"

        sp = get_sku_sp_at_date(sku_id, order_date)
        if sp is None:
            return f"failed: no SP for {sku_id}"

        record_dropship_sale(
            sku_id=sku_id,
            qty=qty,
            channel_id=5,
            selling_price=sp,
            order_date=order_date,
            platform_order_id=order_no,
            city=city,
            notes="fnp_scraper",
            created_by="vignesh",
        )
        logger.info("FnP %s/%s recorded to DB (date=%s city=%s SP=%.0f).",
                    order_no, sku_id, order_date, city, sp)
        return "recorded"
    except Exception as exc:
        logger.error("Failed to record FnP %s/%s: %s", order_no, sku_id, exc)
        return f"failed: {exc}"


# ── Main pipeline ──────────────────────────────────────────────────────────────

def _acquire_lock() -> bool:
    """Return True if this process owns the lock. False if another instance is running."""
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True,
            )
            if str(pid) in result.stdout:
                return False  # stale PID is still alive
        except Exception:
            pass
        LOCK_FILE.unlink(missing_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def _release_lock() -> None:
    LOCK_FILE.unlink(missing_ok=True)


def run(dry_run: bool = False, headed: bool = False) -> dict:
    """
    Full FnP processing pipeline. Returns result dict:
      allocated_accepted  int   — total orders accepted across all date columns
      ship_count          int   — total orders processed from "Orders to be shipped"
      challan_downloaded  bool
      emailed             bool
      skipped             bool  — True if no orders found at all

    Retries once on PWTimeout — the FnP portal is intermittently slow (30–60+ s
    load times), causing transient navigation timeouts that resolve on a retry.
    """
    if not _acquire_lock():
        logger.warning("Another FnP scraper instance is running — exiting to avoid clash.")
        return {
            "allocated_accepted": 0, "ship_count": 0,
            "challan_downloaded": False, "emailed": False,
            "skipped": True, "order_details": [],
            "lock_skipped": True,
        }
    try:
        for attempt in range(1, 3):
            try:
                return _run_once(dry_run=dry_run, headed=headed)
            except PWTimeout as exc:
                if attempt == 2:
                    raise
                logger.warning("Attempt %d/2 timed out — retrying in 20s...", attempt)
                time.sleep(20)
        raise RuntimeError("unreachable")  # satisfies type checkers
    finally:
        _release_lock()


def _run_once(dry_run: bool = False, headed: bool = False) -> dict:
    """Single attempt of the FnP pipeline (called by run() with retry wrapper)."""
    result: dict = {
        "allocated_accepted": 0,
        "ship_count": 0,
        "challan_downloaded": False,
        "emailed": False,
        "skipped": False,
        "order_details": [],
    }

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    pdf_paths: list[Path] = []
    raw_order_rows: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not headed,
            slow_mo=300 if headed else 50,
        )
        ctx  = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        try:
            # ── Step 1: Login ──────────────────────────────────────────────────
            _login(page)

            # ── Step 2: Allocated orders — ALL non-zero columns ────────────────
            # TODAY, TOMORROW, FUTURE can each have orders simultaneously
            alloc_cols = _scan_section(page, "Allocated")
            logger.info("Allocated: %d non-zero column(s) found.", len(alloc_cols))

            for col_idx, col_count in alloc_cols:
                logger.info("Allocated col[%d]: %d order(s). Selecting + accepting...",
                            col_idx, col_count)
                _click_column(page, "Allocated", col_idx)
                count = _read_order_count(page)
                _select_all(page)
                _click_accept(page)
                result["allocated_accepted"] += count if count > 0 else col_count
                _return_to_dashboard(page)

            # ── Step 3: Orders to be shipped — ALL non-zero columns ────────────
            ship_cols = _scan_section(page, "Orders to be shipped")
            logger.info("Orders to be shipped: %d non-zero column(s) found.", len(ship_cols))

            if not ship_cols and result["allocated_accepted"] == 0:
                logger.info("No orders anywhere — nothing to process.")
                result["skipped"] = True
                browser.close()
                return result

            if not ship_cols and result["allocated_accepted"] > 0:
                # Portal takes time to move accepted orders into "Orders to be shipped".
                # Retry up to 4 times with 15s gaps (total up to ~60s).
                for attempt in range(1, 5):
                    logger.warning(
                        "Accepted %d order(s) but 'Orders to be shipped' shows 0. "
                        "Waiting 15s before retry %d/4...",
                        result["allocated_accepted"], attempt,
                    )
                    time.sleep(15)
                    page.reload(wait_until="load", timeout=60_000)
                    time.sleep(3)
                    ship_cols = _scan_section(page, "Orders to be shipped")
                    if ship_cols:
                        break

                if not ship_cols:
                    logger.warning(
                        "Orders were accepted but challan not yet available after ~60s. "
                        "Likely past FnP's evening cutoff — challan will appear in tomorrow's run."
                    )
                    browser.close()
                    return result

            total_ship = 0
            for col_idx, col_count in ship_cols:
                logger.info("Orders to be shipped col[%d]: %d order(s). Downloading challan...",
                            col_idx, col_count)
                _click_column(page, "Orders to be shipped", col_idx)
                count = _read_order_count(page)
                total_ship += count if count > 0 else col_count
                _select_all(page)
                pdf = _click_branding_challan(page)
                pdf_paths.append(pdf)
                result["challan_downloaded"] = True
                # Parse order details from the downloaded challan PDF (authoritative source).
                # This replaces portal table scraping — challan has correct date, city, SKU.
                raw_order_rows.extend(_parse_challan_pdf(pdf))
                _return_to_dashboard(page)

            result["ship_count"] = total_ship

        except Exception:
            logger.exception("FnP scraper encountered an error.")
            try:
                browser.close()
            except Exception:
                pass
            raise

        browser.close()

    # ── Step 4: Record orders to DB ───────────────────────────────────────────
    # raw_order_rows now comes from _parse_challan_pdf() — order_date is already
    # a date object (or None), city is a raw string ready for normalise_city().
    from ingest.utils import normalise_city

    order_details: list[dict] = []
    for row in raw_order_rows:
        order_no   = row.get("order_no", "")
        sku_raw    = row.get("sku_raw")
        qty        = row.get("qty", 1)
        city       = normalise_city(row.get("city"))
        order_date = row.get("order_date") or date.today()

        if row.get("order_date") is None:
            logger.warning("No order_date in challan for %s — using today.", order_no)

        sku_id = _parse_sku(sku_raw)
        if sku_id:
            db_status = _record_fnp_order(order_no, sku_id, qty, city, order_date, dry_run)
        else:
            logger.warning("Could not resolve SKU for FnP order %s (raw=%r) — DB write skipped.",
                           order_no, sku_raw)
            db_status = f"unknown_sku ({sku_raw})"
        order_details.append({
            "order_no":   order_no,
            "sku_id":     sku_id or f"?({sku_raw})",
            "qty":        qty,
            "order_date": str(order_date),
            "city":       city or "—",
            "db_status":  db_status,
        })
    result["order_details"] = order_details

    # ── Step 5: Email all PDFs in one message ─────────────────────────────────
    if not pdf_paths:
        return result

    from automation.email_sender import send_with_attachments

    recipients = [
        r for r in [
            os.environ.get("EMAIL_HIMANSHU", "").strip(),
            os.environ.get("EMAIL_DILWAR", "").strip(),
        ]
        if r
    ]

    if not recipients:
        logger.warning("No email recipients set. Add EMAIL_HIMANSHU / EMAIL_DILWAR to .env")
    else:
        n     = result["ship_count"] if result["ship_count"] > 0 else result["allocated_accepted"]
        today = date.today().strftime("%d-%b-%Y")
        subject = f"FnP Branding Challan — {today} ({n} order(s))"

        if order_details:
            header  = f"  {'Order No':<14} {'SKU':<8} {'Qty':<5} {'Date':<12} {'City':<18} DB Status"
            divider = "  " + "-" * 70
            rows_txt = "\n".join(
                f"  {od['order_no']:<14} {od['sku_id']:<8} {od['qty']:<5} "
                f"{od['order_date']:<12} {od['city']:<18} {od['db_status']}"
                for od in order_details
            )
            db_block = f"{header}\n{divider}\n{rows_txt}"
        else:
            db_block = "  (Order details could not be parsed from portal — check log)"

        body = (
            f"Hi,\n\n"
            f"FnP order(s) processed on {today}.\n\n"
            f"Orders recorded to DB:\n"
            f"{db_block}\n\n"
            f"If anything above looks wrong, fix it in Warehouse App → Ship Out "
            f"before end of day.\n\n"
            f"Challan attached — print and pack as per challan.\n\n"
            f"— Vignesh (automated)\n"
        )
        send_with_attachments(subject, body, recipients, pdf_paths, dry_run=dry_run)
        result["emailed"] = not dry_run

    return result


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FnP order processor")
    parser.add_argument("--dry-run", action="store_true",
                        help="Download challan but do NOT send email")
    parser.add_argument("--headed", action="store_true",
                        help="Show browser window — use this for first-run debugging")
    args = parser.parse_args()

    os.environ.setdefault("TCB_ENV", "prod")

    logger.info("=" * 55)
    logger.info("FnP scraper started — %s", date.today().isoformat())
    logger.info("=" * 55)

    try:
        result = run(dry_run=args.dry_run, headed=args.headed)
        if result.get("lock_skipped"):
            print("Another FnP scraper instance is already running — exiting.")
            sys.exit(0)
        if result["skipped"]:
            print("No FnP orders found — nothing to do.")
        else:
            print(
                f"FnP: allocated_accepted={result['allocated_accepted']} | "
                f"ship_count={result['ship_count']} | "
                f"challan={'downloaded' if result['challan_downloaded'] else 'N/A'} | "
                f"email={'sent' if result['emailed'] else ('dry-run' if args.dry_run else 'not sent')}"
            )
    except Exception as e:
        logger.error("FAILED: %s", e)
        try:
            from automation.email_sender import send_alert
            send_alert(
                subject=f"⚠️ FnP Scraper — Failed ({date.today().strftime('%d-%b')})",
                body=(
                    f"Error: {e}\n\n"
                    f"Log: automation/logs/fnp_{date.today().strftime('%Y%m%d')}.log"
                ),
            )
        except Exception:
            pass
        print(f"ERROR: {e}")
        sys.exit(1)
