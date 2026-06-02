# Plan: Blinkit Shipment Tab — Invoice Generator + E-way Bill

## Context

Every Blinkit replenishment shipment requires two painful manual steps before the boxes leave the warehouse:

1. **Invoice generation** — Himanshu downloads the RO Excel from the Blinkit seller panel, then manually copy-pastes line items, tax rates, MRP, landing prices, and company details into an invoice Excel template. Takes ~30 minutes. Error-prone.
2. **E-way bill creation** — Manually entered on the NIC government portal. Tedious and repetitive.

The downstream steps (Delhivery order creation, label printing) stay manual for now.

**Goal:** A new "📦 Blinkit Shipments" tab in TinySteps WMS where Himanshu uploads the Blinkit RO Excel, inputs an invoice number + date, and downloads a ready-to-sign invoice Excel in under 60 seconds.

**No DB schema changes.** All data needed (company GSTIN, address, SKU↔item code mapping) already exists in `company_config` and `sku_channel_ids`.

---

## What We're Building

### Phase 1 (Now): Invoice Generator
- Upload Blinkit RO Excel → auto-parse line items → generate filled invoice Excel
- Handles two tax formats: **IGST** (non-Karnataka WHs) and **CGST+SGST** (Karnataka WHs)
- Box count and Units in Box left blank — Himanshu fills manually before signing

### Phase 2 (After NIC credentials): E-way Bill
- NIC e-way bill API wrapper → submit invoice data → get EWB number + PDF
- Note: NIC API credentials are obtained by registering on ewaybillgst.gov.in (1–3 days). Not a hard blocker — Himanshu should register now so credentials are ready when Phase 2 starts.

### Bonus (Optional): Thermal Label Printing
- Print Delhivery LR PDF directly to 6×4 inch thermal printer via `win32print`
- Eliminates the BarTender (.btw) copy-paste step entirely
- Scope: one button in the tab after LR PDF upload

---

## Input / Output

| | Details |
|---|---|
| **Input** | Blinkit RO `.xlsx` (downloaded from Blinkit seller panel) |
| **User inputs** | Invoice number (typed), Invoice date, Destination WH (dropdown) |
| **Output 1** | Invoice Excel — matching the template format, auto-filled, Box/Units in Box blank |
| **Output 2** | Auto-saved to `data/blinkit/auto/shipments/<YYYYMM>_<RO#>/` |
| **Phase 2 output** | E-way bill PDF from NIC API |

---

## Key Design Constraints (confirmed)

1. **All invoice data comes from the RO only** — no DB values go into the invoice. Company name, GSTIN, address are read from the RO or typed by Himanshu. The invoice template is the source of truth.
2. **Invoice format must 100% match the provided templates** — one for IGST (inter-state), one for CGST+SGST (intra-state Karnataka). Templates to be shared before build starts.
3. **WH selection is used for address cross-check only** — app shows a warning if the RO destination address differs from what's in `partner_locations`. No DB write.
4. **Landing Price + MRP: taken from RO** — app shows a deviation alert if the RO values differ from the latest DB values (from `sku_channel_ids` / `sku_pricing`). No DB write-back.
5. **No DB values in invoice content** — the generated Excel is purely derived from the RO file + manual inputs (invoice number, date).

---

## Architecture

### New Files
| File | Purpose |
|---|---|
| `tcb/blinkit_invoice.py` | Core logic: RO parsing, deviation checks, invoice generation |
| `automation/ewaybill_scraper.py` | Phase 2: Playwright portal automation for NIC e-way bill |

### Modified Files
| File | Change |
|---|---|
| `ui/tinysteps_app.py` | Add 7th tab: "📦 Blinkit Shipments" |
| `requirements.txt` | Add `pdfplumber` explicitly (already used but not listed) |

---

## tcb/blinkit_invoice.py — Key Functions

### `parse_ro_excel(file_bytes: bytes) → dict`
Reads the Blinkit RO `.xlsx`. RO columns:
`#`, `Item Code`, `HSN Code`, `Product UPC`, `Product Description`, `Grammage`, `CGST %`, `SGST %`, `IGST %`, `CESS %`, `Landing Rate`, `Quantity`, `MRP`, `Total Amount`

Returns `{line_items, ro_number, destination_address}`.
Skips summary/total rows (non-numeric `Item Code`).
**All values taken directly from RO — no DB lookups for invoice content.**

### `check_deviations(db, line_items: list[dict]) → list[dict]`
For each line item, queries DB for latest MRP (`sku_pricing`) and Landing Price (`sku_channel_ids`).
Returns deviation warnings: `{item_code, description, ro_mrp, db_mrp, ro_landing, db_landing}`.
**Display-only — no writes. Surfaces price anomalies before invoice is generated.**

### `check_wh_address(db, selected_wh_name: str, ro_address: str) → str | None`
Looks up `partner_locations` for the selected WH, compares to RO destination address.
Returns a warning string if they differ. **Cross-check only — no writes.**

### `generate_invoice_excel(line_items, invoice_no, invoice_date, ro_number, tax_type, template_path) → BytesIO`
Builds invoice Excel using `openpyxl`, pixel-matching the provided templates.

**Two templates (to be shared by Himanshu before build starts):**
- IGST template — inter-state (all WHs except Karnataka)
- CGST+SGST template — intra-state Karnataka (Bengaluru B3, B5)

Tax type determined by selected WH state: Karnataka → CGST+SGST, else → IGST.
**All data from RO Excel + PDF + manual UI inputs. Zero DB values in invoice content.**

### `parse_ro_pdf(file_bytes: bytes) → dict`
Parses Blinkit RO PDF using `pdfplumber` to extract:
- Consignee name + full address + GSTIN (for Bill To / Ship To)
- RO number (cross-check vs Excel filename)
**PDF is only needed for Bill To / Ship To — all line item data comes from Excel.**

### Complete invoice structure (confirmed from both templates):

*Header block:*
- "TAX INVOICE" (hardcoded)
- Supplier: Goodsense Trading India Private Limited, address, GST: 29AALCG8970F1Z0 (hardcoded)
- Consignee (Bill To = Ship To): from PDF RO — name, address, GSTIN
- RO Number: from Excel filename | Invoice No + Date: UI input | Delivery Date: Invoice Date + 8 days (editable)
- Delivery Partner: UI dropdown — "Self Ship" (GST 29AALCG8970F1Z0) or "Delhivery" (GST 06AAPCS9575E1ZR)
- Total Qty + Item Count: from RO Excel

*Line items:*
`Sr.No | Item ID | Description | UPC | HSN No | MRP | Box (blank) | Units in Box (blank) | Total Units | CGST%+SGST% or IGST% | Unit Basic Price | Unit Landing Price | Total Amount`

Formulas (computed in Python, written as static values):
- `Unit Basic Price = Landing Rate / (1 + GST%)`
- `Total Amount per line = Landing Rate × Total Units`

*Summary (right side):*
- Gross Total (Basic Price) = SUM(Unit Basic Price × Total Units per line)
- CGST-Output Tax = Gross Total × CGST% | SGST-Output Tax = Gross Total × SGST% *(CGST+SGST)*
- IGST-Output Tax = Gross Total × IGST% *(IGST — single row, rest of layout identical)*
- Less: Round Off
- Total Amount Chargeable = SUM(Total Amount per line) — must equal RO Net Amount ✓

*Summary (left side):*
- "Total Amount Chargeable (in words): INR [X] only"
- "Total Tax Amount (in words): INR [X] only"
- Indian number-to-words (lakhs/paise) — utility function in module

*Footer (hardcoded, no bank details):*
- "Thanks for shopping with us."
- Declaration + Terms & Conditions (2 lines) + Authorised Signatory

---

## Streamlit Tab — "📦 Blinkit Shipments"

```
┌──────────────────────────────────────────────────────────┐
│ 📦 Blinkit Shipments                                     │
│                                                          │
│ Upload RO Excel (.xlsx)   Upload RO PDF (.pdf)           │
│ [  Choose file  ]         [  Choose file  ]              │
│  (line items)              (Bill To/Ship To address)     │
│                                                          │
│ Destination WH    [Faridabad - Feeder           ▼]      │
│ Delivery Partner  [Delhivery                    ▼]      │
│ Invoice Number    [GT/26-27/___                  ]       │
│ Invoice Date      [2026-06-02]  Delivery Date [+8 days] │
│                                                          │
│ ── Parsed Line Items ─────────────────────────────────  │
│  Item ID   Description    Qty   MRP   Landing   Total   │
│  10272641  Growing Joy    86   1995    1599    137514   │
│  10282820  Little Looker  51   1195     949     48399   │
│  10273430  Just Arrived   50    995     949     47450   │
│  ───────────────────────────────────────────────────── │
│  TOTAL                   187                  233363   │
│                                                          │
│ Tax type: IGST 5% (Haryana — inter-state)               │
│                                                          │
│ ⚠️ Price deviation: TCB005 MRP ₹1,995 on RO vs ₹1,799  │
│    in DB — verify before generating                     │
│                                                          │
│ ⚠️ Address: RO shows "Sector 25" — DB has "Sector 24"  │
│                                                          │
│ [  Generate Invoice  ]                                   │
│                                                          │
│ ✅ Invoice generated — GT/26-27/014                      │
│ [  ⬇ Download Invoice Excel  ]                          │
│ Saved: data/blinkit/auto/shipments/202605_4906.../      │
└──────────────────────────────────────────────────────────┘
```

**Flow:**
1. User uploads RO `.xlsx` → app parses and shows preview table
2. User selects destination WH from dropdown (populated from `partner_locations` where channel=BLK, type=WH)
3. Tax type shown automatically (IGST or CGST+SGST) based on WH state
4. User types invoice number and confirms date (defaults to today)
5. "Generate Invoice" → builds Excel in memory → shows download button
6. File also saved to `data/blinkit/auto/shipments/YYYYMM_<RO#>/`

**Tab added at the end of the existing tab list** — no disruption to existing 6 tabs.

---

## WH Dropdown Population

Query `partner_locations JOIN channels ON channel_code='BLK' WHERE location_type='WH' AND is_active=TRUE ORDER BY name`.
Display name like "Faridabad - Feeder" (matches the names Blinkit uses on the panel).
State derived from `partner_locations.state` column (populated by migration 009).

---

## Output Folder Structure

```
data/blinkit/auto/shipments/
  202605_49060410032544/
    RO_49060410032544.xlsx          ← copy of uploaded RO
    Invoice_GT_26-27_014.xlsx       ← generated invoice
    EWB_49060410032544.pdf          ← Phase 2: e-way bill PDF
```

RO number extracted from RO Excel filename or from the summary section of the sheet.

---

## Phase 2: E-way Bill — Playwright Portal Automation

**Why not NIC direct API:** NIC "For API" requires 25,000+ invoices/month. TCB doesn't qualify.
**Why not GSP:** At 2–4 EWBs/month, adding a vendor/cost is not worth it.
**Chosen approach: Playwright automation on ewaybillgst.gov.in** — same pattern as blinkit_scraper.py, fnp_scraper.py, fc_scraper.py. Zero per-transaction cost, full control.

**New file:** `automation/ewaybill_scraper.py`

**Flow:**
1. Log into ewaybillgst.gov.in with saved Playwright session (same session-save pattern as blinkit_auth.py)
2. Navigate to e-Waybill → Generate New → fill form fields from invoice data
3. Submit → capture EWB number from confirmation page
4. Download EWB PDF → save to `data/blinkit/auto/shipments/<RO#>/`

**Form fields needed (additional UI inputs in Phase 2):**
- Transporter GSTIN (Delhivery — to be confirmed; can be stored in `.env` or `company_config`)
- LR number (typed by Himanshu after Delhivery order is created)
- Number of boxes + approximate total weight

**EWB portal fields mapped from invoice:**
- Supply type: Outward, Transaction: Regular, Document type: Invoice
- Invoice number, date, value from generated invoice
- From: Goodsense GSTIN + registered address
- To: Blinkit WH GSTIN + address (from partner_locations)
- Item HSN + taxable value + tax rates (from RO line items)
- Transporter details: GSTIN + LR number

---

## Bonus: Thermal Label Printing

**Problem:** Delhivery sends LR PDF with multiple labels. Himanshu currently copies each label into BarTender (.btw) and prints on a 6×4 thermal printer.

**Solution:** Upload LR PDF → split into individual pages → send each page scaled to 6×4 inches to the thermal printer via `win32print` (Windows-only, no new package needed).

```python
# Pseudocode
pages = split_pdf_pages(lr_pdf)          # pdfplumber or pypdf
for page in pages:
    img = render_page_to_image(page, dpi=203)   # 6x4 at 203dpi = 1218x812px
    print_to_thermal(img, printer_name)          # win32print
```

Add a "🖨️ Print Labels" section to the Blinkit Shipments tab — upload LR PDF, select printer name, click Print. Scope: add after Phase 1 is stable.

---

## Reused Existing Code

| Existing asset | Where used in this plan |
|---|---|
| `tcb/geo.py city_to_state()` | Fallback state lookup for WH city |
| `company_config` table | Load company/GSTIN/bank details |
| `sku_channel_ids.platform_pid_additional` | Map Blinkit item codes to SKU names |
| `partner_locations` table | WH dropdown + destination address |
| `openpyxl` (already in requirements.txt) | Invoice Excel generation |
| `pdfplumber` (already used in fnp_scraper.py) | Optional: parse RO PDF if Excel not available |
| `tcb/db.get_client()` pattern | DB queries in new module |
| Tab structure pattern in `tinysteps_app.py` | Extend with 7th tab |

---

## Build Order

```
Step 1 — tcb/blinkit_invoice.py
  - parse_ro_excel()
  - map_item_codes()
  - load_company_config()
  - get_wh_details()
  - generate_invoice_excel() — IGST format first, then CGST+SGST

Step 2 — tinysteps_app.py: new tab
  - File uploader + WH dropdown + invoice inputs
  - Preview table
  - Generate + download button
  - Auto-save to auto/shipments/

Step 3 — Test with the Faridabad sample RO (49060410032544.xlsx)
  - Compare output against the manually-made invoice in the sample folder

Step 4 — Share Karnataka IGST template → add CGST+SGST format support

Step 5 (Phase 2) — automation/ewaybill_scraper.py
  - Playwright session login + form fill on ewaybillgst.gov.in
  - EWB number capture + PDF download
  - "Generate E-way Bill" button in Blinkit Shipments tab
```

---

## Verification

1. Upload `data/blinkit/manual/shipments/202605 Faridabad_1st shipment/49060410032544.xlsx`
2. Select "Faridabad - Feeder", enter invoice number GT/26-27/014, date 22-05-2026
3. Generated invoice should match `Excel Invoice Template_Blinkit Faridabad.xlsx` line-for-line:
   - 3 line items, correct quantities, MRP, landing prices, totals
   - IGST column (not CGST+SGST) since Faridabad = Haryana ≠ Karnataka
   - Gross total ₹233,363, IGST 5% = ₹11,112, Total chargeable ₹244,475
4. Download and open in Excel — Box / Units in Box columns should be empty
5. Check `data/blinkit/auto/shipments/` for saved copy
