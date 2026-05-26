# Phase D — Demand Forecasting Engine

*Plan created: 26-May-2026*

---

## Context

The business needs a 6-month SKU-level demand forecast that can be re-run every 15 days as actuals come in. The primary downstream use is inventory planning: forecast → map to current stock + on-order → determine next PO quantities given supplier lead times (Phase E). The forecast philosophy is **bullish** — stockout is worse than overstock, since excess stock can be liquidated through new channels.

Three channel models are needed:
- **Blinkit**: ADS-driven expansion model (known DS count × P75 of daily demand per DS)
- **Amazon / FnP / FC / Peeko / Ozi**: historical growth model (P75 of observed MoM growth rates applied forward)
- **D2C**: manual input only (no historical data worth extrapolating)

---

## What Already Exists (Reuse These)

| Asset | Location | How it's reused |
|-------|----------|-----------------|
| `demand_forecasts` table | `setup/01_create_tables.sql:316–327` | Already exists, empty. Write `model='VELOCITY_BASE'` for engine output, `model='USER_FINAL'` for locks. UNIQUE on `(sku_id, channel_id, forecast_month)`. |
| `blinkit_performance_ads` | `setup/22_blinkit_replenishment_tables.sql` | Stores **daily** `total_orders` per DS per SKU per day. Has `wh_oos_flag`, `assessment_start`, `assessment_end`. P75 computed from this. |
| `blinkit_ds_sku_eligibility` | same migration | Active/launch_awaited status per DS-SKU pair. |
| `partner_locations` | core schema | DS geography — `city`, `channel_id`, `location_id`. Used to map expansion plan city names → DS counts. |
| `get_orders_raw()` | `tcb/db.py` | Historical orders. Filter by `status IN ('FULFILLED','PENDING')` and date range for velocity. |
| Status constants | `ui/growthspurt_app.py:37–40` | `GROSS_STATUSES`, `NET_STATUSES` — import or replicate. |
| Tab pattern | `ui/growthspurt_app.py` | 7 existing tabs; add tab 8. `load_data()` cached fetch pattern. `st.data_editor` for editable grids. |
| City launch plan | `data/blinkit/manual/City Launch Plan_Blinkit.xlsx` | Per-SKU city lists for Jun–Nov 2026. 10 SKUs: TCB001–006, TCB008–009, TCB011–012. |

---

## Channel Model: Blinkit

**Source of truth for DS count**: the city launch plan Excel, parsed per SKU per month.

**Steps for each (SKU, forecast_month):**

1. **Parse expansion plan**: load `City Launch Plan_Blinkit.xlsx` → `{sku_id: {month_str: [city_list]}}`. Normalize city names (strip whitespace, lowercase for matching). Handle `"All cities"` by querying all Blinkit `partner_locations`.

2. **Get DS list for the month**: query `partner_locations` for all Blinkit DSes in the month's city list. Join to `blinkit_ds_sku_eligibility` for that SKU to get status.

3. **Compute P75 ADS per DS**:
   - For each DS with `status='active'`: query `blinkit_performance_ads` where `wh_oos_flag=False` and `assessment_end = MAX(assessment_end)` for that SKU. Take `PERCENTILE_CONT(0.75)` of `total_orders`. Use P25 as lo, P90 as hi.
   - Minimum data threshold: if a DS has fewer than 5 non-OOS days in the period, use the fallback.
   - **Fallback (launch_awaited or insufficient history)**: use the median of P75 ADS across all currently active DSes for that SKU globally. This assumes new cities will perform at "average active DS" level — consistent with bullish outlook.

4. **Monthly forecast**: `SUM(p75_ads_per_ds) × 30`. lo/hi use P25/P90 respectively.

5. **SKUs not in Blinkit scope** (TCB007 — inactive; TCB010 — no longer planned for Blinkit): exclude from Blinkit forecasting entirely.

6. **Plan vs. live reality**: The expansion plan is a target schedule, not absolute. City matching uses `UNION` logic:
   - **Floor = live DSes in DB**: any city already `active` in `blinkit_ds_sku_eligibility` for that SKU is always included, even if it's ahead of the plan.
   - **Ceiling = plan cities**: cities listed in the plan for a month are added on top.
   - Concretely: `active_cities_for_month = set(plan_cities_for_month) ∪ set(currently_active_cities_in_db)`. This handles both early launches and plan gaps.

---

## Channel Model: Amazon / FnP / FC / Peeko / Ozi

**Steps for each (SKU, channel):**

1. Pull last 4 months of actuals from `orders`: `status IN ('FULFILLED','PENDING')`, grouped by `DATE_TRUNC('month', order_date)`.

2. Compute MoM growth rates: `rate[n] = units[n] / units[n-1] - 1` for consecutive months with non-zero denominators. Skip month pairs where the prior month is 0.

3. **Bullish growth rate** = P75 of observed growth rates. lo/hi = P25/P90.
   - Fallback if < 2 valid growth rate observations: use 15% (configurable constant `DEFAULT_GROWTH_RATE`).

4. Apply forward from last actuals:
   - `M1 = last_month_units × (1 + p75_rate)`
   - `M2 = M1 × (1 + p75_rate)` ... compounding.

5. **FnP note**: if actual MoM growth is very low despite new SKUs being listed, the P75 approach captures this automatically — the 15% floor prevents a zero-growth projection.

---

## Channel Model: D2C

- No computation. All cells are blank/zero until user manually enters and locks.
- Stored as `USER_FINAL` — not generated by the engine.
- Treated the same as other USER_FINAL locks (preserved on re-runs).

---

## Lock / Revision Mechanics

**Model values in `demand_forecasts.model`:**
- `VELOCITY_BASE` — engine output, **always refreshed** on every run regardless of locks
- `USER_FINAL` — user's current judgment; persists until explicitly changed or reset

**On every `generate_base_forecast()` run:**
1. Compute all channel forecasts.
2. Upsert VELOCITY_BASE for **all** (sku_id, channel_id, forecast_month) — no skipping based on USER_FINAL.
3. USER_FINAL rows are untouched.
4. This means: every 15-day run gives you fresh base numbers AND preserved human overrides side by side.

**Coexistence requirement — DB migration needed:**
The current `demand_forecasts` UNIQUE constraint is `(sku_id, channel_id, forecast_month)`, which only allows one row per cell and would block storing both VELOCITY_BASE and USER_FINAL. Fix: drop and replace with `UNIQUE(sku_id, channel_id, forecast_month, model)`.

**Migration file:** `setup/migrations/015_demand_forecasts_unique_model.sql`
```sql
ALTER TABLE demand_forecasts
  DROP CONSTRAINT demand_forecasts_sku_id_channel_id_forecast_month_key;
ALTER TABLE demand_forecasts
  ADD CONSTRAINT demand_forecasts_sku_channel_month_model_key
  UNIQUE (sku_id, channel_id, forecast_month, model);
```
Apply to dev first, test, then Himanshu applies to prod manually.

**Locking in Streamlit (total-SKU level):**
- Streamlit shows two numbers per cell: **Base** (VELOCITY_BASE) and **Forecast** (USER_FINAL if set, else same as base).
- Green highlight when USER_FINAL differs from VELOCITY_BASE — shows where human judgment overrides the model.
- User edits total units for a SKU × Month.
- On lock: distribute total proportionally across channels (using VELOCITY_BASE channel proportions). Upsert/overwrite USER_FINAL rows. Re-locking on the next 15-day run is fine — just overwrites previous USER_FINAL.
- On reset: delete USER_FINAL rows for that (sku, month) → VELOCITY_BASE shows through.

---

## New File: `tcb/forecasting.py`

```python
# Key functions

# --- Blinkit ---
parse_city_launch_plan(path: str) → Dict[str, Dict[str, List[str]]]
  # Reads City Launch Plan_Blinkit.xlsx → {sku_id: {"2026-06": ["Bengaluru", ...], ...}}
  # Normalizes city names. "All cities" → special sentinel.

fetch_blinkit_daily_ads(sku_ids=None) → pd.DataFrame
  # Queries blinkit_performance_ads for latest assessment period per SKU
  # Returns: location_id, sku_id, data_date, total_orders, wh_oos_flag

compute_ds_p75_ads(daily_df: pd.DataFrame) → pd.DataFrame
  # For each (location_id, sku_id): P25/P75/P90 of total_orders on non-OOS days
  # Returns: location_id, sku_id, p25_ads, p75_ads, p90_ads, day_count
  # Computes fallback_ads = median of p75_ads across all DSes for each sku_id

get_ds_for_city_month(sku_id, month_date, city_list, ads_df) → List[dict]
  # Returns DSes with their p75 (or fallback) for the given cities

forecast_blinkit(months=6) → pd.DataFrame
  # Returns: sku_id, channel_id, forecast_month, units, lo, hi

# --- Other channels ---
fetch_historical_monthly_units(lookback_months=4) → pd.DataFrame
  # Queries orders: status IN (FULFILLED, PENDING), last N months
  # Returns: sku_id, channel_id, month (DATE), units

compute_bullish_growth_rates(monthly_df: pd.DataFrame, default_rate=0.15) → pd.DataFrame
  # Returns: sku_id, channel_id, p25_rate, p75_rate, p90_rate

forecast_other_channels(months=6) → pd.DataFrame
  # Returns: sku_id, channel_id, forecast_month, units, lo, hi

# --- Master ---
generate_base_forecast(months=6) → None
  # Calls both models, concatenates, upserts VELOCITY_BASE to demand_forecasts
  # Skips (sku, channel, month) where USER_FINAL exists

get_forecast_display(months=6) → pd.DataFrame
  # Reads demand_forecasts, pivots to SKU × Month (total units, summed across channels)
  # Carries USER_FINAL flag per cell (for color coding)

get_forecast_channel_breakdown(sku_id, months=6) → pd.DataFrame
  # Per-channel breakdown for detail panel

lock_sku_month(sku_id, month_date, total_units) → None
  # Distributes total_units proportionally across channels (by VELOCITY_BASE share)
  # Upserts USER_FINAL rows

reset_sku_month(sku_id, month_date) → None
  # Deletes USER_FINAL rows for this (sku, month) — VELOCITY_BASE shows through
```

---

## Modified File: `ui/growthspurt_app.py`

Add `t8` to the `st.tabs()` call: `"🔮 Forecast"`.

**Tab layout:**

```
┌─────────────────────────────────────────────────────────┐
│ [▶ Regenerate Base Forecast]  Last run: 26-May 12:01    │
├──────────┬──────┬──────┬──────┬──────┬──────┬──────────┤
│ SKU      │ Jun  │ Jul  │ Aug  │ Sep  │ Oct  │ Nov      │
│          │ 2026 │ 2026 │ 2026 │ 2026 │ 2026 │ 2026     │
├──────────┼──────┼──────┼──────┼──────┼──────┼──────────┤
│ TCB001   │  240 │  310 │  420 │  580 │  720 │  900     │
│ TCB005   │  180 │  230 │  ...                           │
│  ...                                                    │
├──────────┴──────┴──────┴──────┴──────┴──────┴──────────┤
│ [🔒 Lock Row]  [↩ Reset Row]  [⬇ Download Excel]       │
├─────────────────────────────────────────────────────────┤
│ ▶ Channel breakdown for selected SKU                    │
│   Blinkit: 180 | Amazon: 40 | FnP: 12 | FC: 8 | ...   │
└─────────────────────────────────────────────────────────┘
```

- Table uses `st.data_editor` with numeric columns. Gray background = VELOCITY_BASE; green = USER_FINAL (via `column_config` styling or row annotation).
- Row selection via `st.data_editor` selection column → populates lock/reset targets.
- Expander shows per-channel breakdown for selected SKU (read-only).

---

## Excel Output

Generated via `openpyxl` on "Download" button click. Three sheets:

| Sheet | Content |
|-------|---------|
| `Summary` | SKU × Month totals (all channels summed). USER_FINAL cells highlighted green. |
| `Channel Breakdown` | SKU × Channel × Month. Shows VELOCITY_BASE and USER_FINAL model label. |
| `Assumptions` | Blinkit P75 ADS per DS per SKU. Growth rates per channel per SKU. DS counts per month per SKU. |

---

## DB Migration Required

One migration (`setup/migrations/015_demand_forecasts_unique_model.sql`) drops the old unique constraint and adds a new one that includes `model`. This is the only schema change. The table itself already exists.

---

## Build Order

1. `tcb/forecasting.py` — write and test all functions against dev DB
2. Verify: run against dev, check row counts in `demand_forecasts`, spot-check Blinkit P75 values manually against raw data
3. `ui/growthspurt_app.py` — add Forecast tab (read-only first, then add lock/reset)
4. Add Excel download
5. Run against prod, screenshot the Forecast tab

---

## Verification Checklist

- [ ] Migration 015 applied to dev; constraint change confirmed in `\d demand_forecasts`
- [ ] `python tcb/forecasting.py` completes without error, prints per-SKU per-channel summary
- [ ] `demand_forecasts` in dev DB: VELOCITY_BASE rows for 10 Blinkit SKUs × 6 months; remaining channels × 12 SKUs × 6 months
- [ ] TCB007 and TCB010 absent from Blinkit rows
- [ ] Blinkit forecast for TCB001 June > current monthly orders (expansion reflected)
- [ ] Re-running `generate_base_forecast()` a second time: VELOCITY_BASE values updated; any existing USER_FINAL rows untouched and still present
- [ ] Streamlit: Forecast tab visible; "Base" and "Forecast" columns per month; both numbers visible
- [ ] Edit a cell → Lock → re-query DB: USER_FINAL rows present alongside VELOCITY_BASE for same month
- [ ] Re-run engine → USER_FINAL rows preserved, VELOCITY_BASE refreshed
- [ ] Re-lock with different number → USER_FINAL overwritten with new value
- [ ] Reset → USER_FINAL rows deleted, VELOCITY_BASE shows through
- [ ] Excel download: 3 sheets, numbers match Streamlit display
- [ ] `pytest tests/` passes (no regressions)

---

## Out of Scope (Phase E, not this phase)

- Mapping forecast → inventory gap analysis
- PO quantity suggestions
- Vignesh `forecast_demand` MCP tool (add after forecast table is stable)
