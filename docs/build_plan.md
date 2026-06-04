# Sales MIS + Demand Planning System — Build Plan

*Last updated: 4-Jun-2026*

---

## Vision

The Cradle Box sells baby gift hampers across 6 channels. This system captures orders, inventory, P&L, and returns in Supabase. The north star: **Vignesh runs ops autonomously** — data flows in without manual intervention, he monitors everything, flags issues, suggests actions, and executes them with approval. Himanshu and Shubhra focus on growth; Vignesh handles the operational loop.

---

## What Is Built (as of May 2026)

| Component | Detail |
|-----------|--------|
| `orders` table | Central sales ledger — all channels, full financial columns |
| `inventory` + `inventory_transactions` | Item-level inventory, all movement types, location-aware |
| `ingest/` scripts | Loaders for all 6 channels — upsert-safe, re-runnable |
| `automation/amazon_sp_api.py` | SP-API client — orders report + finances, poll/download, feeds ingest scripts |
| `ui/tinysteps_app.py` | Warehouse app — Ship Out, Inward, Assembly, Write-off, Reorder, Geography |
| `ui/growthspurt_app.py` | Sales MIS — Overview, Trends, By Channel, By SKU, Returns, Geography |
| Return reason fields | `return_reason`, `return_responsible`, `return_customer_verbatim` — all channels |
| Monthly return enrichment | `ingest/enrich_az_return_reasons.py` — reads Amazon Returns Google Sheet (Tab: Amazon) directly; 3-month rolling window; handles Refunded (→ RTO/SALE_RETURN) and Replaced (→ FULFILLED + reason fields) separately; cross-checks A/B/C. `ingest/reconcile_fc_orders.py` — FC gap detection (Excel Delivered + Shipped files) + return tagging + enrichment from Google Sheet Tab: First Cry. Both run monthly after payout loaders. |
| COGS / lot system | Full lot-based COGS for all 6 channels. Migration 014: `orders.lot_id` (FK → `sku_cogs_lots`) + `orders.supply_state`. Per-channel finalization functions (`finalize_az_cogs`, `finalize_blk_cogs`, `finalize_fnp_fc_cogs`) stamp lot_id + cogs + `lot_cogs_finalized=True`. Order rows split per lot for multi-lot dispatches. |
| `mcp/server.py` | Vignesh — FastMCP server, 9 tools, connected to Claude.ai + Claude Desktop |
| `automation/blinkit_scraper.py` + `blinkit_auth.py` | Playwright scraper — logs into Blinkit portal, downloads last-7d XLSX, ingests to DB. Headless timing fixed 17-May (sleep 8s, selector timeout 10s). |
| `automation/whatsapp.py` | Meta Cloud API sender — daily briefing to Himanshu + Shubhra. Newline sanitization added (flattens `\n` → ` | ` before API call). Live tested 17-May-2026. |
| `automation/daily_summary.py` | Queries yesterday's orders, formats WhatsApp message. PENDING orders included in unit count (matches MIS). |
| `automation/daily_runner.py` | Orchestrator — G1 (Amazon) + G1b (AZ COGS finalization) + G2 (Blinkit sales) + G2b (BLK COGS finalization) + G3 (WhatsApp) + G4 (SOH scraper) + G5 (performance scraper) + G6 (dev DB ping). Logs to automation/logs/. HTTPError exception handler fixed. |
| Windows Task Scheduler — daily_runner | "Blinkit Sales_Daily Run" — triggers daily_runner.py at 12:01 IST. First run: 16-May-2026. |
| `automation/fnp_scraper.py` | Playwright scraper — accepts FnP orders, downloads Branding Challan PDF, emails. Live tested 17-May-2026 (3 orders). Runs 11:00/14:00/16:00 IST ✅ Active. |
| `automation/fc_scraper.py` + `fc_auth.py` | Playwright scraper — accepts FC orders, fills shipment dims, downloads Invoice+PackingSlip PDFs, emails. Multi-item order fix 21-May (row-by-row SKU+qty, all Status dropdowns). Runs 10:30/20:00 IST ✅ Active. |
| `automation/email_sender.py` | SMTP email helper — `send_with_attachments()` + `send_alert()`. `send_alert()` supports `EMAIL_HIMANSHU_ALT` for backup delivery to personal Gmail. |
| **Blinkit Replenishment (Phase J)** | See section below. Full end-to-end replenishment engine built 21-May-2026. |
| **Blinkit perf data cleanup (28-May)** | `blinkit_performance_ads` table fully dropped (dev + prod, migration 017). Trigger 2 updated to Column Q definition: `inventory_available=False AND total_orders>0`. `blinkit_performance_scraper.py` `ingest()` now runs Pass 0a before `process_file()` — new DS appearing in auto-downloaded files are seeded before load (was silently skipping them). |
| **COGS lot fix (28-May)** | Created lot_id=149 for 4 orphaned TCB003 units at ₹698.447 COGS — units existed in OWN_WH but had no lot (initial seeding undercount + returns consumed prior lots). Order processed successfully via TinySteps (txn_id=390). |

---

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| A | Drop-ship sale capture | ✅ Done |
| B | Partner ingestion scripts (all channels) | ✅ Done |
| C | Sales MIS Dashboard | ✅ Done |
| D | Demand Forecasting Engine | ✅ Done |
| E | Reorder Integration | 🔲 Pending |
| F | Vignesh — MCP tool server (9 tools) | ✅ Done |
| G | Daily Automation — data pipeline + WhatsApp briefing | ✅ Done |
| H | Vignesh as Proactive Agent — memory + scheduling + decision logic | 🔲 Next |
| I | Full Autonomy — approval gates, self-monitoring, agent loop | 🔲 Pending |
| J | Blinkit Replenishment Model | ✅ Done (24-May-2026) — fully closed |

---

## Vignesh — The Ops Agent (Overall Arc)

Vignesh is not just an MCP server. The long-term vision is a true ops agent who monitors the business, surfaces issues, and acts. He evolves in layers:

```
Phase F (Done)    → Passive tool server. Answers when asked. No initiative.
Phase G (Done)    → Got eyes and a voice. Data flows in automatically. Sends daily WhatsApp.
Phase H (Next)    → Gets a brain. Monitors proactively. Recommends. Flags anomalies.
Phase I           → Gets autonomy. Drafts POs, approves within guardrails, runs the ops loop.
```

**What Vignesh will own (ultimate state):**
- Inventory monitoring — flags OOS risk before it happens
- Sales monitoring — spots dips, spikes, channel anomalies
- Replenishment — calculates reorder qty, drafts POs, follows up on open POs
- Returns — tracks return rate trends, flags supplier quality issues
- Daily/weekly briefings — WhatsApp to Himanshu + Shubhra
- Invoicing — generates GST-compliant invoices for D2C + FnP
- Amazon ads — pulls ACoS/ROAS from SP-API, flags underperforming campaigns

---

## COGS + Lot Traceability Architecture (25-May-2026)

**Goal:** Every order row in the DB carries the exact lot it was fulfilled from — enabling SKU-level COGS accuracy and a full audit trail from sale back to procurement batch.

### Migration 014

```sql
ALTER TABLE orders
  ADD COLUMN lot_id        INT  REFERENCES sku_cogs_lots(lot_id),
  ADD COLUMN supply_state  TEXT;
```

Applied to dev + prod. `lot_id` is the FK to `sku_cogs_lots` — the specific lot whose `qty_remaining` was decremented for this order.

### `dispatch_sku()` — plan-return + row splitting

`dispatch_sku(sku_id, qty, channel_id, ...)` now returns `(txn_type, unit_cogs, plan)` where `plan` is a list of dicts `[{lot_id, assembled_at, unit_cogs, qty}, ...]` — one entry per lot consumed. When a dispatch spans N lots, callers insert N order rows, each with its own `lot_id`, `qty`, `cogs`, `gross_value`.

Row splitting applies to:
- `record_dropship_sale()` — D2C, Peeko, Ozi, Kiddo (Tinysteps dispatch)
- `record_outright_transfer()` — outright transfer channels
- `finalize_fnp_fc_cogs()` — FnP/FC finalization (lot[0] updates existing row; lot[1+] inserts `"{order_id}-L{lot_id}"` rows)

### Per-channel COGS finalization

| Channel | Function | When called | Mechanism |
|---------|----------|-------------|-----------|
| Amazon FBA | `finalize_az_cogs()` | G1b in daily_runner (after SP-API pull) | `consume_sor_sale()` — tier-1: pools all lots for WHs in the order's customer state; tier-2: all channel lots fallback. No DISPATCH txn inserted. Stamps `lot_id + cogs + lot_cogs_finalized=True`. |
| Amazon FBM | `finalize_az_cogs()` | G1b in daily_runner | `_consume_lots_fifo()` — all FBM lots FIFO. No DISPATCH txn. |
| Blinkit | `finalize_blk_cogs()` | G2b in daily_runner (after sales scraper) | `consume_sor_sale()` using `supply_state` captured from payout sheet. No DISPATCH txn. |
| FnP / FC | `finalize_fnp_fc_cogs()` | End of `load_fnp_sales.py` + `load_fc_sales.py`, after all upserts | `dispatch_sku()` for FULFILLED (creates DISPATCH txn, decrements OWN_WH, consumes lots FIFO). Static fallback COGS for SALE_RETURN (no dispatch, no inventory movement). |
| D2C, Peeko, Ozi, Kiddo | inline at insert | Tinysteps Ship Out button | `dispatch_sku()` via `record_dropship_sale()` — full treatment: DISPATCH txn + OWN_WH decrement + lot consumption + row splitting. `lot_cogs_finalized=True` on insert. |

### Loader conventions

- **FnP/FC loaders** insert with `cogs=None, lot_cogs_finalized=False`. Update payload guards: `not (k == "cogs" and v is None)` + `not (k == "lot_id" and v is None)` — prevents re-runs from NULLing already-finalized values.
- **Blinkit daily loader** inserts with `cogs=None, lot_cogs_finalized=False`; captures `supply_state` from Forward Orders sheet into `supply_state_map` for payout finalization.
- **Historical orders** (`lot_cogs_finalized=True` already set): permanently skipped by all finalization functions.

### `stamp_lot_id_from_dispatch()`

Utility function kept for ad-hoc historical back-fill. Not called from any loader — finalization functions handle all current flows.

---

## Phase D — Demand Forecasting Engine ✅ Done

**File:** `tcb/forecasting.py` | **Streamlit tab:** `🔮 Forecast` (8th tab in `growthspurt_app.py`) | **Migration:** `015_demand_forecasts_unique_model.sql`

### Two models

| Model | Who writes | Protected? |
|-------|-----------|-----------|
| `VELOCITY_BASE` | Engine (`generate_base_forecast()`) | Overwritten on every run |
| `USER_FINAL` | Himanshu via Streamlit Forecast tab | Never overwritten by engine |

Upsert conflict key: `(sku_id, channel_id, forecast_month, model)`. Last run date stored in `company_config` key `forecast_velocity_base_last_run`.

### Blinkit model

Uses `blinkit_performance_detail` (last 30-day rolling window). OOS signal = `inventory_available` (Column Q).

```
ADS per DS = SUM(orders WHERE inventory_available) / COUNT(inventory_available days)
```
DSes with < 5 available days filled with SKU-median ADS from reliable DSes.
Central = `mean_all` (avg ADS across ALL DSes including zero-sellers). Hi = P90 × DS count × 30. Lo = central × 0.5.

DS count per (SKU × Month):
```
ds_count = floor_ds_count (already active in eligibility)
         + new plan cities DS count × (1 - churn_rate)
churn_rate = sku_moved_out_low_sales / (active + moved_out)
```
City expansion read from `data/blinkit/manual/City Launch Plan_Blinkit.xlsx`.
`BLK_EXCLUDE_SKUS = {TCB007, TCB010}` | `BLK_SKU_ALIAS = {TCB009 → TCB009_1}`.

### Growth model (Amazon, FnP, FC, Peeko, Ozi)

Last 4 months of orders (FULFILLED + PENDING). Amazon FBM rolled into Amazon. D2C excluded (manual only).
Falls back to 15% default if < 2 MoM observations OR < 10 total units. P75 → central; P25 → lo; P90 → hi. P75/P90 capped at 35%/40%.
Compounds forward from last observed month's units.

### Constants
`FORECAST_MONTHS=6` | `LOOKBACK_MONTHS=4` | `DEFAULT_GROWTH_RATE=15%` | `MAX_MONTHLY_GROWTH=35%` | `MIN_RELIABLE_VOLUME=10` | `MIN_NON_OOS_DAYS=5`

### Streamlit Forecast tab (as of 28-May-2026)
- **▶ Regenerate** — runs `tcb/forecasting.py` as subprocess
- **Editable grid** — SKU × 6 forecast months + 3 history columns (L2LM, LM, current month projected). No horizontal scroll.
  - Inactive/opportunistic SKUs excluded: `_FC_EXCLUDE = {TCB007, TCB009, TCB009_2}` — only active SKUs shown
  - History columns: read-only, short headers (`Apr '26` format), current month shows pro-rated full-month projection (`MTD × days_in_month / days_elapsed`)
  - **TOTAL row** appended inside the same `st.data_editor` table (bold, not editable)
- **Lock Edited Cells** — `lock_sku_month()` distributes total proportionally across channels via VELOCITY_BASE mix. Lock logic skips TOTAL row and `_FC_EXCLUDE` SKUs.
- **Reset to Base** — deletes USER_FINAL rows for chosen SKU + months
- **Channel Breakdown expander** | **Excel Download** (3 sheets: Summary, Channel Breakdown, Assumptions)
- **QC + locking in progress** (started 28-May-2026) — reviewing VELOCITY_BASE numbers per SKU, locking confirmed USER_FINAL values for Jun–Nov 2026

**Vignesh tool to add (Phase H):** `forecast_demand` — returns locked USER_FINAL forecast.

---

## Phase E — Reorder Integration

**New file:** `tcb/reorder.py`

**Key functions:**
- `calculate_reorder_points()` → USER_FINAL demand → daily velocity per item via BOM → ROP = (daily_velocity × lead_time_days) + safety_stock
- `calculate_reorder_quantities()` → suggest PO qty = max(MOQ, 6-week demand)

**New tab in growthspurt_app.py — 📦 Reorder Plan:**
- Table: Item | Supplier | Current Stock | New ROP | Suggested Order Qty | Days Cover
- Button: "Apply ROPs to Warehouse App" → bulk-updates `items.reorder_point` in DB

**Vignesh tool to add:** `get_reorder_suggestions` — returns suggested POs from reorder engine so Himanshu can ask *"What should I order this week?"* and Vignesh can immediately draft the POs.

**Status: 🔲 Pending** — depends on Phase D.

---

## Phase F — Vignesh MCP Tool Server ✅ Done

**What Vignesh is:** A FastMCP server (`mcp/server.py`) that connects Claude.ai and Claude Desktop to live Supabase data. Himanshu or Shubhra ask in natural language — Vignesh fetches real data and answers.

**Architecture:** `You → Claude.ai → MCP (JSON-RPC) → Vignesh → Supabase`

**MCP tools built (9 total):**

| Tool | Type | What it does |
|------|------|-------------|
| `get_inventory_status` | Read | Item quantities at OWN_WH + assemblable SKU units |
| `get_low_stock_alerts` | Read | Items at/below ROP with gap, MOQ, lead time, supplier |
| `get_oos_risk` | Read | SKUs predicted OOS within N days based on 30d velocity |
| `get_sales_summary` | Read | Revenue + units by channel/SKU/city, filterable by date |
| `get_channel_pnl` | Read | P&L by channel — COGS, commission, ad spend, net margin |
| `get_return_summary` | Read | Return rates by channel/SKU/reason/responsible party |
| `get_po_status` | Read | Open POs (DRAFT/SENT/CONFIRMED/PARTIAL) with line items |
| `create_purchase_order` | Write | Draft PO → saves to DB (supplier match, item resolution) |
| `record_stock_receipt` | Write | Log item receipt at OWN_WH (calls `receive_item()`, batch merge) |

**Example conversations:**
- *"Which city is seeing a sales dip in May?"*
- *"What will go OOS in the next 2 weeks?"*
- *"Draft a PO for muslin swaddles — 200 units at ₹45 each"*
- *"What's the Blinkit return rate this month vs last?"*

**Connect:** Toggle "vignesh" in Claude.ai Connectors. For Claude Desktop, register in `claude_desktop_config.json` (see server.py header).

---

## Phase G — Daily Automation + WhatsApp Briefing ✅ Done

**Goal:** Data pipeline runs at 12:00 noon IST with zero manual intervention. Vignesh sends a WhatsApp sales briefing to Himanshu + Shubhra immediately after.

### G1 — Amazon SP-API daily pull ✅ Done

`automation/amazon_sp_api.py` is built and used for production loads. Needs to be wired to a daily scheduler.

```
12:00 noon IST
  → python automation/amazon_sp_api.py orders    # last 10 days window
  → python automation/amazon_sp_api.py finances  # settlement data
```

### G1b — Amazon COGS finalization ✅ Done

Runs immediately after G1 in `daily_runner.py`. Calls `finalize_az_cogs()` which stamps `lot_id + cogs + lot_cogs_finalized=True` on all pending Amazon orders using `consume_sor_sale()` (FBA, state-level FIFO) or `_consume_lots_fifo()` (FBM). No DISPATCH txns — pure lot consumption + column stamp.

### G2 — Blinkit daily scraper ✅ Done

**File:** `automation/blinkit_scraper.py` + `automation/blinkit_auth.py`

Playwright-based. Loads saved session → navigates to Performance → clicks Reports → downloads last-7d XLSX → ingests via `load_blinkit_sales.py`. Session-expiry handled: exit code 2 → `daily_runner.py` sends failure email + WhatsApp alert.

**Note:** Report is always named `sales-report-last-7d-{yesterday}.xlsx` — latest Blinkit date in DB is always yesterday, not today. This is expected.

**Headless timing fix (17-May-2026):** In headless mode the SPA sidebar renders slower. Bumped post-load sleep 4s→8s and per-selector timeout 5s→10s. First clean headless run expected 18-May noon.

### G2b — Blinkit COGS finalization ✅ Done

Runs immediately after G2 in `daily_runner.py`. Calls `finalize_blk_cogs()` which stamps `cogs + lot_cogs_finalized=True` on pending Blinkit FULFILLED orders using `consume_sor_sale()` with `supply_state` tier-1 (from payout loader) and channel-wide tier-2 fallback. No DISPATCH txns.

### G3 — WhatsApp daily briefing ✅ Done

**Platform:** Meta Cloud API (free tier, up to 1000 conversations/month) — setup complete.
**Sender number:** Dedicated WhatsApp Business number registered on Meta Business Suite.
**Recipients:** Himanshu + Shubhra

**Message format (sent every day ~12:15 IST after both ingestions complete):**

```
Sales update: 16-May Sat  27 units overall: | • Blinkit: 4TCB006, 3TCB004 | • Amazon: 5TCB009_1 | • FnP: 1TCB004 - Vignesh
```

Single flat line (` | ` separator) — Meta template params cannot contain newlines. One entry per channel, sorted by volume. Each entry = `{qty}{SKU_ID}`. Only channels with orders appear.

**Recipients:** Himanshu + Shubhra — both live and confirmed 17-May-2026. Shubhra added to Meta allowed list manually.

**Sale statuses counted:** FULFILLED, DELIVERED, SHIPPED, PENDING (PENDING included to match MIS count — confirmed 17-May).

**Files built:**
- `automation/whatsapp.py` — Meta Cloud API sender (template `daily_sales_brief`, approved)
- `automation/daily_summary.py` — queries yesterday's orders from DB, formats message, calls whatsapp.py
- `automation/daily_runner.py` — orchestrates G1+G2+G3, handles partial failures, sends failure alert emails, logs to `automation/logs/`

### G4 — Scheduler ✅ Done

**Windows Task Scheduler:** Task "Blinkit Sales_Daily Run" created and active.
- Trigger: Daily at 12:01 IST
- Action: runs `automation/daily_runner.py`
- First live run: 16-May-2026
- First fully clean run expected: 18-May-2026 (after Blinkit headless fix)

**Meta one-time setup:** Complete — sender number registered, `daily_sales_brief` template approved, tokens stored in `.env`. Shubhra added to allowed recipients 17-May-2026.

### G5 — FnP scraper ✅ Done

**Files:** `automation/fnp_scraper.py` + `automation/email_sender.py`

Playwright-based. Logs in → checks ALL date columns (TODAY/TOMORROW/FUTURE) in Allocated section → accepts orders → checks all date columns in "Orders to be shipped" → downloads Branding Challan PDF(s) → emails to Himanshu + Dilwar. Failure alerts email Himanshu.
- Schedules: 11:00, 14:00, 16:00 IST via Windows Task Scheduler ✅ Active
- Live tested 17-May-2026: 3 orders accepted, PDFs downloaded correctly
- 16:00 run on 17-May: clean ("No orders") confirming scheduler is working
- Email send test: pending (next real order with the current code)

### G6 — First Cry scraper ✅ Live + Tested

**Files:** `automation/fc_scraper.py` + `automation/fc_auth.py` + `automation/fc_dimensions.json`

Playwright-based. Loads saved session → processes each pending B2C order (accept, fill shipment dims, save) → downloads Invoice + Packing Slip PDFs → emails to Himanshu + Dilwar. Failure alerts email Himanshu.
- Dry-run passed 17-May-2026 (PDFs downloaded correctly)
- Schedule: 10:30 IST + 20:00 IST via Windows Task Scheduler ✅ Active (from 17-May-2026 evening)
- Email test passed 18-May-2026: 10:30 run picked up 1 real order, PDF downloaded and emailed ✅

### G7 — FnP + FC Layer 1 order recording ✅ Done

**Goal:** Complete the automation loop — scrapers accept orders, email PDFs, AND now auto-record each sale to DB (orders table + inventory decrement) so Sales MIS has same-day data without manual Ship Out.

**Design:** Auto-write to DB immediately. The email body includes a per-order table (Order No, SKU, Qty, City, DB status) so Himanshu can catch errors same-day and fix in Warehouse App → Ship Out, instead of waiting for month-end reconciliation.

**What was built (19-May-2026, commit 22afc9b):**
- `_read_order_rows()` in `fnp_scraper.py` — JS extraction of order table on the portal list page; resolves SKU via TCB code match or product-name → SKU lookup dict (`_FNP_PRODUCT_TO_SKU`)
- `_record_fnp_order()` — duplicate-checks then calls `record_dropship_sale()` for each FnP order; never raises (DB failure logs warning only, does not block email)
- `_record_fc_order()` in `fc_scraper.py` — same pattern, channel_id=6
- `_process_one_order()` updated to also extract qty (small-integer cell scan) and city (known-cities list scan of page text); returns `(pdfs, order_info)` tuple
- Both email bodies updated with order details table + DB status column

**Verification status:**
- **FC: ✅ Live-tested 19-May-2026** — order 13812306MQDC22099B (TCB010, qty=1, New Delhi, 2026-05-19). Order Date and City read from table row. Box No 4 fallback triggered (NonFCPackaging Material removed by FC). Weight-only fill worked. PDFs downloaded. DB recorded. Email sent.
  - Note: `NonFCPackaging Material` option appears to be permanently removed from FC portal. If it returns, scraper will use it automatically. If absent for many more days, clean up the dead primary path.
- **FnP: ✅ Verified (22-May-2026)** — Live-tested with real orders. Order extraction, DB recording, and email body (with DB status column) all confirmed working.

**Safety properties:**
- Duplicate-check before every DB write — safe on retry runs
- `--dry-run` skips DB writes but runs extraction (to test parsing without side effects)
- DB failure never blocks challan download or email

---

## Phase H — Vignesh as Proactive Agent 🔲 Pending

**Goal:** Vignesh stops waiting to be asked. He observes the business daily and surfaces what matters — without Himanshu having to remember to check.

### H1 — Memory

Vignesh needs to remember decisions, observations, and context across sessions.

**New table:** `vignesh_memory`
```
timestamp | type (observation/decision/alert) | body | resolved (bool)
```

**New MCP tools:**
- `log_observation(type, body)` — Vignesh records what he noticed
- `get_open_alerts()` — returns unresolved items needing attention

### H2 — Decision playbooks

Rules that turn observations into recommendations. Stored in code (not improvised):

```python
# Examples
if days_cover < 10 and no open PO for this item:
    → draft PO suggestion, log as unresolved alert

if blinkit_acos > 60% for 3 consecutive days:
    → flag with suggested bid reduction

if sku has zero Blinkit orders for 5 days:
    → suggest pulling from dark store

if return_rate > 2x rolling average:
    → flag supplier quality issue
```

**New file:** `automation/vignesh_monitor.py` — runs the playbook daily, logs alerts, triggers WhatsApp for anything actionable.

### H3 — Enhanced WhatsApp (with alerts)

Morning briefing expands to include anomalies:

```
14-May Thurs  25 units overall:
• Amazon: 1TCB005, 9TCB009
• Blinkit: 2TCB004, 2TCB009

⚠️  TCB003 has 4 days cover — reorder needed
⚠️  Blinkit ACoS 67% (3-day avg) — review bids
```

---

## Phase I — Full Autonomy 🔲 Pending

**Goal:** Vignesh acts within defined guardrails without always needing to ask.

### Approval-gate pattern

For consequential actions Vignesh asks once, then executes:

```
Vignesh (WhatsApp): "TCB005 stock = 6 days cover.
  Draft PO — Ram Textiles, 200 hooded towels @ ₹45 = ₹9,000.
  Reply YES to confirm."

Himanshu: "YES"

Vignesh: → creates PO in DB, marks SENT, logs decision, sets 3-day follow-up reminder
```

### Tools to add in Phase I

| Tool | What it does |
|------|-------------|
| `generate_invoice` | GST-compliant invoice PDF for D2C / FnP orders |
| `send_po_to_supplier` | Emails PO PDF to supplier (via SMTP) |
| `get_amazon_ad_performance` | Pulls SP/SB campaign ACoS from SP-API Advertising API |
| `update_blinkit_bid` | Adjusts Blinkit promoted listing bids via portal automation |
| `get_forecast_vs_actual` | Compares locked forecast to actual — flags deviation |

---

## Phase J — Blinkit Replenishment Model ✅ Done (21-May-2026)

Replaces a 2-hour manual replenishment process across 6 browser tabs. Engine computes units to ship per WH × SKU from ADS velocity + inventory snapshot, writes pre-formatted Excel.

### What Was Built

| File | Purpose |
|------|---------|
| `tcb/replenishment.py` | Engine + Excel output. `--dry-run` to preview. |
| `ingest/blinkit_performance_loader.py` | DS master refresh (Pass 0a) + eligibility (Pass 1) + ADS (Pass 2) |
| `ingest/blinkit_inventory_loader.py` | SOH snapshot loader (run on replenishment day) |
| `automation/blinkit_performance_scraper.py` | Daily Playwright download of performance CSVs |
| `setup/22_blinkit_replenishment_tables.sql` | Migration — 5 new tables |

**Formula:** `target_stock = total_ads × 37 (30d coverage + 7d buffer)` | Gate: ₹1.5L per WH

**Excel output (6 sheets):** Overview-SKU, Overview-WH, Ship Now, Full Plan, Summary (per-WH gate), Geo (city breakdown per WH)

**DS master:** 629 active dark stores seeded across 20 WHs. Hash-based DS codes (ES numbers not globally unique). `is_active` synced on every loader run.

### J — All Items Closed (24-May-2026)

| Item | Status |
|------|--------|
| `ds_choked` status + Trigger 1 & 2 data quality alerts | ✅ Done + committed |
| Replen parquet cache — dashboard reads file, never recomputes | ✅ Done |
| Blinkit Deepdive — Warehouse Status section (WH + City selectors, SKU table, Refresh & Download button) | ✅ Done |
| Blinkit Deepdive — Warehouse-City Mapping table (SKUs Launched col, city DS count, color by active SKUs) | ✅ Done |
| WH-OOS fallback ADS | Deferred — Himanshu knows affected WHs (Hyd H3) by heart |
| Streamlit tab in tinysteps_app.py | Deferred — revisit after several real replenishment cycles |

### J — DB + Folder Cleanup (23-May-2026)

**Prod DB tables dropped:**
- `blinkit_performance_summary` — empty, no code ever wrote to it; detail CSVs are a superset
- `blinkit_locations` — data fully migrated into `partner_locations` (migration 009); all FKs re-pointed
- `amazon_locations` — same; Amazon WH lives in `partner_locations` as `AZ_BLR8`
- `distribution_rules` — empty, no code references
- `replenishment_recommendations` — empty, no code references
- `blinkit_ageing_snapshots` — empty, loader never built; ageing dropped from scope (see G6 above)
- `purchase_orders` / `purchase_order_items` — empty Phase F skeleton; will recreate at Phase F build time

**Prod DB views dropped:**
- `v_blinkit_reconciliation` — referenced `blinkit_locations` (dropped) + tables that never existed
- `v_amazon_reconciliation` — referenced `amazon_fba_inventory` + tables that never existed
- `v_darkstore_doc` — referenced `darkstores`, `darkstore_inventory`, `darkstore_sales` (never existed)
- `v_monthly_mis` — broken (wrong column schema); `get_monthly_mis()` dead function removed from `tcb/db.py`; will redesign with correct P&L columns when Phase C is built

**`data/blinkit/auto/` restructured:**
- `auto/sales/` — Blinkit sales XLSX downloads (`blinkit_scraper.py`)
- `auto/replenishment/` — replenishment plan Excel (`replenishment.py`)
- `auto/product_performance/` — unchanged

**Blinkit summary CSV:** Decided not to download going forward. Summary report is a strict subset of the detail CSVs already downloaded daily — every column is derivable from the DB.

---

## FnP Fulfillment Reconciliation — Pending (Next Session)

### Current state of `load_fnp_sales.py`

Built as a **one-time historical backfill** to load all FnP orders that existed before the FnP scraper was set up. Takes two inputs: `FnP_Extracted.xlsx` (order × SKU with city/state/date) and a CDA delivery report (confirmed-delivered orders). Determines status by cross-referencing them (FULFILLED if in report, PENDING if recent, SALE_RETURN if old and absent). Has a hardcoded fix for order 7044576301 (in delivery report but missing from Extracted). Still does UPDATE on existing orders — same issue as old `load_fc_sales.py`.

**This script must not be re-run as-is** — it would overwrite App-recorded data with report data.

### What it should become (monthly recurring tool)

The FnP CDA delivery report (`cda-export_*.xls`) is the authoritative source for which orders have been delivered to the customer. The new flow:

1. **FC scraper marks orders as `SHIPPED`** (not `FULFILLED`) when it accepts and ships an order via the App. `FULFILLED` should only be set by the delivery report confirming actual delivery. **Requires a status change in `automation/fc_scraper.py`** — currently the scraper marks App entries as FULFILLED at ship time. This needs to change to `SHIPPED`.

2. **Monthly reconciliation script** (rewrite of `load_fnp_sales.py`):
   - Reads the monthly CDA delivery report
   - Any DB order (FnP channel, status `SHIPPED`) that appears in the report → update to `FULFILLED`
   - Any DB order that is `SHIPPED` but NOT in the report AND is older than ~7 days → flag as "long-pending — investigate" (stale shipment, possible lost in transit or return not captured)
   - Any order in the report NOT in DB at all → flag as "App miss"
   - No pricing recalculation, no COGS changes — those happen at App ship time
   - TP validation retained: compare GRAND_TOTAL from report against sum of `sku_channel_tp` — flag any gap > ₹1

### Dependency
- `automation/fc_scraper.py` (and `automation/fnp_scraper.py`) must be updated to write `status = SHIPPED` instead of `FULFILLED` when recording the ship-out in the App.
- All downstream queries (Sales MIS, WhatsApp summary, MCP tools) that filter on `FULFILLED` need to also include `SHIPPED` for revenue counting — or we define SHIPPED as "revenue recognised, pending delivery confirmation".
- Agreed convention: for P&L and MIS, `SHIPPED` = counts as sale (revenue recognised). `FULFILLED` = additionally confirmed delivered. Both count as revenue.

**File to create:** Rename/rewrite `load_fnp_sales.py` → `reconcile_fnp_orders.py` (consistent with `reconcile_fc_orders.py`).
**Status: 🔲 Pending — starting next session (5-Jun-2026)**

---

## Build Order Going Forward

```
Track 1 — Forecasting + Reorder:
  D. Demand Forecasting Engine ✅ Done
  E. Reorder Integration + Vignesh tool (tcb/reorder.py + Reorder Plan tab) ← next

Track 2 — Vignesh agent layer (can start in parallel):
  H. Memory + decision playbooks + enhanced WhatsApp alerts
  I. Approval gates + invoice/PO automation
```

---

## Deferred / Backlog

Items explicitly decided to skip for now but worth revisiting:

| Item | Context | When to pick up |
|------|---------|-----------------|
| `sku_cogs_lot_txns` audit table | `sku_cogs_lots.qty_remaining` is mutated in-place by `_consume_lots_fifo()` and `refresh_blinkit_lots.py` with no log. Unlike inventory, there is no transaction trail for lot consumption — you can reconstruct *which* lot an order used (via `orders.lot_id` added 25-May), but not the reverse (which orders consumed a given lot, or whether a qty drop was a sale vs. reconciliation). A log table (lot_id, event_type, qty_change, order_id, reference, txn_date) would close this gap. Code change: one extra insert inside `_consume_lots_fifo()` and `refresh_blinkit_lots.py`. | Before tax/accounting audit queries become needed — likely Phase D or E |

---

## Critical Files

| File | Status |
|------|--------|
| `tcb/inventory.py` | ✅ Complete — `dispatch_sku()` returns plan list; `finalize_az_cogs()`, `finalize_blk_cogs()`, `finalize_fnp_fc_cogs()` (new 25-May); row splitting in `record_dropship_sale()` + `record_outright_transfer()` |
| `setup/migrations/014_orders_lot_id_supply_state.sql` | ✅ Applied to dev + prod — `orders.lot_id` FK + `orders.supply_state` |
| `ui/tinysteps_app.py` | ✅ Warehouse app complete |
| `ui/growthspurt_app.py` | ✅ Sales MIS complete (6 tabs + City filter) |
| `ingest/load_blinkit_sales.py` | ✅ Built |
| `ingest/load_amazon_sales.py` | ✅ Built |
| `ingest/load_amazon_payout.py` | ✅ Built |
| `ingest/load_fnp_sales.py` | ⚠️ Historical one-time loader — do NOT re-run. To be replaced by `reconcile_fnp_orders.py` (see FnP Fulfillment Reconciliation section) |
| `ingest/reconcile_fc_orders.py` | ✅ Built (replaces `load_fc_sales.py`) — monthly FC gap detection + return tagging from Google Sheet |
| `ingest/enrich_az_return_reasons.py` | ✅ Built — monthly Amazon return reason enrichment from Google Sheet (3-month window, Refunded/Replaced handling) |
| `automation/amazon_sp_api.py` | ✅ Built — orders + finances, poll/download |
| `mcp/server.py` | ✅ Built — 9 tools, live on Claude.ai |
| `automation/blinkit_scraper.py` | ✅ Live. Stealth Chrome fix 18-May (bot detection bypass, panel download, sidebar retry) |
| `automation/blinkit_auth.py` | ✅ Built — saves Playwright session state |
| `automation/whatsapp.py` | ✅ Built + live — Meta Cloud API, newline fix applied, both recipients confirmed |
| `automation/daily_summary.py` | ✅ Built + live — PENDING orders included, matches MIS |
| `automation/daily_runner.py` | ✅ Built + live — G1+G2+G3, failure email alerts, HTTPError handler fixed |
| Windows Task Scheduler — daily_runner | ✅ Active — "Blinkit Sales_Daily Run" at 12:01 IST daily |
| `automation/fnp_scraper.py` | ✅ Live. Angular timing + load wait fix 18-May (retry loop, startsWith match) |
| `automation/email_sender.py` | ✅ Built — SMTP sender, EMAIL_HIMANSHU_ALT backup support added |
| FnP Task Scheduler jobs | ✅ Active — 11:00, 14:00, 16:00 IST |
| `automation/fc_scraper.py` + `fc_auth.py` | ✅ Live + tested. Multi-item fix 21-May: row-by-row SKU scan, all Status dropdowns set to Accepted, weights summed across items |
| `automation/fc_dimensions.json` | ✅ All 12 SKUs filled |
| FC Task Scheduler jobs | ✅ Active — 10:30, 20:00 IST (from 17-May-2026 evening) |
| `tcb/replenishment.py` | ✅ Phase J — replenishment engine + Excel (6 sheets) |
| `ingest/blinkit_performance_loader.py` | ✅ Phase J — DS master refresh + eligibility + ADS loader |
| `ingest/blinkit_inventory_loader.py` | ✅ Phase J — SOH snapshot loader |
| `automation/blinkit_soh_scraper.py` | ✅ Phase J G4 — daily SOH download + ingest. Inventory → Bulk reports → Download Stock on Hand. Saves date-stamped XLSX to auto/inventory/SOH/. |
| `automation/blinkit_performance_scraper.py` | ✅ Phase J G5 — daily perf CSV download. Navigation: Product Expansion tab → header checkbox → Reports → Detailed Report. 10-min download timeout. |
| `setup/22_blinkit_replenishment_tables.sql` | ✅ Phase J — applied to prod |
| `automation/vignesh_monitor.py` | 🔲 Phase H2 |
| `tcb/forecasting.py` | ✅ Phase D — Blinkit ADS model + growth model; VELOCITY_BASE + USER_FINAL; Forecast tab in growthspurt_app.py |
| `tcb/reorder.py` | 🔲 Phase E |
