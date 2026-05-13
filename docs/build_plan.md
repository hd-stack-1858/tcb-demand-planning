# Sales MIS + Demand Planning System — Build Plan

*Last updated: May 2026*

## Context

The Cradle Box sells baby gift hampers across 6 channels (Amazon FBA, Amazon FBM, Blinkit, FnP, First Cry, D2C). The system captures orders, inventory movements, P&L, and returns in Supabase. The goal is a fully automated ops loop: data flows in without manual intervention, a forecasting engine drives reorder decisions, and an intelligent agent (Vignesh) answers operational questions in natural language.

---

## What Is Built (as of May 2026)

| Component | Detail |
|-----------|--------|
| `orders` table | Central sales ledger — all channels, full financial columns |
| `inventory` + `inventory_transactions` | Item-level inventory, all movement types, location-aware |
| `ingest/` scripts | Loaders for all 6 channels — upsert-safe, re-runnable |
| `ui/app.py` | Warehouse app — Ship Out, Inward, Assembly, Write-off, Reorder, Geography |
| `ui/sales_app.py` | Sales MIS — Overview, Trends, By Channel, By SKU, Returns, Geography |
| Return reason fields | `return_reason`, `return_responsible`, `return_customer_verbatim` — populated for all channels |
| COGS / lot system | FIFO lot consumption for Amazon FBA and Blinkit |

---

## Phase Status

| Phase | Description | Status |
|-------|-------------|--------|
| A | Drop-ship sale capture | ✅ Done |
| B | Partner ingestion scripts (all channels) | ✅ Done |
| C | Sales MIS Dashboard | ✅ Done |
| D | Demand Forecasting Engine | 🔲 Pending |
| E | Reorder Integration | 🔲 Pending |
| F | Vignesh — Claude Desktop Agent | 🚧 Starting |
| G | Amazon SP-API Automation | 🚧 Starting |
| H | GitHub Actions — Full Ingestion Automation | 🚧 Starting |

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

**Status: 🔲 Pending** — depends on Phase D.

---

## Phase F — Vignesh (Claude Desktop Agent)

**What Vignesh is:** An intelligent ops employee, available in Claude Desktop. Himanshu talks to him in natural language. He has access to live DB data and answers operational questions, flags problems, and can take actions (draft POs, log adjustments).

**Not:** A scheduled bot. Vignesh is interactive — Himanshu asks, Vignesh answers with live data.

**Architecture:** FastMCP server (`mcp/server.py`) connects Claude Desktop to Supabase.

**MCP tools to build:**

| Tool | What it does |
|------|-------------|
| `get_inventory_status` | Item quantities at all locations + assemblable SKU units |
| `get_low_stock_alerts` | Items at/below ROP with days-of-stock remaining |
| `get_oos_risk` | SKUs predicted OOS within N days based on velocity |
| `get_sales_report` | Revenue + units by channel/SKU/date range |
| `get_channel_pnl` | P&L by channel — margin, ACoS, net margin |
| `get_return_summary` | Return rate by channel/SKU/reason/responsible |
| `forecast_demand` | Predicted units next 1–3 months |
| `create_purchase_order` | Draft PO → saves to DB |
| `record_stock_movement` | Log receipt/dispatch/adjustment |
| `get_po_status` | Open POs + expected delivery dates |

**Example conversations with Vignesh:**
- *"What will go OOS in the next 2 weeks?"*
- *"Our Blinkit return rate this month vs last?"*
- *"Draft a PO for TCB005 — 6 weeks of stock at current velocity"*
- *"How many units of TCB009 can I assemble right now?"*

**Connect:** Register `mcp/server.py` in `claude_desktop_config.json`.

**Status: 🚧 Starting** — next major build after D/E, or can be built in parallel.

---

## Phase G — Amazon SP-API Automation

**Goal:** Amazon daily sales and released payout updates run automatically — no manual CSV downloads.

**What to automate:**
- **Orders/Sales report:** SP-API Reports API → request `GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL` → poll until ready → download → run `ingest/load_amazon_sales.py`
- **Payout/settlements:** SP-API Finances API → `listFinancialEvents` → run `ingest/load_amazon_payout.py`
- **Trigger:** Daily at 07:00 IST via GitHub Actions cron (Phase H)

**Steps to get started:**
1. Register as SP-API developer in Amazon Seller Central (Settings → Developer Console) — ~1 week approval
2. Create IAM role + OAuth credentials
3. Build `automation/amazon_sp_api.py` — thin wrapper around SP-API for report request + poll + download
4. Wire into GitHub Actions (Phase H)

**Key SP-API endpoints:**
- `POST /reports/2021-06-30/reports` — request report
- `GET /reports/2021-06-30/reports/{reportId}` — poll status
- `GET /reports/2021-06-30/documents/{reportDocumentId}` — download
- `GET /finances/v0/financialEvents` — settlements/payouts

**Status: 🚧 Starting** — SP-API registration is the first action. Can build the code wrapper while approval is pending.

---

## Phase H — GitHub Actions Ingestion Automation

**Goal:** All channel data updates happen on a schedule with zero manual intervention. Problems are called out intelligently.

**Architecture:**

```
GitHub Actions (cron)
    │
    ├── Amazon (daily)     → SP-API download → load_amazon_sales.py → prod DB
    ├── Blinkit (daily)    → Playwright browser → download CSV → load_blinkit_sales.py → prod DB
    ├── FnP (weekly)       → Playwright browser → download → load_fnp_sales.py → prod DB
    ├── First Cry (weekly) → Playwright browser → download → load_fc_sales.py → prod DB
    ├── Peeko (weekly)     → Playwright browser or email parse → prod DB
    └── Ozi (weekly)       → Playwright browser or email parse → prod DB
    │
    └── Post-load: Claude API anomaly detection → WhatsApp alert (Twilio)
```

**Workflow files:** `.github/workflows/`
- `ingest_amazon.yml` — daily 07:00 IST (01:30 UTC)
- `ingest_blinkit.yml` — daily 08:00 IST
- `ingest_partners.yml` — weekly Sunday, covers FnP/FC/Peeko/Ozi

**Secrets stored in GitHub:** `SUPABASE_URL`, `SUPABASE_KEY`, `AMAZON_SP_API_*`, portal credentials per channel, `TWILIO_*`

**Post-load intelligence (Claude API):**
After each successful load, a Python script calls Claude API with a summary of what was loaded + any anomaly signals (zero orders, unusual return spike, revenue drop >30%). Claude returns a structured alert. Alert sent via WhatsApp (Twilio) or email.

**Intelligent callouts:**
- Zero orders loaded for a channel that usually has orders
- Return rate spike (>2x rolling average)
- Revenue drop >30% vs same day last week
- COGS lot mismatch or lot exhaustion
- Rows loaded but `lot_cogs_finalized=False` still pending

**Status: 🚧 Starting** — depends on Phase G for Amazon leg. Blinkit Playwright leg can start independently.

---

## Build Order Going Forward

```
Parallel track 1 (Forecasting + Reorder):
  D. Demand Forecasting Engine
  E. Reorder Integration

Parallel track 2 (Automation):
  G. SP-API registration (background — 1 week approval)
  H. GitHub Actions — start with Blinkit Playwright leg
  G. SP-API code wrapper (build while approval pending)
  H. Wire Amazon into GitHub Actions once SP-API approved

Parallel track 3 (Agent):
  F. Vignesh MCP server — start with read-only tools (inventory + sales)
     then add write tools (PO, stock movement) once read tools stable
```

---

## Critical Files

| File | Status |
|------|--------|
| `tcb/inventory.py` | ✅ `record_dropship_sale()` added |
| `ui/app.py` | ✅ Warehouse app complete |
| `ui/sales_app.py` | ✅ Sales MIS complete (6 tabs) |
| `ingest/load_blinkit_sales.py` | ✅ Built |
| `ingest/load_amazon_sales.py` | ✅ Built |
| `ingest/load_amazon_payout.py` | ✅ Built |
| `ingest/load_fnp_sales.py` | ✅ Built |
| `ingest/load_fc_sales.py` | ✅ Built |
| `setup/_populate_az_return_reasons.py` | ✅ Built |
| `setup/_populate_fc_return_reasons.py` | ✅ Built |
| `tcb/forecasting.py` | 🔲 New |
| `tcb/reorder.py` | 🔲 New |
| `mcp/server.py` | 🔲 New — Vignesh |
| `automation/amazon_sp_api.py` | 🔲 New |
| `.github/workflows/ingest_amazon.yml` | 🔲 New |
| `.github/workflows/ingest_blinkit.yml` | 🔲 New |
| `.github/workflows/ingest_partners.yml` | 🔲 New |
