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

## Blinkit Replenishment System — Key Rules

Phase H is implemented. Core files: `tcb/replenishment.py` (engine + Excel), `ingest/blinkit_performance_loader.py` (DS master + ADS loader), `ingest/blinkit_inventory_loader.py` (SOH snapshot), `automation/blinkit_performance_scraper.py` (daily Playwright download).

### Blinkit Performance Detail Report — the most important Blinkit data source

The **Performance Detail report** (`blinkit_performance_detail` table) feeds nearly every Blinkit process: WH-level COGS finalization (G2c), demand/ADS calculation, the replenishment plan, and DS eligibility status. Before touching any of those, read the full column-by-column reference in memory: `.claude/memory/blinkit_perf_detail_columns.md` (APPROVED 2026-06-18).

Two corrections to keep in mind so old assumptions don't creep back in:
- `Considered for assessment (Y/N)` is the **primary eligibility gate** — a dark store-SKU-date with `Considered=N` is excluded entirely from ADS and replenishment, not just treated as a zero-sales day.
- The WH-out-of-stock signal does **not** come from text-matching the Remarks column ("Insufficient Inventory at warehouse for transfers" is not parsed). It comes from `Considered=Y AND Available=0` rows, surfaced as a stock-out-days count per WH/SKU in the replenishment plan.

### Blinkit Seller Process (must understand before touching this system)

Launching a SKU in a new city is a **3-step gate**:
1. **Blinkit panel activation** — Himanshu activates the city/DS in the Blinkit seller panel. Until this happens, Blinkit will NOT send stock to that city's dark stores, even if the WH has it.
2. **WH stocking** — Ship stock to the supplying WH.
3. **DS distribution** — Blinkit distributes from WH to activated dark stores automatically.

`ds_not_launched` (status = `launch_awaited`) means step 1 has not been done. Do NOT recommend shipping stock to serve these DS until panel activation is confirmed. Flag them as "Action needed: activate city in Blinkit panel" — not as a pure stock shortage.

### DS Eligibility Status Taxonomy

All status values come from the `Darkstore remark` column in the performance CSV (mapped by keyword rules in the loader):

| Status | Meaning | Include in ADS? |
|--------|---------|----------------|
| `active` | DS selling the SKU (`Considered for assessment = Y`) | Yes |
| `launch_awaited` | City not activated in Blinkit panel | No |
| `darkstore_closed` | Physical store closed (per-SKU-DS — only set if SKU was live there) | No |
| `sku_moved_out_low_sales` | SKU redistributed out due to low sales | No |
| `sku_city_exited` | SKU pulled from that city entirely | No |
| `sku_recalled` | SKU recalled | No |

`darkstore_closed` is recorded per SKU-DS pair, not per DS. If a store closes and a SKU was never listed there, no `darkstore_closed` row exists for that pair — it simply has no eligibility record.

### ADS Formula

`ADS per DS = SUM(total_orders on non-OOS days) / COUNT(non-OOS days)` within the latest assessment period for that SKU.

Three states:
- `wh_oos_flag = True` → WH was dry that day → **exclude from denominator AND numerator**
- `wh_oos_flag = False, orders = 0` → in-stock, no sale → counts as zero-sale day (denominator++)
- `wh_oos_flag = False, orders > 0` → normal sale day

**WH-OOS blind spot:** If a WH has been out of stock for the entire assessment period, ADS=0 and target_stock=0 — but this means we've never given the WH stock to sell, not that demand is zero. Hyd H3 exhibits this. Requires manual attention or city-average fallback (not yet implemented).

### Replenishment Formula

```
target_stock = total_ads × (coverage_days + transit_buffer) = total_ads × 37
units_to_ship = max(0, target_stock − effective_stock)
effective_stock = wh_soh + units_incoming + units_in_transit
```

- Coverage = 30 days, transit buffer = 7 days
- Gate = ₹1.5L invoice value **per WH** (not aggregate)
- Output: `data/blinkit/auto/replenishment/replenishment_plan_YYYYMMDD.xlsx` (5 sheets: Overview-SKU, Overview-WH, Ship Now, Full Plan, Summary)

### Performance Data Rules

- **Daily download is important** — Blinkit does not expose arbitrary historical data. A missed day is recoverable as long as the SKU's current assessment window still includes that date. It becomes permanently unrecoverable only if that SKU's assessment period ends before you re-run. Run daily; a missed run can usually be recovered same-day or next morning.
- Performance CSV lives in `data/blinkit/manual/product_performance/` (downloaded manually or via `automation/blinkit_performance_scraper.py`)
- DS master is auto-refreshed from CSVs on every loader run (Pass 0a) — new DS are seeded, `is_active` is synced from latest file
- **ES numbers are NOT globally unique across cities** — e.g. ES7 exists in both Faridabad and Kochi. DS unique codes use MD5 hash of full name, not ES number alone.

### WH-Level COGS Finalization (G2c — agreed Jun 2026, not yet built)

**State-level FIFO is SUPERSEDED.** It caused cross-WH lot attribution drift (e.g. Mumbai orders consuming Pune lots because both are Maharashtra). Do not extend state-level consumption.

**New design:** Daily join of two reports at `(sku_id, customer_city, date)`:
1. MTD sales report → order count by SKU + customer city
2. Performance detail (`blinkit_performance_detail`) → WH attribution by `serving_wh` per city

Result: each DELIVERED order is attributed to a specific WH → consume that WH's FIFO lot.

**Mismatch rule:** If sales count ≠ perf detail count for any (sku, city, date) → hold COGS finalization for those units + email Himanshu. Never partially finalize.

**Missing performance data:** If G5 (performance scraper) fails → hold ALL COGS finalization for that day + email alert. Payout backstop catches deferred days at payout time (uses state-level as last resort).

**Job order:** G5 (performance scraper, 7-8 min) must complete → then G2c (WH-level finalization).

**WH names:** `partner_locations.name` exactly matches `serving_wh` in performance detail after migration 024. Keep in sync if Blinkit renames any WH.

**Baseline:** K1b resets lots = SOH before Jun 19. New system starts clean from Jun 19.

### WH Geography (Blinkit)

| WH Code | WH Name (exact, matches serving_wh) | Key Cities Served |
|---------|---------|-------------------|
| BLK_WH_1873 | Bengaluru B3 - Feeder | Bengaluru + Ballari, Bidar, Hosur, Kurnool (outlying) |
| BLK_WH_5397 | Bengaluru B5 - Feeder | Bengaluru + all South India: Kochi, Coimbatore, Mysore, Mangaluru, Trivandrum, Davanagere, Manipal, Chikkamagaluru |
| BLK_WH_2681 | Coimbatore C1 - Feeder | Coimbatore (also partially served by B5) |
| BLK_WH_5096 | Faridabad - Feeder | Faridabad + NCR south |
| BLK_WH_2010 | Kundli - Feeder | NCR north/Haryana |
| BLK_WH_2576 | Noida N1 - Feeder | Noida/UP |
| BLK_WH_3201 | Hyderabad H3 | Hyderabad + surrounding AP/Telangana |

WH name → code resolution lives in `ingest/blinkit_wh_resolver.py` (`WH_MANUAL_OVERRIDES`, shared by the performance loader, SOH loader, and replenishment engine). New WHs are auto-created from the performance detail file — see `docs/plans/humble-questing-graham.md`.

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
| H | Blinkit Replenishment Model | 🔲 Next — see `docs/blinkit_replenishment.md` |

---

## DB Change Workflow — MANDATORY

Follow this exact sequence for **any** work that touches DB schema or data:

### Step 1 — Sync dev to prod before starting
```
python setup/sync_dev_to_prod.py
```
Always run this first. Dev may have drifted from prod (stale stock values, missing rows, schema gaps). Syncing ensures dev is a faithful copy of prod before any new work begins.

### Step 2 — Make all schema changes in dev first
- New tables, columns, constraints, indexes → apply to dev via psycopg2 (see [[feedback-dev-db-direct-access]])
- Write the migration SQL in `setup/migrations/NNN_name.sql` (next sequential number)
- Test all code against dev (`TCB_ENV=dev`) until the feature works end-to-end

### Step 3 — Himanshu applies the migration to prod manually
- Share the `setup/migrations/NNN_name.sql` file with Himanshu
- Himanshu runs it in the Supabase prod SQL editor
- **Claude never touches prod DDL** — not via MCP, not via psycopg2, not via Supabase client

### Step 4 — Push code
- Commit code changes + the migration file together
- `git push origin main` → Streamlit Cloud auto-deploys

### Why this order matters
- Dev sync first prevents "works on my machine" bugs where dev schema is behind prod
- Dev-first schema means prod never sees untested DDL
- Himanshu controls the prod apply so there's always a human sign-off before prod changes

---

## DB State Verification Standard — MANDATORY

When investigating data discrepancies or answering "why does X show Y?":

1. **Query first, explain second.** Never state a specific count, status, or DB value as fact without running a query. Reasoning from code logic is a hypothesis.
2. **Label every claim clearly:**
   - `[QUERIED]` — I ran the query and confirmed this
   - `[CODE REASONING]` — I'm inferring from code logic, not verified in DB
   - `[HYPOTHESIS]` — I believe this is true but need a query to confirm
3. **One query beats three rounds of reasoning.** If a discrepancy needs investigation, run a targeted query immediately rather than speculating across multiple turns.
4. **When uncertain, say so.** "I believe X based on the code, but I need to query to confirm" is the correct form. Confidently wrong is worse than flagged uncertainty.
5. **After being wrong once, always query before the next claim** — do not try to reason your way out of a wrong answer.

---

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
