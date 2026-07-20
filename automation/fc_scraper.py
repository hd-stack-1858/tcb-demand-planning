"""
First Cry order processor.
Runs at 11:00, 20:00 IST via Windows Task Scheduler.

Flow per run:
  1. Load saved session (from fc_auth.py) — no reCAPTCHA needed
  2. Navigate to Pending Orders
  3. For each pending order (one by one):
       a. Click gear icon -> new tab opens (B2C Configure Order)
       b. Check header checkbox (select all items)
       c. Set Status -> "Accepted"
       d. Set Select Shipment -> "New Shipment"
       e. Click "Send Item in Po"
       f. Fill Weight / Select Box / Length / Breadth / Height from fc_dimensions.json
       g. Click Save
       h. Handle "No Records Found" popup if present (click OK)
       i. Click "Print Invoice" -> download PDF
       j. Click "Print Address" -> download PDF
       k. Close configure tab
  4. Email all downloaded PDFs (Invoice + Packing Slip for each order) to Himanshu + Dilwar + Meet

Self-healing: orders already processed disappear from Pending Orders, so re-running
the same schedule slot is always safe.

Required .env vars:
  FC_USERNAME       vendor portal email
  FC_PASSWORD       vendor portal password (used only if session expired)
  SMTP_SENDER       sending email (hd@thecradlebox.com)
  SMTP_PASSWORD     Gmail App Password
  EMAIL_HIMANSHU    Himanshu's email
  EMAIL_DILWAR      Dilwar's email
  EMAIL_MEET        Meet's email

Setup:
  1. Run `python automation/fc_auth.py` once to save session
  2. Fill dimensions in `automation/fc_dimensions.json` for all SKUs
  3. Set up Task Scheduler: python automation/fc_scraper.py at 11:00 and 20:00 IST

Usage:
  python automation/fc_scraper.py              # normal run
  python automation/fc_scraper.py --dry-run    # process orders, skip email
  python automation/fc_scraper.py --headed     # show browser window (debug)

Logs: automation/logs/fc_YYYYMMDD.log
Session expiry: if session expires, scraper exits with code 2 and logs a warning.
  Re-run `python automation/fc_auth.py` to refresh the session.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_DIR  = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"fc_{date.today().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(str(log_file), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

PORTAL_URL        = "https://in-vcom.brainbees.com/#/"
PENDING_ORDERS_URL = "https://in-vcom.brainbees.com/#/ordermanagement/pendingorders"
SESSION_FILE      = Path(__file__).parent.parent / ".fc_session" / "state.json"
DOWNLOAD_DIR = Path(__file__).parent.parent / "data" / "firstcry" / "auto"  # scraper writes invoices/packing slips here
DIMS_FILE    = Path(__file__).parent / "fc_dimensions.json"


class FCSessionExpired(Exception):
    pass


# ── Dimensions config ──────────────────────────────────────────────────────────

def _load_dimensions() -> dict:
    with open(DIMS_FILE, encoding="utf-8") as f:
        dims = json.load(f)
    # Remove instruction key
    return {k: v for k, v in dims.items() if not k.startswith("_")}


def _get_dims(sku_code: str) -> dict:
    dims = _load_dimensions()
    sku = sku_code.strip().upper()
    if sku not in dims:
        raise ValueError(
            f"No dimensions found for SKU '{sku}'. "
            f"Add it to automation/fc_dimensions.json"
        )
    d = dims[sku]
    if d["weight_kg"] == 0 or d["length_cm"] == 0:
        raise ValueError(
            f"Dimensions for '{sku}' are all zeros — fill in automation/fc_dimensions.json first."
        )
    return d


# ── Session check ──────────────────────────────────────────────────────────────

def _is_logged_in(page) -> bool:
    """Returns True if the page loaded the pending orders section (not the login page)."""
    try:
        return (
            page.locator("text=Pending Orders").count() > 0
            or page.locator("text=Pending Orders [").count() > 0
        )
    except Exception:
        return False


# ── Navigation ─────────────────────────────────────────────────────────────────

def _navigate_to_pending_orders(page) -> None:
    """Navigate directly to the pending orders page using the known URL."""
    try:
        page.goto(PENDING_ORDERS_URL, wait_until="domcontentloaded", timeout=30_000)
    except Exception:
        pass  # "No pending orders" popup can prevent networkidle — page still loaded
    time.sleep(3)
    logger.info("Navigated to Pending Orders. URL: %s", page.url)


def _get_pending_count(page) -> int:
    """Read the count from 'Pending Orders [B2C: N & B2B: M]' heading."""
    try:
        heading = page.locator("text=Pending Orders").first.inner_text()
        import re
        # Format: "Pending Orders [ B2C : 1 & B2B : 0 ]"
        b2c = re.search(r'B2C\s*:\s*(\d+)', heading)
        count = int(b2c.group(1)) if b2c else -1
        logger.info("Pending Orders heading: '%s' -> B2C count: %d", heading.strip(), count)
        return count
    except Exception as exc:
        logger.warning("Could not read pending count: %s", exc)
        return -1


# ── Row-level parsing helpers ─────────────────────────────────────────────────

def _parse_fc_order_date(raw: str) -> date | None:
    """Parse '19-05-2026 19:45:55' or '19-05-2026' -> date. Returns None on failure."""
    try:
        return datetime.strptime(raw.strip(), "%d-%m-%Y %H:%M:%S").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(raw.strip().split()[0], "%d-%m-%Y").date()
    except Exception:
        return None


def _parse_pincode_from_address(address: str) -> str | None:
    """
    Extract 6-digit pincode from FC shipping address.
    Pincode is always the last numeric field — much more reliable than
    position-based city extraction which breaks on varied address formats.
    """
    import re as _re
    m = _re.search(r'\b(\d{6})\b', address)
    return m.group(1) if m else None


# ── DB recording ──────────────────────────────────────────────────────────────

def _record_fc_order(order_id: str, sku_id: str, qty: int,
                     city: str | None, state: str | None,
                     order_date: date | None, dry_run: bool) -> str:
    """
    Write one FC order to the orders table + decrement OWN_WH inventory.
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
            .eq("channel_id", 6)
            .eq("platform_order_id", order_id)
            .eq("sku_id", sku_id)
            .execute()
        )
        if existing.data:
            logger.info("FC %s/%s already in DB — skipping.", order_id, sku_id)
            return "already_recorded"

        sp = get_sku_sp_at_date(sku_id, date.today())
        if sp is None:
            return f"failed: no SP for {sku_id}"

        record_dropship_sale(
            sku_id=sku_id,
            qty=qty,
            channel_id=6,
            selling_price=sp,
            order_date=order_date or date.today(),
            platform_order_id=order_id,
            city=city,
            state=state,
            notes="fc_scraper",
            created_by="vignesh",
        )
        logger.info("FC %s/%s recorded to DB (SP=%.0f, date=%s).",
                    order_id, sku_id, sp, order_date or date.today())
        return "recorded"
    except Exception as exc:
        logger.error("Failed to record FC %s/%s: %s", order_id, sku_id, exc)
        return f"failed: {exc}"


# ── Per-order processing ───────────────────────────────────────────────────────

def _dismiss_blocking_modals(tab, label: str = "") -> None:
    """
    Wait for any active loading overlay to clear, then dismiss any residual
    dialog modals that would intercept pointer events.  Call this before
    clicking any element that may be blocked by FC portal overlays.
    """
    # 1. Wait for loading overlay to finish (FC shows a spinner after Save/OK clicks)
    try:
        tab.wait_for_selector(".loading-overlay.is-active", state="hidden", timeout=15_000)
    except Exception:
        pass  # If selector never appears, nothing to wait for

    # 2. Dismiss any residual dialog modal
    for _ in range(4):
        try:
            modal = tab.locator(".dialog.modal.is-active")
            if not modal.count():
                break
            ok_btn = modal.locator("button").filter(has_text="OK").first
            if ok_btn.count():
                logger.warning("%s: blocking dialog modal found — clicking OK to clear.", label)
                ok_btn.click()
                time.sleep(1.5)
            else:
                logger.warning("%s: blocking modal has no OK button — continuing anyway.", label)
                break
        except Exception:
            break


def _download_pdf_link(tab, link_text: str, dest: Path) -> Path:
    """
    Click a PDF link (e.g. "Print Invoice") and save the result to dest.
    Handles both direct-download and new-tab-opens cases.
    """
    # Clear any loading overlay or blocking modal before attempting the click
    _dismiss_blocking_modals(tab, label=f"'{link_text}' download")

    link = tab.get_by_text(link_text, exact=True).first
    if not link.count():
        link = tab.locator(f"a:has-text('{link_text}')").first
    link.wait_for(timeout=10_000)

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Try direct download first
    try:
        with tab.expect_download(timeout=20_000) as dl:
            link.click()
        download = dl.value
        if download.failure():
            raise RuntimeError(f"Download failed: {download.failure()}")
        download.save_as(str(dest))
        logger.info("Downloaded '%s' -> %s (%d bytes)", link_text, dest.name, dest.stat().st_size)
        return dest
    except Exception:
        pass

    # Fallback: link opens a new tab containing the PDF
    try:
        with tab.context.expect_page() as new_page_info:
            link.click()
        pdf_tab = new_page_info.value
        pdf_tab.wait_for_load_state("domcontentloaded", timeout=15_000)
        time.sleep(2)
        pdf_url = pdf_tab.url
        pdf_tab.close()

        # Download via requests using the same session cookies
        import requests
        cookies = {c["name"]: c["value"] for c in tab.context.cookies()}
        resp = requests.get(pdf_url, cookies=cookies, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        logger.info("Downloaded '%s' via new-tab -> %s (%d bytes)", link_text, dest.name, len(resp.content))
        return dest
    except Exception as exc:
        raise RuntimeError(f"Could not download '{link_text}': {exc}") from exc


def _process_one_order(context, gear_icon, order_id: str) -> tuple[list[Path], dict]:
    """
    Open the Configure Order tab for one order, fill the form, download PDFs.

    Returns ([invoice_pdf, packing_slip_pdf], {sku_id, qty, city}).
    """
    today_str = date.today().strftime("%Y%m%d")
    run_time  = time.strftime("%H%M")

    # ── Open configure tab ────────────────────────────────────────────────────
    logger.info("Order %s: clicking gear icon...", order_id)
    with context.expect_page() as new_page_info:
        gear_icon.click()
    tab = new_page_info.value
    tab.wait_for_load_state("networkidle", timeout=30_000)
    time.sleep(2)
    logger.info("Order %s: configure tab opened. URL: %s", order_id, tab.url)

    try:
        # ── Read all line items (SKU + qty per row) ──────────────────────────────
        # Wait for the table to render before scanning
        tab.wait_for_selector("table td", timeout=15_000)
        time.sleep(1)

        import re

        # Scan row-by-row so we can associate qty with its SKU
        order_items: list[dict] = []  # [{sku_id, qty}, ...]
        body_rows = tab.locator("tbody tr")
        total_cells = tab.locator("table td")
        logger.info("Order %s: scanning %d rows / %d cells for TCB line items...",
                    order_id, body_rows.count(), total_cells.count())

        for row_i in range(body_rows.count()):
            row_el = body_rows.nth(row_i)
            cells = row_el.locator("td")
            cell_count = cells.count()
            row_sku = ""
            for ci in range(cell_count):
                try:
                    cell_text = cells.nth(ci).inner_text().strip()
                    if re.match(r'^TCB\d+$', cell_text, re.IGNORECASE):
                        row_sku = cell_text.upper()
                        # Look for qty in the next few cells after the SKU
                        row_qty = 1
                        for qi in range(ci + 1, min(ci + 6, cell_count)):
                            qt = cells.nth(qi).inner_text().strip()
                            if qt.isdigit() and 1 <= int(qt) <= 50:
                                row_qty = int(qt)
                                break
                        order_items.append({"sku_id": row_sku, "qty": row_qty})
                        logger.info("Order %s: row[%d] -> sku=%s qty=%d",
                                    order_id, row_i, row_sku, row_qty)
                        break  # one SKU per row
                except Exception:
                    continue

        if not order_items:
            # Fallback: scan all cells flat for any TCB code
            for i in range(total_cells.count()):
                try:
                    cell_text = total_cells.nth(i).inner_text().strip()
                    if re.match(r'^TCB\d+$', cell_text, re.IGNORECASE):
                        order_items.append({"sku_id": cell_text.upper(), "qty": 1})
                        logger.warning("Order %s: fallback flat-scan found %s (qty assumed 1)",
                                       order_id, cell_text.upper())
                except Exception:
                    continue

        if not order_items:
            all_texts = []
            for i in range(min(total_cells.count(), 30)):
                try:
                    all_texts.append(f"[{i}]='{total_cells.nth(i).inner_text().strip()}'")
                except Exception:
                    pass
            logger.error("Order %s: no TCB SKU found. First 30 cells: %s",
                         order_id, ", ".join(all_texts))
            raise ValueError(f"Could not read any SKU for order {order_id}")

        # Group by SKU: FC's Configure Order table sometimes renders multiple units of
        # the same SKU as separate rows (each parsed as qty=1) instead of one row with
        # qty=N. Without this, each extra row is a duplicate DB write attempt that gets
        # silently dropped as "already_recorded" — undercounting the real quantity.
        grouped: dict[str, int] = {}
        for it in order_items:
            grouped[it["sku_id"]] = grouped.get(it["sku_id"], 0) + it["qty"]
        order_items = [{"sku_id": sku, "qty": qty} for sku, qty in grouped.items()]

        # Compute shipment dims: sum weight across all items × qty, share L/B/H from primary SKU
        primary_sku = order_items[0]["sku_id"]
        primary_dims = _get_dims(primary_sku)
        total_weight = sum(_get_dims(it["sku_id"])["weight_kg"] * it["qty"] for it in order_items)
        dims = {**primary_dims, "weight_kg": round(total_weight, 3)}
        if len(order_items) > 1:
            logger.warning("Order %s: MULTI-ITEM ORDER — %d line items: %s. "
                           "Combined weight=%.3f kg, L/B/H from %s.",
                           order_id, len(order_items), order_items, total_weight, primary_sku)
        logger.info("Order %s: shipment dims=%s", order_id, dims)

        # ── Step 1: Check header checkbox (select all items) ──────────────────
        header_cb = tab.locator("th input[type='checkbox'], thead input[type='checkbox']").first
        if header_cb.count() and header_cb.is_visible():
            header_cb.check()
            time.sleep(0.5)
            logger.info("Order %s: header checkbox checked.", order_id)
        else:
            row_cb = tab.locator("tbody td input[type='checkbox']").first
            row_cb.check()
            time.sleep(0.5)

        # ── Step 2: Set Status -> "Accepted" on EVERY item row ─────────────────
        # tbody-scoped selector avoids catching the "Select Shipment" dropdown below the table.
        # Multi-item orders have one Status <select> per row — all must be Accepted or FC
        # won't generate the PO panel after "Send Item in Po".
        row_status_selects = tab.locator("tbody tr td select")
        n_status = row_status_selects.count()
        if n_status == 0:
            raise RuntimeError(f"Order {order_id}: no Status dropdowns found in table rows.")
        logger.info("Order %s: setting Accepted on %d Status dropdown(s).", order_id, n_status)
        for si in range(n_status):
            try:
                row_status_selects.nth(si).select_option(label="Accepted")
                time.sleep(0.3)
                logger.info("Order %s: Status[%d] -> Accepted.", order_id, si)
            except Exception as exc:
                logger.warning("Order %s: could not set Status[%d]: %s", order_id, si, exc)

        # ── Step 3: Set Select Shipment -> "New Shipment" ──────────────────────
        # "Select Shipment" dropdown is below the table (not inside it)
        shipment_select = tab.locator("select").filter(
            has=tab.locator("option:has-text('New Shipment')")
        ).first
        shipment_select.wait_for(timeout=10_000)
        shipment_select.select_option(label="New Shipment")
        time.sleep(0.5)
        logger.info("Order %s: shipment set to New Shipment.", order_id)

        # ── Step 4: Click "Send Item in Po" ───────────────────────────────────
        send_btn = tab.get_by_role("button", name="Send Item in Po")
        if not send_btn.count():
            send_btn = tab.locator("button:has-text('Send Item in Po')").first
        send_btn.wait_for(timeout=10_000)
        send_btn.click()
        time.sleep(2)
        logger.info("Order %s: 'Send Item in Po' clicked. PO panel should appear.", order_id)

        # ── Step 5: Fill PO panel dimensions ─────────────────────────────────
        # The PO panel appears below with: Weight | Select Box | Length | Breadth | Height
        # IMPORTANT: Select Box MUST be set FIRST — selecting it after filling weight
        # resets the weight field to 0 (portal behaviour).

        # Wait for the PO panel to appear (keyed on "Purchase Order:" text)
        tab.wait_for_selector("text=Purchase Order:", timeout=15_000)
        time.sleep(1)

        # 1. Select Box FIRST — try NonFCPackaging, fall back to Box No 4
        active_select = None
        packaging_mode = "nonfc"

        nonfc_select = tab.locator("select").filter(
            has=tab.locator("option:has-text('NonFCPackaging')")
        ).first
        try:
            nonfc_select.wait_for(timeout=10_000)
            nonfc_select.select_option(label="NonFCPackaging Material")
            active_select = nonfc_select
            logger.info("Order %s: Select Box set to NonFCPackaging Material.", order_id)
        except PWTimeout:
            # NonFCPackaging not available — try Box No 4
            box4_select = tab.locator("select").filter(
                has=tab.locator("option:has-text('Box No 4')")
            ).first
            try:
                box4_select.wait_for(timeout=5_000)
                # Get exact option label from the DOM (guards against label drift)
                box4_label = tab.evaluate("""
                    () => {
                        for (const s of document.querySelectorAll('select')) {
                            const opt = [...s.options].find(o => o.text.trim().startsWith('Box No 4'));
                            if (opt) return opt.text.trim();
                        }
                        return null;
                    }
                """)
                if not box4_label:
                    raise RuntimeError(f"Order {order_id}: Box No 4 option text not found.")
                box4_select.select_option(label=box4_label)
                active_select = box4_select
                packaging_mode = "box4"
                logger.info("Order %s: NonFCPackaging not available — using Box No 4 (%s). "
                            "L/B/H will be skipped (auto-filled by FC).", order_id, box4_label)
            except (PWTimeout, RuntimeError):
                # Neither option found — dump diagnostics before failing
                all_selects = tab.evaluate("""
                    () => [...document.querySelectorAll('select')].map(s => ({
                        id: s.id, name: s.name,
                        options: [...s.options].map(o => o.text.trim())
                    }))
                """)
                logger.error("Order %s: No packaging select found. All selects: %s",
                             order_id, all_selects)
                raise RuntimeError(
                    f"Order {order_id}: no packaging option (NonFCPackaging or Box No 4) found on PO panel."
                )
        time.sleep(0.5)

        # 2–5. Fill Weight / Length / Breadth / Height
        # Strategy: use the Select dropdown as an anchor — find the ancestor element
        # that contains both the dropdown and at least 3 inputs, then fill by position.
        # This is more robust than matching by placeholder (portal uses non-standard names).
        po_container = None
        for xpath_levels in ["xpath=../..", "xpath=../../..", "xpath=../../../.."]:
            candidate = active_select.locator(xpath_levels)
            if candidate.count() and candidate.locator("input").count() >= 1:
                po_container = candidate
                break

        # Which fields to fill depends on packaging choice:
        # NonFCPackaging -> Weight + Length + Breadth + Height
        # Box No 4       -> Weight only (L/B/H auto-filled by FC portal)
        if packaging_mode == "box4":
            dim_values = [("weight_kg", dims["weight_kg"])]
        else:
            dim_values = [
                ("weight_kg",  dims["weight_kg"]),
                ("length_cm",  dims["length_cm"]),
                ("breadth_cm", dims["breadth_cm"]),
                ("height_cm",  dims["height_cm"]),
            ]

        if po_container:
            po_inputs = po_container.locator("input")
            n = po_inputs.count()
            for i in range(n):
                ph = po_inputs.nth(i).get_attribute("placeholder") or ""
                nm = po_inputs.nth(i).get_attribute("name") or ""
                logger.info("Order %s: po_input[%d] placeholder='%s' name='%s'",
                            order_id, i, ph, nm)

            if n < len(dim_values):
                raise RuntimeError(
                    f"Order {order_id}: expected {len(dim_values)} input(s) in PO panel, found {n}."
                )

            for idx, (field, value) in enumerate(dim_values):
                po_inputs.nth(idx).fill(str(value))
                time.sleep(0.2)
                logger.info("Order %s: po_input[%d] (%s) = %s", order_id, idx, field, value)

        else:
            logger.warning("Order %s: PO container not found via anchor — falling back to page-level selectors.", order_id)
            field_selectors_all = [
                ("weight_kg",  "input[placeholder*='weight' i], input[name*='weight' i], input[id*='weight' i]"),
                ("length_cm",  "input[placeholder*='length' i], input[name*='length' i], input[id*='length' i]"),
                ("breadth_cm", "input[placeholder*='breadth' i], input[name*='breadth' i], input[id*='breadth' i]"),
                ("height_cm",  "input[placeholder*='height' i], input[placeholder*=' ht' i], "
                               "input[name*='height' i], input[id*='height' i]"),
            ]
            # Only fill the fields relevant to the current packaging mode
            active_fields = {f for f, _ in dim_values}
            for field, sel in field_selectors_all:
                if field not in active_fields:
                    continue
                inp = tab.locator(sel).first
                if not inp.count():
                    raise RuntimeError(f"Order {order_id}: could not find input for '{field}'.")
                inp.fill(str(dims[field]))
                time.sleep(0.2)
                logger.info("Order %s: filled %s = %s", order_id, field, dims[field])

        if packaging_mode == "box4":
            logger.info("Order %s: dimensions filled — W=%.1f (L/B/H auto-filled by FC).",
                        order_id, dims["weight_kg"])
        else:
            logger.info("Order %s: dimensions filled — W=%.1f L=%s B=%s H=%s",
                        order_id, dims["weight_kg"], dims["length_cm"],
                        dims["breadth_cm"], dims["height_cm"])

        # ── Step 6: Click Save ────────────────────────────────────────────────
        # The page is an Angular SPA — scrollable content is inside a div container,
        # not the window. window.scrollTo does nothing. Use JS scrollIntoView on the
        # element itself, then JS click — bypasses all viewport/visibility issues.

        # Save is an <a class="button ..."> element (Bulma CSS framework),
        # NOT a <button> — so querySelectorAll('button') misses it entirely.
        clicked = tab.evaluate("""
            () => {
                const candidates = [
                    ...document.querySelectorAll('a, input[type="submit"]')
                ];
                const btn = candidates.find(el =>
                    (el.innerText || el.value || '').trim().toLowerCase().includes('save')
                );
                if (!btn) return {found: false, total: candidates.length};
                btn.scrollIntoView({behavior: 'instant', block: 'center'});
                btn.click();
                return {
                    found: true,
                    tag: btn.tagName,
                    cls: btn.className,
                    text: (btn.innerText || btn.value || '').trim(),
                };
            }
        """)
        logger.info("Order %s: Save click result: %s", order_id, clicked)
        if not clicked or not clicked.get("found"):
            raise RuntimeError(f"Order {order_id}: Save <a> element not found in DOM.")
        time.sleep(3)
        logger.info("Order %s: Save clicked.", order_id)

        # ── Step 7: Dismiss ALL modal dialogs (loop — FC can show multiple sequentially) ───
        # "No Records Found" appears on the last order; additional dialogs can follow.
        for _popup_n in range(6):
            try:
                ok_btn = tab.get_by_role("button", name="OK")
                ok_btn.wait_for(timeout=5_000)
                logger.info("Order %s: modal/popup detected (attempt %d) — clicking OK.",
                            order_id, _popup_n + 1)
                ok_btn.click()
                time.sleep(1.5)
            except PWTimeout:
                break  # no more popups

        # ── Step 8: Download PDFs ─────────────────────────────────────────────
        # Wait for "Print Invoice" and "Print Address" links to appear
        tab.wait_for_selector("text=Print Invoice", timeout=15_000)
        time.sleep(1)

        safe_id  = order_id.replace("/", "_")
        invoice_dest = DOWNLOAD_DIR / f"fc_invoice_{safe_id}_{today_str}_{run_time}.pdf"
        address_dest = DOWNLOAD_DIR / f"fc_packing_slip_{safe_id}_{today_str}_{run_time}.pdf"

        invoice_path = _download_pdf_link(tab, "Print Invoice", invoice_dest)
        time.sleep(1)
        address_path = _download_pdf_link(tab, "Print Address", address_dest)

        logger.info("Order %s: PDFs downloaded — %s, %s",
                    order_id, invoice_path.name, address_path.name)

    except Exception:
        logger.exception("Order %s: processing failed.", order_id)
        tab.close()
        raise

    tab.close()
    return [invoice_path, address_path], order_items


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run(dry_run: bool = False, headed: bool = False, no_email: bool = False) -> dict:
    """
    Full FC processing pipeline. Returns result dict:
      orders_processed  int   — number of orders successfully processed
      pdfs_downloaded   int   — total PDF files downloaded
      emailed           bool
      skipped           bool  — True if no pending orders found
    """
    result: dict = {
        "orders_processed": 0,
        "pdfs_downloaded": 0,
        "emailed": False,
        "skipped": False,
        "order_details": [],
    }

    if not SESSION_FILE.exists():
        raise FileNotFoundError(
            f"No saved session at {SESSION_FILE}.\n"
            "Run: python automation/fc_auth.py"
        )

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    all_pdfs: list[Path] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not headed,
            slow_mo=300 if headed else 100,
        )
        ctx  = browser.new_context(
            storage_state=str(SESSION_FILE),
            accept_downloads=True,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        try:
            # ── Load pending orders directly (avoids reCAPTCHA on home page) ──
            logger.info("Loading FC pending orders directly...")
            try:
                page.goto(PENDING_ORDERS_URL, wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                pass  # popup on empty orders list can prevent networkidle
            time.sleep(3)

            if not _is_logged_in(page):
                browser.close()
                raise FCSessionExpired(
                    "First Cry session has expired. Run: python automation/fc_auth.py"
                )

            logger.info("Session valid. URL: %s", page.url)

            # ── Navigate to Pending Orders ────────────────────────────────────
            _navigate_to_pending_orders(page)

            # ── Check count ───────────────────────────────────────────────────
            pending_count = _get_pending_count(page)
            logger.info("Pending orders: %d", pending_count)

            if pending_count == 0:
                logger.info("No pending orders. Nothing to do.")
                result["skipped"] = True
                browser.close()
                return result

            # ── Process orders one by one ─────────────────────────────────────
            # Re-fetch gear icons on each iteration (DOM changes after each order)
            processed_ids: set[str] = set()
            max_orders = 50  # safety cap

            for _ in range(max_orders):
                # Re-read the pending orders table
                rows = page.locator("tbody tr")
                if not rows.count():
                    logger.info("No more order rows in table.")
                    break

                # Find the first unprocessed order
                order_id = ""
                gear_icon = None
                row_index = -1
                order_date_raw = ""
                shipping_address = ""

                for i in range(rows.count()):
                    row = rows.nth(i)
                    # Order ID is the first link in the row
                    id_link = row.locator("td a").first
                    if id_link.count():
                        oid = id_link.inner_text().strip()
                        if oid and oid not in processed_ids:
                            order_id = oid
                            row_index = i
                            # Gear icon is the last element in the row
                            gear = row.locator("td:last-child a, td:last-child button, [class*='gear'], [title*='Configure']").first
                            if not gear.count():
                                gear = row.locator("td").last.locator("a, button").first
                            gear_icon = gear
                            # Read Order Date (col 2) and Shipping Address (col 5)
                            try:
                                order_date_raw   = row.locator("td").nth(2).inner_text().strip()
                                shipping_address = row.locator("td").nth(5).inner_text().strip()
                            except Exception:
                                pass
                            break

                if not order_id or gear_icon is None:
                    logger.info("No more unprocessed orders found.")
                    break

                from tcb.geo import pincode_to_city_state
                pincode    = _parse_pincode_from_address(shipping_address)
                city, state = pincode_to_city_state(pincode)
                order_date = _parse_fc_order_date(order_date_raw)
                logger.info("Processing order: %s (row %d) date=%s pincode=%s city=%s state=%s",
                            order_id, row_index, order_date, pincode, city, state)

                try:
                    pdfs, order_items_list = _process_one_order(ctx, gear_icon, order_id)
                    all_pdfs.extend(pdfs)
                    result["orders_processed"] += 1
                    result["pdfs_downloaded"] += len(pdfs)
                    processed_ids.add(order_id)
                    for item in order_items_list:
                        db_status = _record_fc_order(
                            order_id, item["sku_id"], item["qty"],
                            city, state, order_date, dry_run,
                        )
                        result["order_details"].append({
                            "order_id":   order_id,
                            "sku_id":     item["sku_id"],
                            "qty":        item["qty"],
                            "city":       city,
                            "order_date": order_date.isoformat() if order_date else None,
                            "db_status":  db_status,
                        })
                        logger.info("Order %s/%s: done. PDFs=%d DB=%s",
                                    order_id, item["sku_id"], len(pdfs), db_status)
                except Exception as exc:
                    logger.error("Order %s: FAILED — %s", order_id, exc)
                    processed_ids.add(order_id)  # mark as attempted, skip on next loop
                    result["order_details"].append({
                        "order_id":   order_id,
                        "sku_id":     "?",
                        "qty":        "?",
                        "city":       city,
                        "order_date": order_date.isoformat() if order_date else None,
                        "db_status":  f"FAILED: {exc}",
                    })

                # Brief pause between orders
                time.sleep(2)

                # Reload pending orders for the next iteration
                _navigate_to_pending_orders(page)
                time.sleep(2)

        except FCSessionExpired:
            try:
                browser.close()
            except Exception:
                pass
            raise
        except Exception:
            logger.exception("FC scraper encountered an error.")
            try:
                browser.close()
            except Exception:
                pass
            raise

        browser.close()

    # ── Email all PDFs ─────────────────────────────────────────────────────────
    if not all_pdfs:
        failed_orders = [od for od in result.get("order_details", []) if str(od.get("db_status", "")).startswith("FAILED")]
        if failed_orders:
            logger.warning("No PDFs downloaded — %d order(s) failed. Sending alert.", len(failed_orders))
            try:
                from automation.email_sender import send_alert
                rows_txt = "\n".join(
                    f"  {od['order_id']}  {od.get('db_status', '')}"
                    for od in failed_orders
                )
                send_alert(
                    subject=f"⚠️ FC Scraper — {len(failed_orders)} order(s) failed ({date.today().strftime('%d-%b')})",
                    body=(
                        f"{len(failed_orders)} First Cry order(s) failed to process:\n\n"
                        f"{rows_txt}\n\n"
                        f"The order(s) are still pending on the FC portal — re-run the scraper or process manually.\n\n"
                        f"Log: automation/logs/fc_{date.today().strftime('%Y%m%d')}.log"
                    ),
                )
            except Exception as alert_exc:
                logger.error("Could not send failure alert: %s", alert_exc)
        else:
            logger.warning("No PDFs downloaded despite pending orders — check logs.")
        return result

    if no_email:
        logger.info("--no-email: skipping email send. PDFs saved to %s", DOWNLOAD_DIR)
        return result

    from automation.email_sender import send_with_attachments

    recipients = [
        r for r in [
            os.environ.get("EMAIL_HIMANSHU", "").strip(),
            os.environ.get("EMAIL_DILWAR", "").strip(),
            os.environ.get("EMAIL_MEET", "").strip(),
        ]
        if r
    ]

    if not recipients:
        logger.warning("No email recipients. Set EMAIL_HIMANSHU / EMAIL_DILWAR / EMAIL_MEET in .env")
    else:
        n     = result["orders_processed"]
        today = date.today().strftime("%d-%b-%Y")
        run_time = datetime.now().strftime("%H:%M")
        subject = f"First Cry Orders — {today} {run_time} ({n} order(s), {len(all_pdfs)} PDFs)"

        od_list = result.get("order_details", [])
        if od_list:
            header  = f"  {'Order No':<22} {'SKU':<8} {'Qty':<5} {'Date':<12} {'City':<15} DB Status"
            divider = "  " + "-" * 78
            rows_txt = "\n".join(
                f"  {od['order_id']:<22} {od['sku_id']:<8} {od['qty']:<5} "
                f"{(od.get('order_date') or '-'):<12} "
                f"{(od.get('city') or '-'):<15} {od['db_status']}"
                for od in od_list
            )
            db_block = f"{header}\n{divider}\n{rows_txt}"
        else:
            db_block = "  (No orders processed)"

        body = (
            f"Hi,\n\n"
            f"{n} First Cry order(s) processed on {today}.\n\n"
            f"Orders recorded to DB:\n"
            f"{db_block}\n\n"
            f"If anything above looks wrong, fix it in Warehouse App -> Ship Out "
            f"before end of day.\n\n"
            f"Attachments: Invoice + Packing Slip for each order.\n\n"
            f"— Vignesh (automated)\n"
        )
        send_with_attachments(subject, body, recipients, all_pdfs, dry_run=dry_run)
        result["emailed"] = not dry_run
        logger.info("Email sent to %s with %d attachment(s).", recipients, len(all_pdfs))

    return result


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="First Cry order processor")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process orders and download PDFs, but skip email and DB write")
    parser.add_argument("--no-email", action="store_true",
                        help="Process orders, write to DB, download PDFs — but skip email")
    parser.add_argument("--headed", action="store_true",
                        help="Show browser window — use for first-run debugging")
    args = parser.parse_args()

    os.environ.setdefault("TCB_ENV", "prod")

    logger.info("=" * 55)
    logger.info("FC scraper started — %s", date.today().isoformat())
    logger.info("=" * 55)

    try:
        result = run(dry_run=args.dry_run, headed=args.headed, no_email=args.no_email)
        if result["skipped"]:
            print("No pending First Cry orders — nothing to do.")
        else:
            print(
                f"FC: orders_processed={result['orders_processed']} | "
                f"pdfs={result['pdfs_downloaded']} | "
                f"email={'sent' if result['emailed'] else ('dry-run' if args.dry_run else 'not sent')}"
            )
    except FCSessionExpired as e:
        logger.error("SESSION EXPIRED: %s", e)
        try:
            from automation.email_sender import send_alert
            send_alert(
                subject=f"⚠️ FC Scraper — Session Expired ({date.today().strftime('%d-%b')})",
                body=(
                    f"The First Cry portal session has expired.\n\n"
                    f"Action required:\n"
                    f"  python automation/fc_auth.py\n\n"
                    f"Log: automation/logs/fc_{date.today().strftime('%Y%m%d')}.log"
                ),
            )
        except Exception:
            pass
        print(f"SESSION EXPIRED: {e}")
        sys.exit(2)
    except Exception as e:
        logger.error("FAILED: %s", e)
        try:
            from automation.email_sender import send_alert
            send_alert(
                subject=f"⚠️ FC Scraper — Failed ({date.today().strftime('%d-%b')})",
                body=(
                    f"Error: {e}\n\n"
                    f"Log: automation/logs/fc_{date.today().strftime('%Y%m%d')}.log"
                ),
            )
        except Exception:
            pass
        print(f"ERROR: {e}")
        sys.exit(1)
