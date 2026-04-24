# The Cradle Box — Demand Planning System
## Project Context & Objectives

**Company:** Goodsense Trading India Private Limited (Brand: The Cradle Box)
**GSTIN:** 29AALCG8970F1Z0 | **PAN:** AALCG8970F
**Registered Address:** No. 2731, First Floor, HAL 3rd Stage, New Thippasandra, Bengaluru, Karnataka - 560075

---

## What We Are Building

An end-to-end, agentic demand planning and operations system. The north star: **never go out of stock, on anything, ever** — while keeping operations lean, data-driven, and mostly automated.

---

## Objectives

### a. Demand Forecasting + Item-Level Purchase Orders
- Forecast SKU-level demand by channel (Amazon FBM, Blinkit, FnP, FC, D2C, etc.)
- Convert SKU forecasts to item-level demand via BOM (Bill of Materials)
- Auto-generate purchase orders to suppliers at the item level
- Track reorder points, safety stock, and supplier lead times
- Store forecasts in DB; refresh weekly

### b. Sales Recording + MIS Reporting
- Unified orders table across all channels (Amazon, Blinkit, FnP, First Cry, Peeko, Ozi, Kiddo, D2C)
- Daily/weekly/monthly MIS: units sold, gross revenue, net margin by channel and SKU
- Returns and RTOs tracked separately, reconciled against orders
- Source of truth for all financial and operational reporting

### c. Inventory Management
- **Two-layer model:**
  - Loose item inventory (raw items + packaging, unpacked)
  - Assembled SKU inventory (packed hampers, ready to ship)
- **All movement types tracked:**
  - Inward: supplier receipts (batch-wise, FIFO costing)
  - Assembly: items consumed → SKU packed
  - Outward sales: direct order fulfillment
  - Outward stock transfers: to FBA, Blinkit darkstores, partner WHs (Peeko, Kiddo)
  - RTOs (Return to Origin): stock back from courier
  - Sale Returns: customer-initiated returns
  - Damage write-offs and adjustments
- Location-aware: OWN_WH, FBA, Blinkit darkstores, partner darkstores
- Streamlit UI for scan in / scan out operations

### d. Agent-like Behaviour (Claude Desktop + MCP)
- Claude Desktop connected via FastMCP server
- Ask open-ended questions: "What will go OOS first?", "Draft a PO for next month", "What's my Blinkit margin this week?"
- Claude has access to all DB views and can take actions (create POs, log adjustments, generate invoices)
- Designed for ongoing collaboration — not just reporting, but joint problem-solving

### e. API Integrations + Automation
- **Phase 1 (now):** Manual CSV uploads for all channels
- **Phase 2:**
  - Amazon SP-API: auto-pull orders, FBA inventory, Search Term Reports
  - Blinkit: scraping/download scripts for sales + darkstore inventory reports
  - FnP, First Cry: CSV-based ingestion scripts
- **Phase 3:**
  - Supabase Edge Functions for real-time reorder alerts
  - Scheduled weekly forecast refresh
  - WhatsApp/push alerts for low stock and OOS risk

---

## Tech Stack

| Layer | Tool |
|-------|------|
| Database | Supabase (PostgreSQL) |
| Backend | Python (supabase-py, pandas, openpyxl) |
| Inventory UI | Streamlit |
| Agent Interface | Claude Desktop + FastMCP |
| Scheduling | Python `schedule` / Supabase Edge Functions |
| APIs | Amazon SP-API, Blinkit scraper |

---

## Data Model — Key Concepts

**3-layer product hierarchy:**
- Items (raw components) + Packaging → assembled into SKUs via BOM

**Batch tracking:**
- Every supplier receipt = one batch (code = YYYYMMDD)
- Each batch has its own cost_per_unit
- Inventory tracked at batch level, dispatched FIFO

**Channel business models:**
- DROP_SHIP: Amazon FBM, FnP, First Cry (we ship to end customer)
- FBA: Amazon FBA (Amazon fulfills)
- SOR: Blinkit, Ozi (sale-or-return, they hold stock)
- OUTRIGHT: Peeko, Kiddo (we invoice upfront, they sell from their darkstores)
- DIRECT: Own Website (we ship from OWN_WH)

**SKU Pricing model:**
- **MRP** — Maximum Retail Price, SKU-level, same everywhere. Stored in `sku_pricing`.
- **SP (Selling Price)** — uniform minimum price across all channels. Stored in `sku_pricing` alongside MRP. Effective-dated to track price changes over time.
- **TP (Transfer Price)** — fixed per-unit payout agreed with select partners. Stored in `sku_channel_tp` (SKU × channel). Only for: FnP, Peeko, Kiddo, First Cry, Ozi.
  - These 5 channels pay us exactly TP per unit — no further deductions
  - Amazon and Blinkit have NO TP — they deduct tax, commission, storage, discounts from SP and remit the net. Their payout is computed in P&L views.

**COGS model:**
- COGS is NOT a static number on a SKU. It is batch-derived and varies with every assembly run.
- **`v_sku_live_cogs`** (view) — forward-looking estimate: computes COGS dynamically from BOM × current batch costs. Used for planning and reorder decisions.
- **`sku_inventory_transactions.unit_cogs`** — actual COGS locked in at the moment of assembly, based on which batches (FIFO) were consumed. Used for accurate P&L reporting.
- There is no static `cogs` field on SKUs or pricing tables — all COGS is derived from item batch costs.

---

## Project Directory
```
C:\01Claude\projects\DemandPlanning\
├── setup/          # SQL migrations + seed scripts (01–13)
├── tcb/            # Python modules (db.py, inventory.py, forecast.py)
├── ingest/         # Channel-specific sales ingestion scripts
├── ui/             # Streamlit inventory app
├── mcp/            # FastMCP server for Claude Desktop
├── master files/   # Source Excel files (Item-Packaging-SKU mapping.xlsx, etc.)
└── .env            # Supabase credentials (not committed)
```

---

*Last updated: April 2026*
