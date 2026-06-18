# Blinkit Replenishment Engine
## How We Decide What to Ship, and Where

---

## The One Question We're Answering

> **"How many units of each SKU should I ship to each Blinkit warehouse this week?"**

We answer this every time we run the replenishment plan. The output is a shipping manifest: warehouse by warehouse, SKU by SKU, with an invoice value check so we never ship a trickle.

---

## How Blinkit's Supply Chain Works

Before the math, the geography matters.

```
YOUR OFFICE / 3PL
       |
       |  (you ship here)
       v
  WAREHOUSE (WH)          ← The Cradle Box ships to this level
  e.g. Bengaluru B3
       |
       |  (Blinkit distributes automatically)
       v
  DARK STORES (DS)         ← Where customers actually order from
  e.g. ES25 Indiranagar
  e.g. ES31 Koramangala
  e.g. ES41 HSR Layout
  (10–25 dark stores per WH)
```

**You never ship directly to dark stores.** You ship to the WH. Blinkit moves stock from WH → DS on their own cadence. Your job is to keep the WH stocked.

---

## The 7 Warehouses We Plan For

| WH Code | WH Name | Key Cities |
|---------|---------|-----------|
| BLK_WH_1873 | Bengaluru B3 | Bengaluru, Hosur, Kurnool |
| BLK_WH_5397 | Bengaluru B5 | South India: Kochi, Coimbatore, Mysore, Mangaluru, Trivandrum |
| BLK_WH_2681 | Coimbatore C1 | Coimbatore |
| BLK_WH_5096 | Faridabad | Faridabad, NCR south |
| BLK_WH_2010 | Kundli | NCR north, Haryana |
| BLK_WH_2576 | Noida N1 | Noida, UP |
| BLK_WH_3201 | Hyderabad H3 | Hyderabad, AP, Telangana |

---

## Step 1 — Measure Daily Sales Rate (ADS)

ADS = **Average Daily Sales per Dark Store**, computed over the most recent 30 days.

We pull this from Blinkit's daily performance report (the CSV you download each morning and the scraper saves automatically).

### The Raw Formula

```
raw_ADS  =  orders on available days
            ─────────────────────────
             count of available days
```

**"Available day"** = a day when Column Q in the performance CSV showed inventory was present at that dark store.

We only divide by days the SKU was actually in stock. If a DS was OOS for 20 of 30 days, we divide by 10, not 30 — because we're measuring selling velocity, not penalising OOS.

### But What About OOS Days?

If a DS ran out of stock for 10 days, those days had zero recorded orders — but demand didn't disappear. Customers just couldn't buy.

We **impute** missing demand for OOS days:

```
imputed_ADS  =  (raw_ADS × avail_days)  +  (P75 × oos_days)
                ─────────────────────────────────────────────
                                   30
```

**P75** is the 75th percentile ADS across all reliable dark stores for that SKU in the same city. If no city data exists (e.g. a brand-new city), it falls back to the global P75 across all cities.

**Why P75, not average?** It's mildly bullish — assumes OOS days had at least median+ demand. Better to ship slightly more than to go OOS.

### Reliability Gate

A dark store must have **at least 5 available days** in the 30-day window to be counted as a reliable data point for P75 computation. Stores with fewer days are imputed using the city/global P75 but don't influence it.

---

## Step 2 — Aggregate to WH Level

For each WH × SKU pair:

```
total_ADS  =  SUM of imputed_ADS across all active, eligible DSes under that WH
```

**Eligible** means the dark store has status = `active` in our eligibility table. We exclude:

| Status | What It Means | Included? |
|--------|--------------|-----------|
| `active` | DS selling the SKU | Yes |
| `launch_awaited` | City not yet activated in Blinkit panel | No |
| `darkstore_closed` | Physical store shut | No |
| `sku_moved_out_low_sales` | SKU redistributed out by Blinkit | No |
| `sku_city_exited` | SKU pulled from city entirely | No |
| `ds_choked` | DS throttled by Blinkit | Counted but flagged |

---

## Step 3 — Compute Target Stock

```
target_stock  =  total_ADS  ×  (coverage_days + transit_buffer)
              =  total_ADS  ×  (30 + 7)
              =  total_ADS  ×  37
```

| Parameter | Value | Reasoning |
|-----------|-------|-----------|
| Coverage days | 30 | Monthly shipping cadence — one shipment covers one month |
| Transit buffer | 7 | In-transit safety stock — stock is en route and not yet in WH |

### The Floor Rule

If a SKU is newly launched or has been OOS so long that its computed ADS is near zero, the formula would give a dangerously low target stock — potentially zero, meaning we'd never seed the WH.

**Floor:** `target_stock = max(computed_target, active_DS_count)`

This guarantees at least 1 unit per active dark store, so live stores never starve.

---

## Step 4 — Subtract Effective Stock

We don't ship what we already have:

```
effective_stock  =  units_wh  +  units_incoming  +  units_transit  +  units_ds
```

| Component | What It Is |
|-----------|-----------|
| `units_wh` | On WH shelf right now |
| `units_incoming` | Dispatched from your location, not yet received |
| `units_transit` | In WH → DS pipeline |
| `units_ds` | Already on DS shelves |

```
units_to_ship  =  max(0,  target_stock  −  effective_stock)
```

---

## Step 5 — The ₹1.5 Lakh Gate

We only actually ship to a WH if the total invoice value of the shipment crosses **₹1,50,000**.

Below this threshold: `DEFER` — accumulate more SKUs or wait until the next cycle.

This prevents sending small parcels that cost more in logistics than the inventory value justifies.

---

## The Full Flow, End to End

```
Daily performance CSV
        |
        v
  blinkit_performance_detail (DB)
        |
        v
  compute_ads()
  ├─ Per DS: raw_ADS on available days
  ├─ Impute OOS days with city P75 (or global fallback)
  └─ ADS = (raw_orders + imputed_orders) / 30
        |
        v
  Filter to active, eligible DSes
  Group by WH × SKU → total_ADS
        |
        v
  target_stock = total_ADS × 37
  (floored at active_DS_count)
        |
        v
  Subtract effective_stock from inventory snapshot
        |
        v
  units_to_ship per WH × SKU
        |
        v
  Apply ₹1.5L gate per WH
        |
        v
  Replenishment Plan Excel
  ├─ Sheet: Ship Now  (WHs that pass the gate)
  ├─ Sheet: Full Plan (all WH × SKU with target, stock, gap)
  ├─ Sheet: Overview-WH
  └─ Sheet: Summary
```

---

## A Worked Example

**SKU:** TCB001 (Tiny Splash Pink)
**WH:** Bengaluru B3

| Dark Store | Avail Days | OOS Days | Orders (avail days) | raw_ADS |
|------------|-----------|---------|---------------------|---------|
| ES25 Indiranagar | 18 | 0 | 4 | 0.222 |
| ES31 Koramangala | 15 | 5 | 3 | 0.200 |
| ES41 HSR Layout | 12 | 8 | 1 | 0.083 |
| ES58 Whitefield | 0 | 9 | 0 | — (imputed) |

City P75 for TCB001 in Bengaluru = **0.18**

| Dark Store | Imputed ADS |
|------------|------------|
| ES25 | (0.222 × 18 + 0.18 × 0) / 30 = **0.133** |
| ES31 | (0.200 × 15 + 0.18 × 5) / 30 = **0.130** |
| ES41 | (0.083 × 12 + 0.18 × 8) / 30 = **0.081** |
| ES58 | (0 × 0 + 0.18 × 9) / 30 = **0.054** |

**Total ADS = 0.133 + 0.130 + 0.081 + 0.054 = 0.398**

```
Target stock  = 0.398 × 37 = 14.7  →  15 units
Effective stock = 3 (WH) + 0 (incoming) + 0 (transit) + 1 (DS) = 4
Units to ship = 15 − 4 = 11 units
```

---

## What Can Go Wrong

| Issue | What You See | What It Means |
|-------|-------------|--------------|
| **All Kundli DSes are OOS for a new SKU** | ADS driven entirely by global P75 fallback | The OOS imputation is using South India demand as proxy for Delhi — treat with caution |
| **WH-OOS blind spot** | total_ADS = 0 despite SKU being listed | WH has been dry all period, so no performance data accumulated. Floor kicks in (target = DS count), but it's a guess |
| **DS not launched** | `launch_awaited` status | City activation not done in Blinkit panel. Do NOT ship stock — it won't reach dark stores |
| **DS choked** | `ds_choked` status | Blinkit has throttled that DS. Counted in overview but excluded from ADS |

---

## Key Numbers

| Parameter | Value |
|-----------|-------|
| Lookback window | 30 days (rolling from latest data date) |
| Coverage target | 30 days |
| Transit buffer | 7 days |
| Min available days for reliable ADS | 5 days |
| WH shipment gate | ₹1,50,000 per WH |
| OOS imputation | city P75 → global P75 fallback |

---

*Generated by The Cradle Box demand planning system · tcb/replenishment.py*
