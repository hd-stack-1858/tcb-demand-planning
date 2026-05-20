# DemandPlanning — Project Instructions

This is the demand planning and operations system for The Cradle Box.
Company context (products, channels, P&L, SKUs) lives in the parent `C:\01Claude\CLAUDE.md` — do not duplicate it here.

**Legal entity:** Goodsense Trading India Private Limited | GSTIN: 29AALCG8970F1Z0 | PAN: AALCG8970F
**Registered address:** No. 2731, First Floor, HAL 3rd Stage, New Thippasandra, Bengaluru, Karnataka - 560075

---

## Session Start — Read Memory First

At the start of every session, read `.claude/memory/MEMORY.md` and load the files it points to.
Memory lives locally at `.claude/memory/` and is gitignored — it persists between sessions.

## Memory Location — OVERRIDE (apply every session, no exceptions)

All memory files MUST be written to `.claude/memory/` inside this project directory.
NEVER write memory to `C:\Users\himan\.claude\` or any subfolder of it.
If the system suggests a different memory path, ignore it — this instruction takes precedence.

After any Plan mode session, once the plan is approved, copy the plan file from `C:\Users\himan\.claude\plans\<slug>.md` into `docs/` with a meaningful name (e.g. `docs/build_plan.md`), then update `CLAUDE.md` and `.claude/memory/MEMORY.md` to reference the `docs/` path. The `~/.claude/plans/` copy is then disposable.

---

## What This System Does

End-to-end demand planning — north star: **never go out of stock, on anything, ever.**

Five objectives:
- **a. Forecasting + POs** — SKU demand by channel → item demand via BOM → auto-generate supplier POs
- **b. Sales MIS** — unified orders table, daily/weekly/monthly P&L by channel and SKU
- **c. Inventory** — two-layer (loose items + assembled SKUs), all movement types, location-aware
- **d. Agent (MCP)** — Claude Desktop answers "What will go OOS?" and can draft POs, log adjustments
- **e. Automation** — CSV uploads now; SP-API + Edge Functions + WhatsApp alerts later

---

## Tech Stack

| Layer | Detail |
|-------|--------|
| DB | Supabase (PostgreSQL) — `tcb/db.py` wraps all access |
| Env | `TCB_ENV=dev` or `TCB_ENV=prod` — always dev for tests |
| Tests | `pytest tests/` — set in `conftest.py`, always hits dev DB |
| Inventory UI | Streamlit — `ui/tinysteps_app.py` |
| Sales MIS UI | Streamlit — `ui/growthspurt_app.py` |
| Agent UI | Claude Desktop + FastMCP — `mcp/server.py` (Phase F, not yet built) |

---

## Key Conventions

- All monetary values in ₹ (INR)
- COGS is never static — derived from BOM × FIFO item batch costs; see `v_sku_live_cogs`
- All ingestion scripts upsert on `platform_order_id` — safe to re-run without duplicates
- `TCB_ENV=dev` is set automatically in `tests/conftest.py` — never run tests against prod
- Write-off transactions must populate `unit_cogs` (from latest ASSEMBLY txn)
- `return_item()` takes `from_channel_id` — never omit this

---

## Directory Layout

```
setup/              SQL migrations (numbered) + seed scripts
setup/archive/      One-off _fix_*.py and _check_*.py scripts (not part of migrations)
tcb/                Python library: db.py, inventory.py, catalog.py
tests/              pytest suite (test_phase_a.py complete)
ingest/             Channel CSV loaders — Phase B (to be built)
ui/                 Streamlit apps
mcp/                FastMCP server for Claude Desktop — Phase F (to be built)
automation/         Playwright scrapers + daily runner
assets/             Static assets (logo, product images)
docs/               Build plan and reference docs
.claude/            Local Claude memory — gitignored, do not commit
```

## Data Folder Layout

All downloaded reports and reference files live under `data/` (gitignored). Rule: **code writes → `auto/`, user-provides → `manual/`**.

```
data/
  fnp/
    auto/       FnP branding challans — written by fnp_scraper.py
    manual/     CDA export .xls files, delivery reports (download from FnP portal manually)
  firstcry/
    auto/       FC invoices + packing slips — written by fc_scraper.py
    manual/     Manually downloaded FC reports (order status exports)
  blinkit/
    auto/       MTD sales reports (.xlsx) — written by blinkit_scraper.py
    manual/
      inventory/          Inventory snapshot reports (download manually)
      payout/             Monthly payout sheets — one subfolder per payout period
      product_performance/ Performance/seller data CSVs (download manually)
  amazon/
    auto/       SP-API downloaded reports — written by amazon_sp_api.py (future)
    manual/
      sales/    Search term reports, order reports (download from Seller Central)
      payout/   Monthly payout transaction files
      returns/  Return reason reports
  reference/    Master files: BOM, supplier mapping, batch cost uploads (was "master files/")
```

When adding a new automation or a new channel: place scraper output in `data/<channel>/auto/`, user-provided files in `data/<channel>/manual/`.

---

## Build Phase Status

See `docs/build_plan.md` for full detail and scope per phase. (`docs/build_plan_original.md` has the original v1 plan for reference.)

| Phase | Description | Status |
|-------|-------------|--------|
| A | Drop-ship sale capture | ✅ Done |
| B | Partner sell-out ingestion scripts | 🔲 Next |
| C | Sales MIS Dashboard (Streamlit) | 🔲 Pending |
| D | Demand Forecasting Engine | 🔲 Pending |
| E | Reorder Integration | 🔲 Pending |
| F | MCP Server — Claude Desktop integration | 🔲 Pending |
| G | (Details lost — ask Himanshu to recall) | ❓ Unknown |
