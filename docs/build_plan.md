# Sales MIS + Demand Planning System — Build Plan

*Last updated: 23-May 2026*

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
| COGS / lot system | FIFO lot consumption for Amazon FBA and Blinkit |
| `mcp/server.py` | Vignesh — FastMCP server, 9 tools, connected to Claude.ai + Claude Desktop |
| `automation/blinkit_scraper.py` + `blinkit_auth.py` | Playwright scraper — logs into Blinkit portal, downloads last-7d XLSX, ingests to DB. Headless timing fixed 17-May (sleep 8s, selector timeout 10s). |
| `automation/whatsapp.py` | Meta Cloud API sender — daily briefing to Himanshu + Shubhra. Newline sanitization added (flattens `\n` → ` | ` before API call). Live tested 17-May-2026. |
| `automation/daily_summary.py` | Queries yesterday's orders, formats WhatsApp message. PENDING orders included in unit count (matches MIS). |
| `automation/daily_runner.py` | Orchestrator — G1 (Amazon) + G2 (Blinkit sales) + G3 (WhatsApp) + G4 (Blinkit performance scraper, runs last ~20 min). Logs to automation/logs/. HTTPError exception handler fixed. |
| Windows Task Scheduler — daily_runner | "Blinkit Sales_Daily Run" — triggers daily_runner.py at 12:01 IST. First run: 16-May-2026. |
| `automation/fnp_scraper.py` | Playwright scraper — accepts FnP orders, downloads Branding Challan PDF, emails. Live tested 17-May-2026 (3 orders). Runs 11:00/14:00/16:00 IST ✅ Active. |
| `automation/fc_scraper.py` + `fc_auth.py` | Playwright scraper — accepts FC orders, fills shipment dims, downloads Invoice+PackingSlip PDFs, emails. Multi-item order fix 21-May (row-by-row SKU+qty, all Status dropdowns). Runs 10:30/20:00 IST ✅ Active. |
| `automation/email_sender.py` | SMTP email helper — `send_with_attachments()` + `send_alert()`. `send_alert()` supports `EMAIL_HIMANSHU_ALT` for backup delivery to personal Gmail. |
| **Blinkit Replenishment (Phase J)** | See section below. Full end-to-end replenishment engine built 21-May-2026. |

---

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| A | Drop-ship sale capture | ✅ Done |
| B | Partner ingestion scripts (all channels) | ✅ Done |
| C | Sales MIS Dashboard | ✅ Done |
| D | Demand Forecasting Engine | 🔲 Pending |
| E | Reorder Integration | 🔲 Pending |
| F | Vignesh — MCP tool server (9 tools) | ✅ Done |
| G | Daily Automation — data pipeline + WhatsApp briefing | ✅ Done |
| H | Vignesh as Proactive Agent — memory + scheduling + decision logic | 🔲 Next |
| I | Full Autonomy — approval gates, self-monitoring, agent loop | 🔲 Pending |
| J | Blinkit Replenishment Model | ✅ Done (21-May-2026) — pending items below |

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

## Phase D — Demand Forecasting Engine

**New file:** `tcb/forecasting.py`

**Key functions:**
- `get_velocity(sku_id, channel_id=None, lookback_weeks=8)` → avg weekly units from `orders`
- `generate_forecast(lookback_weeks=8, horizon_months=3)` → extrapolate velocity × weeks → write to `demand_forecasts` with model='VELOCITY_AVG'

**New tab in growthspurt_app.py — 🔮 Forecast:**
- Button: "Generate Forecast (last 8 weeks velocity)"
- Editable table: SKU × Month1 / Month2 / Month3 (pre-filled, overridable)
- Button: "Lock Final Demand" → upserts to `demand_forecasts` with model='USER_FINAL'
- Only USER_FINAL rows drive reorder calculations

**Vignesh tool to add:** `forecast_demand` — returns locked USER_FINAL forecast so Himanshu can ask *"What are we expecting to sell next month?"*

**Status: 🔲 Pending** — blocked on nothing, can start anytime.

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

### G2 — Blinkit daily scraper ✅ Done

**File:** `automation/blinkit_scraper.py` + `automation/blinkit_auth.py`

Playwright-based. Loads saved session → navigates to Performance → clicks Reports → downloads last-7d XLSX → ingests via `load_blinkit_sales.py`. Session-expiry handled: exit code 2 → `daily_runner.py` sends failure email + WhatsApp alert.

**Note:** Report is always named `sales-report-last-7d-{yesterday}.xlsx` — latest Blinkit date in DB is always yesterday, not today. This is expected.

**Headless timing fix (17-May-2026):** In headless mode the SPA sidebar renders slower. Bumped post-load sleep 4s→8s and per-selector timeout 5s→10s. First clean headless run expected 18-May noon.

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

### J — Pending Items

| Item | Priority | Notes |
|------|----------|-------|
| ~~City callout flag in Excel~~ | ~~High~~ | ✅ Closed — Geo tab already shows this; no extra column needed. |
| ~~Daily performance scraper scheduler~~ | ~~High~~ | ✅ Done 22-May — wired into `daily_runner.py` as G4 (runs last, 12-min timeout). No separate Task Scheduler job needed. |
| Blinkit SOH scraper (G5) | Medium | Portal flow not yet shown. Will be wired into daily_runner after G4. |
| Blinkit ageing scraper (G6, weekly) | Medium | Portal flow not yet shown. Weekly (Mondays). `blinkit_ageing_snapshots` table exists, loader not built. Needed for >60 day recall rule. |
| WH-OOS fallback ADS | Low | Explicitly deferred — Himanshu knows affected WHs (Hyd H3) by heart for now |
| Streamlit tab in tinysteps_app.py | Low | Deferred until CLI fully validated against several real replenishment cycles |

### J — DB + Folder Cleanup (23-May-2026)

**Prod DB tables dropped:**
- `blinkit_performance_summary` — empty, no code ever wrote to it; detail CSVs are a superset
- `blinkit_locations` — data fully migrated into `partner_locations` (migration 009); all FKs re-pointed
- `amazon_locations` — same; Amazon WH lives in `partner_locations` as `AZ_BLR8`
- `distribution_rules` — empty, no code references
- `replenishment_recommendations` — empty, no code references

**`data/blinkit/auto/` restructured:**
- `auto/sales/` — Blinkit sales XLSX downloads (`blinkit_scraper.py`)
- `auto/replenishment/` — replenishment plan Excel (`replenishment.py`)
- `auto/product_performance/` — unchanged

**Blinkit summary CSV:** Decided not to download going forward. Summary report is a strict subset of the detail CSVs already downloaded daily — every column is derivable from the DB.

---

## Build Order Going Forward

```
Immediate:
  J (pending). City callout in replen Excel + SOH scraper (G5) + ageing scraper (G6, weekly)

Track 1 — Forecasting + Reorder (no blockers):
  D. Demand Forecasting Engine (tcb/forecasting.py + Forecast tab in sales_app)
  E. Reorder Integration + Vignesh tool (tcb/reorder.py + Reorder Plan tab)

Track 2 — Vignesh agent layer (can start now that G is live):
  H. Memory + decision playbooks + enhanced WhatsApp alerts
  I. Approval gates + invoice/PO automation
```

---

## Deferred / Backlog

Items explicitly decided to skip for now but worth revisiting:

| Item | Context | When to pick up |
|------|---------|-----------------|
| `sku_cogs_lot_txns` audit table | `sku_cogs_lots.qty_remaining` is mutated in-place by `_consume_lots_fifo()` and `refresh_blinkit_lots.py` with no log. Unlike inventory, there is no transaction trail — you can't tell which orders consumed a lot or whether a drop was a sale vs. a reconciliation. A log table (lot_id, event_type, qty_change, order_id, reference, txn_date) would close this gap. Code change: one extra insert inside `_consume_lots_fifo()` and `refresh_blinkit_lots.py`. | Before tax/accounting audit queries become needed — likely Phase D or E when COGS accuracy matters for forecasting |

---

## Critical Files

| File | Status |
|------|--------|
| `tcb/inventory.py` | ✅ Complete |
| `ui/tinysteps_app.py` | ✅ Warehouse app complete |
| `ui/growthspurt_app.py` | ✅ Sales MIS complete (6 tabs + City filter) |
| `ingest/load_blinkit_sales.py` | ✅ Built |
| `ingest/load_amazon_sales.py` | ✅ Built |
| `ingest/load_amazon_payout.py` | ✅ Built |
| `ingest/load_fnp_sales.py` | ✅ Built |
| `ingest/load_fc_sales.py` | ✅ Built |
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
| `automation/blinkit_performance_scraper.py` | ✅ Phase J — daily perf CSV download. Wired into daily_runner.py (G4, 22-May). Navigation fixed: Product Expansion tab → header checkbox → Reports → Detailed Report. 10-min download timeout. |
| `setup/22_blinkit_replenishment_tables.sql` | ✅ Phase J — applied to prod |
| `automation/vignesh_monitor.py` | 🔲 Phase H2 |
| `tcb/forecasting.py` | 🔲 Phase D |
| `tcb/reorder.py` | 🔲 Phase E |
