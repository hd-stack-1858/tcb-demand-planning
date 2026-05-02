# Demand Planning System — The Cradle Box (Original Plan)

> **Note:** This is the original planning document (v1). The active plan is `build_plan.md`.
> Kept for reference — it has more architectural detail on the data model and schema.

## Context

The Cradle Box needs an end-to-end demand planning system with a single goal: **never go out of stock, on anything, ever**. The business ships from one central warehouse to: (a) customers directly (Shopify, First Cry, FnP, Amazon FBM), (b) fulfillment nodes (Amazon FBA, Blinkit dark stores), and (c) outright-purchase partners (Peeko, Kiddo). New channels (Zepto, Instamart) will be added over time. Each hamper SKU is a bundle of raw items — so inventory must be tracked at item level, then surfaced at SKU level. The system must also be the agentic "employee" Himanshu can converse with via Claude Desktop.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLAUDE DESKTOP (Agent UI)                │
│         Natural language → MCP tools → answers/alerts       │
└───────────────────────┬─────────────────────────────────────┘
                        │ MCP Protocol
┌───────────────────────▼─────────────────────────────────────┐
│                 MCP SERVER (FastMCP, Python)                 │
│  get_inventory | get_sales | forecast | create_po | alerts  │
└───────────────────────┬─────────────────────────────────────┘
                        │ Python (supabase-py)
┌───────────────────────▼─────────────────────────────────────┐
│              SUPABASE (PostgreSQL cloud DB)                  │
│  Items · SKUs · BOM · Inventory · Orders · POs · Channels   │
└─────────────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
   Data Ingestion       Inventory UI         Forecasting Engine
   (channel CSVs        (Streamlit:          (Python scripts,
    → orders table)      scan in/out)         scheduled)
```

**Tech Stack:**
- Database: Supabase (PostgreSQL) — cloud, accessible anywhere, free tier sufficient
- Backend: Python (reuses existing pandas/openpyxl/supabase-py stack)
- Agent UI: Claude Desktop + MCP Server (FastMCP)
- Inventory UI: Streamlit web app (runs locally, opened in browser)
- Scheduling: Python `schedule` library or Supabase Edge Functions

---

## Database Schema (Supabase)

### Core Tables

```sql
-- Raw components / items
items (
  item_id SERIAL PK,
  name TEXT,           -- "Hooded Towel Pink", "Crocheted Bunny Pip"
  supplier_id INT FK,
  unit TEXT,           -- "piece", "set", "roll"
  reorder_point INT,   -- alert threshold
  lead_time_days INT,  -- supplier lead time
  cost_per_unit NUMERIC
)

-- Finished hamper SKUs
skus (
  sku_id TEXT PK,      -- TCB001–TCB012
  name TEXT,
  mrp NUMERIC,
  min_sp NUMERIC,
  cogs NUMERIC,
  is_active BOOL
)

-- Bill of Materials: which items go into each SKU
bom (
  bom_id SERIAL PK,
  sku_id TEXT FK → skus,
  item_id INT FK → items,
  quantity_per_sku NUMERIC
)

-- Fulfillment locations / channels
channels (
  channel_id SERIAL PK,
  name TEXT,
  type TEXT,           -- DIRECT | FBA | DARKSTORE | PARTNER | OWN_WH
  fulfillment_source TEXT,
  commission_pct NUMERIC,
  is_active BOOL
)

-- Inventory positions — item level, by location
inventory (
  inv_id SERIAL PK,
  item_id INT FK → items,
  channel_id INT FK → channels,
  quantity_on_hand INT,
  quantity_reserved INT,
  last_updated TIMESTAMPTZ
)

-- Every stock movement — the immutable audit log
inventory_transactions (
  txn_id SERIAL PK,
  txn_date TIMESTAMPTZ,
  type TEXT,    -- RECEIPT | DISPATCH | TRANSFER | ADJUSTMENT | RETURN
  item_id INT FK,
  from_channel_id INT,
  to_channel_id INT,
  quantity INT,
  reference TEXT,
  notes TEXT,
  created_by TEXT
)

-- All sales orders (unified across channels)
orders (
  order_id TEXT PK,
  channel_id INT FK,
  order_date DATE,
  sku_id TEXT FK,
  quantity INT,
  selling_price NUMERIC,
  fulfillment_type TEXT,
  status TEXT
)

-- Suppliers
suppliers (
  supplier_id SERIAL PK,
  name TEXT,
  contact TEXT,
  phone TEXT,
  city TEXT,
  lead_time_days INT,
  payment_terms TEXT
)

-- Purchase orders to suppliers
purchase_orders (
  po_id SERIAL PK,
  supplier_id INT FK,
  created_date DATE,
  expected_date DATE,
  status TEXT,          -- DRAFT | SENT | CONFIRMED | RECEIVED | PARTIAL
  notes TEXT
)

purchase_order_items (
  poi_id SERIAL PK,
  po_id INT FK,
  item_id INT FK,
  quantity_ordered INT,
  cost_per_unit NUMERIC,
  quantity_received INT DEFAULT 0
)

-- Demand forecasts
demand_forecasts (
  forecast_id SERIAL PK,
  sku_id TEXT FK,
  channel_id INT FK,
  forecast_month DATE,
  forecast_units INT,
  model TEXT,            -- "3M_AVG" | "WEIGHTED" | "MANUAL"
  created_at TIMESTAMPTZ
)
```

---

## 5 Pillars of the System

1. **Sales MIS** — Unified sales + returns across every channel. Daily/weekly/monthly reports. Source of truth.
2. **Inventory Management** — Item-level stock at all locations (Own WH, FBA, Blinkit darkstores, Partners). Scan in/out.
3. **Distribution Intelligence** — What to ship where, when. Blinkit darkstore-wise replenishment triggers. FBA replenishment.
4. **Demand Forecasting** — SKU × channel × location demand prediction. Item-level via BOM. Reorder alerts.
5. **Procurement / POs** — Generate purchase orders to suppliers. Never go OOS.

---

## Build Phases (original numbering — superseded by A–G in build_plan.md)

### Phase 1: Foundation — Supabase + Data Model ✅ DONE
### Phase 2: Inventory Core — Scan In/Out + Position Tracking ✅ DONE
### Phase 3: Sales Ingestion — Unified Orders Table → Phase B in active plan
### Phase 4: MCP Server — Claude Desktop Integration → Phase F in active plan
### Phase 5: Demand Forecasting Engine → Phase D in active plan
### Phase 6: API Integrations (Month 2+) → Phase E / future

---

## MCP Tools Planned (Phase F)

| Tool | What it does |
|------|-------------|
| `get_inventory_status` | Current item quantities at all locations + assembable SKU units |
| `get_low_stock_alerts` | Items at or below reorder point, with days-of-stock remaining |
| `get_oos_risk` | SKUs predicted to go OOS within N days based on sales velocity |
| `get_sales_report` | Units + revenue by channel, SKU, date range |
| `get_channel_pnl` | P&L by channel (margin, ACoS, net margin) |
| `forecast_demand` | Predicted units for next 1–3 months by SKU + channel |
| `create_purchase_order` | Draft PO for specified items + quantities → saves to DB |
| `record_stock_movement` | Log a receipt, dispatch, or adjustment |
| `get_po_status` | Open POs, expected delivery dates |
| `add_channel` | Register a new sales channel (Zepto, Instamart, etc.) |

---

## Open Questions (from original plan — most resolved)

1. **Item granularity:** Size variants (e.g., "Bear Cap NB" vs "Bear Cap 3M") — confirm with Shubhra
2. **Supplier list:** Names, contacts, lead times → populated in `suppliers` table ✅
3. **Blinkit dark store locations:** GGN, HYD, BLR — tracked via `partner_location_id` in orders
4. **Peeko/Kiddo model:** Outright — they take physical stock upfront, recorded as TRANSFER_OUT ✅
