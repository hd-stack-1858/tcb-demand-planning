# Plan: Blinkit Replenishment Model (Phase H)

**Generated:** 2026-05-20 | **Updated:** 2026-05-21  
**Design doc:** `docs/blinkit_replenishment.md` (full detail)

---

## Context

The Cradle Box runs Blinkit replenishment manually today — 6 steps across multiple browser tabs, gut-feel velocity, ~2 hours per replenishment run. Now operating in 6-7 cities with 12 planned by June end. Supply restock arriving mid-June — model must be ready before inventory lands.

Formula: `units_to_ship = max(0, ADS_per_DS × active_DS_count × 30 days − (units_wh + units_incoming))`  
Minimum gate: ₹2L invoice value. Below this, defer or batch.

---

## Approach

Three-layer build:
1. **Data layer** — performance ADS + inventory snapshots into Supabase; DS master into `partner_locations`
2. **Engine layer** — `tcb/replenishment.py` module computes the plan
3. **Output layer** — pre-formatted Excel for Blinkit portal import

---

## Key Design Decisions (from schema analysis session 2026-05-21)

**ADS is a daily metric, not cycle-level constant.** Each row in the performance detail file represents one day's ADS for one DS-SKU. ADS varies day-to-day as orders come in.

**ADS formula (Option C):**  
`ADS = SUM(total_orders WHERE NOT wh_oos_flag) / COUNT(days WHERE NOT wh_oos_flag)`  
within the latest available assessment period for that sku_id (open cycle OK to use).

**Three ADS states:**
- `ads_units = NULL` + `wh_oos_flag = TRUE` → WH was OOS that day — EXCLUDE from ADS calculation
- `ads_units = 0` + `wh_oos_flag = FALSE` → DS in stock, no sale — counts as zero-sales day (denominator ++)
- `ads_units > 0` → actual sale occurred

**Each SKU has its own assessment cycle.** Do not assume one SKU's cycle applies to others.

**Daily download required.** Blinkit does not allow retroactive access to past performance data. The detail CSV must be downloaded every day to capture historical ADS. A daily Playwright scraper is needed.

**WH name matching for performance file:** Performance "Serving warehouse" is text (no Facility ID). Match to `partner_locations.name` via loader-level normalization (strip "- Feeder" suffix, fuzzy match). Raise error if no match found.

**Farukhnagar SR:** Marked `is_active=FALSE` in `partner_locations`. Skip entirely — SOH inventory merged into Faridabad WH at loader level.

---

## Critical Files

| File | Action |
|------|--------|
| `setup/22_blinkit_replenishment_tables.sql` | ✅ Written — migration with 5 new tables |
| `ingest/blinkit_performance_loader.py` | NEW — historical + daily incremental loader |
| `ingest/blinkit_inventory_loader.py` | NEW — SOH snapshot loader (run on replen day) |
| `automation/blinkit_performance_scraper.py` | NEW — daily Playwright scraper for performance detail CSV |
| `tcb/replenishment.py` | NEW — recommendation engine + Excel output |
| `ui/tinysteps_app.py` | Add Replenishment tab (deferred until CLI validated) |

---

## Data Model (actual tables in migration 22)

```
partner_locations (existing)
  WH rows: location_type='WH', external_id=Blinkit WH Facility ID
  DS rows: location_type='DARKSTORE', external_id=Blinkit Outlet ID, parent_location_id=WH
  Farukhnagar SR: is_active=FALSE (updated in migration 22)

blinkit_ds_sku_eligibility  [PRIMARY KEY: (location_id, sku_id)]
  status: active | launch_awaited | darkstore_closed | sku_moved_out_low_sales
          | sku_city_exited | sku_recalled
  Updated by performance loader — two-pass: (1) all rows for status, (2) Y-rows for ADS

blinkit_performance_ads  [UNIQUE: (data_date, location_id, sku_id)]
  One row per day × DS × SKU from performance detail CSV (Y-rows only)
  Key columns: ads_units, total_orders, wh_oos_flag, assessment_start/end, download_date
  Index on (sku_id, location_id, data_date DESC) for engine queries

blinkit_inventory_snapshots  [UNIQUE: (snapshot_date, location_id, sku_id)]
  One row per snapshot × WH × SKU from SOH file
  Effective WH stock = units_wh + units_incoming (prevents double-shipping)

blinkit_performance_summary  [UNIQUE: (assessment_start, assessment_end, sku_id)]
  SKU-level aggregate per cycle from summary CSV. Not in replenishment formula.

blinkit_ageing_snapshots  [PK: (report_date, location_id, sku_id, inventory_type, age_slab)]
  Deferred — table created, loader to be built after ageing recall rule is defined.
  Frontend=DS shelf, Backend=WH-level at DS.
  Flag: >60 days stable/growing units → "Consider recall" in replenishment output.
```

---

## Engine Logic (`tcb/replenishment.py`)

```python
def compute_replenishment_plan(snapshot_date=None, coverage_days=30, min_invoice_value=200_000):
    # For each SKU × WH combination:
    # 1. Get active DS for this WH: partner_locations WHERE parent_location_id=WH AND is_active
    #    INNER JOIN blinkit_ds_sku_eligibility WHERE status='active'
    # 2. For each active DS-SKU: compute ADS from blinkit_performance_ads
    #    ADS = SUM(total_orders WHERE NOT wh_oos_flag) / COUNT(days WHERE NOT wh_oos_flag)
    #    using latest available assessment period data
    # 3. ADS_sum = SUM(ADS per active DS) for this WH-SKU
    # 4. target_stock = ADS_sum × coverage_days + transit_buffer (7 days)
    # 5. effective_stock = units_wh + units_incoming from latest inventory snapshot
    # 6. units_to_ship = max(0, target_stock - effective_stock)
    # 7. Flag wh_oos rows in output as "Priority — WH was dry"
    # 8. invoice_value = units_to_ship × SP (from sku_channel_sp)
    # Returns DataFrame + ₹2L gate check
```

---

## Build Phases

| Phase | Task | Status |
|-------|------|--------|
| 1 | SQL migration `22_blinkit_replenishment_tables.sql` | ✅ Done |
| 2 | Populate DS master in `partner_locations` (from ageing Outlet IDs + performance WH→DS mapping) | ✅ Done (`setup/gen_ds_seed.py` → `seed_blinkit_ds_master.sql`) |
| 3 | `ingest/blinkit_performance_loader.py` — historical load of existing CSVs, then incremental | ✅ Done |
| 4 | `ingest/blinkit_inventory_loader.py` — SOH loader with Farukhnagar merge logic | ✅ Done |
| 5 | `automation/blinkit_performance_scraper.py` — daily Playwright download | ✅ Done (saves to `data/blinkit/auto/product_performance/detail/`) |
| 6 | `tcb/replenishment.py` — engine + Excel output | ✅ Done |
| 7 | Streamlit tab in `ui/tinysteps_app.py` | After CLI validated against prod data |
| 8 | Invoice + e-way bill automation | When shipping weekly to 3+ WHs |

**Remaining before prod:**
- Apply migration 22 + DS seed SQL to prod (user runs manually in Supabase)
- Load historical performance CSVs: `python ingest/blinkit_performance_loader.py`
- Load today's SOH: `python ingest/blinkit_inventory_loader.py`
- Run engine: `python tcb/replenishment.py --dry-run`
- Verify output against last manual replenishment decision (within ~20%)
- Get May 16-31 ageing report to resolve 7 DS with NULL external_id

---

## Verification Checklist (before first production run)

1. DS master: verify DS count per WH matches Blinkit portal manually for 2 WHs
2. Performance load: row count matches source CSVs; spot-check ADS for 2-3 DS-SKUs
3. Inventory load: spot-check units_wh + units_incoming for 2-3 SKUs vs Blinkit portal
4. Engine output: compare replenishment plan to last manual decision for Bangalore — must be within ~20%
5. WH OOS flag: confirm "Insufficient Inventory" rows flagged as priority in output
6. ₹2L gate: confirm it fires correctly on a below-threshold test scenario
7. Multi-WH city (Bangalore has B3 + B5): confirm each WH gets separate plan row
