# Sales MIS + Demand Planning System — Build Plan

## Context

The Cradle Box has a working warehouse app that tracks inventory movements but records zero financial data — no selling price, no revenue. The `orders` table exists in Supabase with full financial columns but is entirely empty. No channel sell-out data has been ingested from any partner.

The goal is to close this loop: capture actual sales velocity (from drop-ship shipments + partner CSV exports), build a Sales MIS dashboard on a separate URL, feed that data into a 3-month demand forecast, let Himanshu tweak the final demand, and use that to drive proper reorder point calculations back into the warehouse app.

---

## What Already Exists (reuse, don't recreate)

| Table | Use |
|-------|-----|
| `orders` | Central sales ledger — all channel sell-out goes here. Full financial columns already designed. |
| `darkstore_sales` | Blinkit darkstore-level sell-out (date × darkstore × SKU × qty × value) |
| `demand_forecasts` | Forecast output (sku_id, channel_id, forecast_month, forecast_units, model) |
| `sku_pricing` | Auto-populate selling price in Ship Out form |
| `channels` | 12 channels already seeded; channel_id used as FK in orders |
| `darkstores` | Blinkit darkstores already seeded |
| `replenishment_recommendations` | Will store reorder suggestions once demand is known |

---

## Five Phases — Build Sequence

### Phase A — Drop-ship sale capture (update existing warehouse app)

**Problem:** Ship Out tab dispatches inventory but writes nothing to `orders` table.

**Changes to `tcb/inventory.py`:**
- Add `record_dropship_sale(sku_id, qty, channel_id, selling_price, order_date, platform_order_id, city, notes, created_by)` function
- It calls the existing `dispatch_sku()` internally, then writes one row to `orders` per SKU shipped
- Populates: channel_id, sku_id, quantity, selling_price, gross_value (qty × sp), cogs (from item_batches FIFO), commission_amt (channel.commission_pct × gross_value), net_margin, order_date, platform_order_id, status='FULFILLED'

**Changes to `ui/app.py` — Ship Out tab (drop-ship branch only):**
- Add "Selling Price (₹)" column to the SKU data_editor table — auto-populated from `sku_pricing.sp` for each SKU, editable override
- Add "Order # (optional)" field (already exists as `reference`)
- Add "City" text input (optional, for geo analytics)
- On submit: call `record_dropship_sale()` instead of `dispatch_sku()` directly

**No schema changes needed.**

**Status: ✅ DONE** — `record_dropship_sale()` implemented, `tests/test_phase_a.py` passing.

---

### Phase B — Partner sell-out ingestion scripts

New folder: `ingest/`

**Script per partner (start with Blinkit, then Amazon, FnP, FirstCry):**

`ingest/load_blinkit.py`
- Input: Blinkit CSV export (user provides)
- Maps Blinkit product name → our sku_id (via `sku_channel_ids.platform_pid` or name matching table)
- Writes to: `orders` table (channel_id=BLK, fulfillment_type=SOR)
- Deduplication: upsert on `platform_order_id` (or date+darkstore+sku composite key)
- Handles historical Dec 2025 → now in one run

`ingest/load_amazon.py`
- Input: Amazon MTR (Merchant Tax Report) or Orders CSV
- Writes to `orders` table (channel_id=AZ for FBA sales, AZ_FBM for merchant-fulfilled drop-ship)

`ingest/load_fnp.py`, `load_firstcry.py`, `load_peeko.py`, `load_ozi.py`
- Similar pattern per partner

Each script accepts a `--file` argument and `--env dev/prod` flag.

**Design rule:** All scripts use upsert (not insert) on `platform_order_id` — safe to re-run without creating duplicates.

**Note:** `darkstore_sales` table was dropped (migration 006). Blinkit data goes to `orders` only, with `partner_location_id` for darkstore granularity. `partner_soh_snapshots` (for Blinkit/FBA inventory snapshots) to be designed in this phase.

**Status: 🔲 NEXT**

---

### Phase C — Sales MIS Dashboard (new Streamlit app)

**New file:** `ui/sales_app.py`
**Deploy to:** separate Streamlit Cloud app (e.g., `tcbsales.streamlit.app`)
**Shares:** same Supabase prod DB, same `tcb/` library

**Tabs:**

1. **📊 Overview**
   - Revenue by month (bar chart) — all channels combined
   - Net margin by channel (table, color-coded)
   - Units sold by SKU (bar, ranked)
   - Filters: date range, channel

2. **🔍 Velocity**
   - Weekly/monthly units sold per SKU × channel
   - Trend sparklines
   - Rolling 4-week avg — this is the core input to forecasting

3. **📤 Upload Data**
   - File uploader widget (CSV)
   - Partner selector (Blinkit / Amazon / FnP / etc.)
   - Calls the relevant `ingest/load_*.py` logic inline
   - Shows preview of rows to be loaded + confirmation
   - Shows load summary: N rows inserted, M duplicates skipped

**Status: ✅ Done** — `ui/sales_app.py` built. 5 tabs: Overview, Trends, By Channel, By SKU, Returns & Status. Auth via Streamlit Cloud viewer allowlist.

---

### Phase D — Demand Forecasting Engine

**New file:** `tcb/forecasting.py`

**Key functions:**
- `get_velocity(sku_id, channel_id=None, lookback_weeks=8)` → avg weekly units from `orders`
- `generate_forecast(lookback_weeks=8, horizon_months=3)` → for each SKU × channel, extrapolate velocity × weeks in month → write to `demand_forecasts` with model='VELOCITY_AVG'
- Returns dict of {sku_id: {month: units}} for UI display

**New tab in sales_app.py — 🔮 Forecast:**
- Button: "Generate Forecast (last 8 weeks velocity)"
- Shows editable table: SKU × Month1 / Month2 / Month3 (pre-filled from velocity forecast)
- User edits any cell directly
- Button: "Lock Final Demand" → upserts to `demand_forecasts` with model='USER_FINAL'
- Only USER_FINAL rows drive reorder calculations

**Status: 🔲 PENDING**

---

### Phase E — Reorder Integration

**New file:** `tcb/reorder.py`

**Key functions:**
- `calculate_reorder_points()` → reads USER_FINAL demand forecasts → calculates daily velocity per item (via BOM) → ROP = (daily_velocity × lead_time_days) + safety_stock
- `calculate_reorder_quantities()` → monthly demand by item → suggest PO qty = max(MOQ, 6-week demand)
- Returns dict of {item_id: {rop, suggested_qty, current_stock, days_cover}}

**New tab in sales_app.py — 📦 Reorder Plan:**
- Table: Item | Supplier | Current Stock | New ROP | Suggested Order Qty | Days Cover
- Button: "Apply ROPs to Warehouse App" → bulk-updates `items.reorder_point` in DB
- Immediately visible in the existing Reorder tab of `tcbinventory.streamlit.app`

**Status: 🔲 PENDING**

---

### Phase F — MCP Server (Claude Desktop Integration)

**New file:** `mcp/server.py` using FastMCP.

**MCP tools:**
- `get_inventory_status` — item quantities at all locations + assemblable SKU units
- `get_low_stock_alerts` — items at/below ROP with days-of-stock remaining
- `get_oos_risk` — SKUs predicted OOS within N days based on velocity
- `get_sales_report` — units + revenue by channel/SKU/date range
- `get_channel_pnl` — P&L by channel (margin, ACoS, net margin)
- `forecast_demand` — predicted units next 1–3 months
- `create_purchase_order` — draft PO → saves to DB
- `record_stock_movement` — log receipt/dispatch/adjustment
- `get_po_status` — open POs + expected delivery dates

**Connect:** Add server to `claude_desktop_config.json`.

**Status: 🔲 PENDING**

---

### Phase G — ❓ LOST

Details discussed in a prior session (~29-Apr-2026) but not saved. Ask Himanshu to recall.

**Status: ❓ UNKNOWN**

---

## Build Order (recommended sequence)

```
Week 1:
  A. Drop-ship sale capture ✅ DONE
  B. Load historical data — Blinkit CSV ingestion first

Week 2:
  C. Sales MIS app — Overview + Velocity + Upload tabs
  B. Remaining partners (Amazon, FnP, FirstCry, Peeko, Ozi)

Week 3:
  D. Demand Forecasting tab in sales app
  E. Reorder Plan tab + push ROPs back to warehouse app

Later:
  F. MCP server — Claude Desktop integration
  G. TBD
```

---

## Critical Files

| File | Action |
|------|--------|
| `tcb/inventory.py` | ✅ `record_dropship_sale()` added |
| `ui/app.py` | ✅ Ship Out drop-ship branch updated |
| `ingest/load_blinkit.py` | NEW — Blinkit CSV → orders |
| `ingest/load_amazon.py` | NEW — Amazon CSV → orders |
| `ingest/load_fnp.py` | NEW — FnP statement → orders |
| `ui/sales_app.py` | NEW — Sales MIS + Forecast + Reorder dashboard |
| `tcb/forecasting.py` | NEW — velocity calculation + forecast generation |
| `tcb/reorder.py` | NEW — ROP + order qty from final demand |
| `mcp/server.py` | NEW — FastMCP server for Claude Desktop |

---

## Verification Checklist

- [x] Ship 1× TCB005 via D2C in warehouse app → `orders` table has row with correct selling price, COGS
- [ ] Run `load_blinkit.py` on sample CSV → rows appear in orders; re-running creates zero duplicates
- [ ] Open sales_app: revenue chart matches manual sum of orders table
- [ ] Generate forecast for TCB005: override March value → Lock → `demand_forecasts` shows model='USER_FINAL'
- [ ] Push ROPs → open Reorder tab in warehouse app → updated ROP visible immediately
