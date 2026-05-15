# Sales MIS + Demand Planning System — Build Plan

*Last updated: May 2026*

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
| `ui/app.py` | Warehouse app — Ship Out, Inward, Assembly, Write-off, Reorder, Geography |
| `ui/sales_app.py` | Sales MIS — Overview, Trends, By Channel, By SKU, Returns, Geography |
| Return reason fields | `return_reason`, `return_responsible`, `return_customer_verbatim` — all channels |
| COGS / lot system | FIFO lot consumption for Amazon FBA and Blinkit |
| `mcp/server.py` | Vignesh — FastMCP server, 9 tools, connected to Claude.ai + Claude Desktop |

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
| G | Daily Automation — data pipeline + WhatsApp briefing | 🚧 Next |
| H | Vignesh as Proactive Agent — memory + scheduling + decision logic | 🔲 Pending |
| I | Full Autonomy — approval gates, self-monitoring, agent loop | 🔲 Pending |

---

## Vignesh — The Ops Agent (Overall Arc)

Vignesh is not just an MCP server. The long-term vision is a true ops agent who monitors the business, surfaces issues, and acts. He evolves in layers:

```
Phase F (Done)    → Passive tool server. Answers when asked. No initiative.
Phase G (Next)    → Gets eyes and a voice. Data flows in automatically. Sends daily WhatsApp.
Phase H           → Gets a brain. Monitors proactively. Recommends. Flags anomalies.
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

**New tab in sales_app.py — 🔮 Forecast:**
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

**New tab in sales_app.py — 📦 Reorder Plan:**
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

## Phase G — Daily Automation + WhatsApp Briefing 🚧 Next

**Goal:** Data pipeline runs at 12:00 noon IST with zero manual intervention. Vignesh sends a WhatsApp sales briefing to Himanshu + Shubhra immediately after.

### G1 — Amazon SP-API daily pull ✅ Already working

`automation/amazon_sp_api.py` is built and used for production loads. Needs to be wired to a daily scheduler.

```
12:00 noon IST
  → python automation/amazon_sp_api.py orders    # last 10 days window
  → python automation/amazon_sp_api.py finances  # settlement data
```

### G2 — Blinkit daily scraper 🔲 To build

**File:** `automation/blinkit_scraper.py`

Blinkit has no public API. Use Playwright to:
1. Log into Blinkit seller portal (credentials in `.env`)
2. Navigate to MTD sales report
3. Download CSV
4. Run `ingest/load_blinkit_sales.py` on the file

```
12:00 noon IST
  → python automation/blinkit_scraper.py  # downloads + ingests
```

### G3 — WhatsApp daily briefing 🔲 To build

**Platform:** Meta Cloud API (free tier, up to 1000 conversations/month)
**Sender number:** Dedicated number registered as WhatsApp Business (not on personal WhatsApp)
**Recipients:** Himanshu + Shubhra

**Message format (sent every day ~12:15 IST after both ingestions complete):**

```
14-May Thurs  25 units overall:
• Amazon: 1TCB005, 1TCB006, 1TCB008, 9TCB009
• Blinkit: 1TCB001, 1TCB002, 2TCB004, 1TCB005, 2TCB009
• First Cry: 1TCB006
```

One row per channel. Each entry = `{qty}{SKU_ID}`. Only channels with orders that day appear.

**Files to build:**
- `automation/whatsapp.py` — Meta Cloud API sender (template message)
- `automation/daily_summary.py` — queries yesterday's orders from DB, formats message, calls whatsapp.py

### G4 — Scheduler 🔲 To build

**Windows:** Task Scheduler jobs (local machine, runs at noon IST)
**Cloud option (later):** GitHub Actions cron for resilience

```
12:00 → G1 Amazon orders + finances
12:00 → G2 Blinkit scraper
12:15 → G3 WhatsApp briefing (after both G1 + G2 complete)
```

**One-time setup required before G3:**
1. Register sender number on Meta Business Suite → WhatsApp Business API
2. Create message template (get Meta approval — ~24 hrs)
3. Store `META_WA_TOKEN`, `META_PHONE_NUMBER_ID`, recipient numbers in `.env`

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

## Build Order Going Forward

```
Track 1 — Vignesh daily automation (immediate):
  G2. Blinkit Playwright scraper
  G3. WhatsApp sender (Meta API setup first)
  G4. Scheduler (Task Scheduler, noon IST)

Track 2 — Forecasting + Reorder (parallel):
  D. Demand Forecasting Engine
  E. Reorder Integration + Vignesh tool

Track 3 — Vignesh agent layer (after G):
  H. Memory + playbooks + enhanced briefing
  I. Approval gates + invoice/PO automation
```

---

## Critical Files

| File | Status |
|------|--------|
| `tcb/inventory.py` | ✅ Complete |
| `ui/app.py` | ✅ Warehouse app complete |
| `ui/sales_app.py` | ✅ Sales MIS complete (6 tabs + City filter) |
| `ingest/load_blinkit_sales.py` | ✅ Built |
| `ingest/load_amazon_sales.py` | ✅ Built |
| `ingest/load_amazon_payout.py` | ✅ Built |
| `ingest/load_fnp_sales.py` | ✅ Built |
| `ingest/load_fc_sales.py` | ✅ Built |
| `automation/amazon_sp_api.py` | ✅ Built — orders + finances, poll/download |
| `mcp/server.py` | ✅ Built — 9 tools, live on Claude.ai |
| `automation/blinkit_scraper.py` | 🔲 Phase G2 |
| `automation/whatsapp.py` | 🔲 Phase G3 |
| `automation/daily_summary.py` | 🔲 Phase G3 |
| `automation/vignesh_monitor.py` | 🔲 Phase H2 |
| `tcb/forecasting.py` | 🔲 Phase D |
| `tcb/reorder.py` | 🔲 Phase E |
