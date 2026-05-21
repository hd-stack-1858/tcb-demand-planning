-- ── Phase H: Blinkit Replenishment Model ─────────────────────────────────────
-- Creates tables for performance data, inventory snapshots, DS-SKU eligibility.
-- partner_locations already holds WH and DS master data (channel_id=4, Blinkit).
-- DS rows will be populated by the blinkit_performance_loader.

-- ── 0. Mark Farukhnagar SR as inactive (closed, never served by us) ───────────
UPDATE partner_locations
SET    is_active = FALSE,
       updated_at = NOW()
WHERE  code = 'BLK_WH_264';


-- ── 1. DS × SKU eligibility status ───────────────────────────────────────────
-- One row per dark store × SKU. Updated by performance loader from darkstore_remark column.
-- Only DS-type rows from partner_locations are referenced here.

CREATE TABLE IF NOT EXISTS blinkit_ds_sku_eligibility (
    location_id   INTEGER NOT NULL REFERENCES partner_locations(location_id),
    sku_id        TEXT    NOT NULL REFERENCES skus(sku_id),
    status        TEXT    NOT NULL DEFAULT 'active'
                      CHECK (status IN (
                          'active',               -- eligible for replenishment
                          'launch_awaited',        -- we have never supplied this DS
                          'darkstore_closed',      -- Blinkit permanently closed this DS
                          'sku_moved_out_low_sales', -- Blinkit redistributed due to low sales
                          'sku_city_exited',       -- we opted out of this city for this SKU (permanent)
                          'sku_recalled'           -- we initiated recall (requires manual relaunch)
                      )),
    last_remark   TEXT,          -- raw darkstore_remark text from performance file
    updated_date  DATE NOT NULL, -- date of the performance file row that set this status
    PRIMARY KEY (location_id, sku_id)
);

COMMENT ON TABLE blinkit_ds_sku_eligibility IS
  'Tracks replenishment eligibility per dark store × SKU. '
  'Updated via two-pass load: pass 1 scans all rows for remark changes; '
  'pass 2 loads ADS only from Y-rows. '
  'sku_city_exited = permanent Blinkit exit (e.g. TCB003/TCB006 from Hyderabad). '
  'sku_recalled = temporary; requires manual relaunch before restoring to active.';


-- ── 2. Daily performance ADS data ────────────────────────────────────────────
-- One row per calendar date × dark store × SKU.
-- Source: "Considered for assessment = Y" rows from Blinkit performance detail CSV.
-- ADS for replenishment engine = SUM(total_orders WHERE NOT wh_oos_flag)
--                              / COUNT(data_date WHERE NOT wh_oos_flag)
-- within the relevant assessment period for that SKU.

CREATE TABLE IF NOT EXISTS blinkit_performance_ads (
    id               SERIAL  PRIMARY KEY,
    data_date        DATE    NOT NULL,
    location_id      INTEGER NOT NULL REFERENCES partner_locations(location_id),
    sku_id           TEXT    NOT NULL REFERENCES skus(sku_id),

    -- Assessment period this row belongs to (per-SKU cycle, 30-day window)
    assessment_start DATE    NOT NULL,
    assessment_end   DATE    NOT NULL,

    -- Velocity data
    ads_units        NUMERIC,        -- Blinkit's "Adjusted units sold per darkstore" — NULL when WH OOS
    total_orders     INTEGER,        -- raw order count for this date at this DS
    available_hours  NUMERIC,        -- hours DS was available
    operation_hours  NUMERIC,        -- hours DS was in operation

    -- Flags and metadata
    wh_oos_flag      BOOLEAN NOT NULL DEFAULT FALSE,
                     -- TRUE when Remarks = "Insufficient Inventory at warehouse for transfers"
    present_level    TEXT,           -- L1/L2/L3/L4 — Blinkit's performance grade for this cycle
    download_date    DATE    NOT NULL, -- date the CSV file was downloaded (for audit)

    UNIQUE (data_date, location_id, sku_id)
);

CREATE INDEX IF NOT EXISTS idx_perf_ads_sku_loc_date
    ON blinkit_performance_ads (sku_id, location_id, data_date DESC);

CREATE INDEX IF NOT EXISTS idx_perf_ads_assessment
    ON blinkit_performance_ads (sku_id, assessment_start, assessment_end);

COMMENT ON TABLE blinkit_performance_ads IS
  'Daily ADS data per dark store × SKU. '
  'wh_oos_flag=TRUE rows are excluded from velocity calculation (no stock at WH). '
  'wh_oos_flag=FALSE AND total_orders=0 rows count as zero-sales days in ADS denominator. '
  'Replenishment ADS = SUM(total_orders WHERE NOT wh_oos_flag) / COUNT(days WHERE NOT wh_oos_flag) '
  'using the latest assessment period data available for that sku_id.';


-- ── 3. Inventory snapshots (SOH file) ────────────────────────────────────────
-- One row per snapshot date × WH × SKU.
-- Downloaded from Blinkit portal on the day of running replenishment analysis.
-- Replenishment formula uses: units_wh + units_incoming as effective WH stock.

CREATE TABLE IF NOT EXISTS blinkit_inventory_snapshots (
    id              SERIAL  PRIMARY KEY,
    snapshot_date   DATE    NOT NULL,
    location_id     INTEGER NOT NULL REFERENCES partner_locations(location_id),  -- WH rows only
    sku_id          TEXT    NOT NULL REFERENCES skus(sku_id),

    units_wh        INTEGER NOT NULL DEFAULT 0,  -- stock physically at WH (sellable, Warehouse col)
    units_incoming  INTEGER NOT NULL DEFAULT 0,  -- "Incoming scheduled inventory" — already dispatched, not yet inwarded
    units_ds        INTEGER NOT NULL DEFAULT 0,  -- stock at dark stores (reference only; cannot redirect)
    units_transit   INTEGER NOT NULL DEFAULT 0,  -- WH→DS in transit (reference only)
    total_sellable  INTEGER NOT NULL DEFAULT 0,

    last_7d_sales   INTEGER,   -- Blinkit-reported recent velocity (reference only)
    last_15d_sales  INTEGER,
    last_30d_sales  INTEGER,

    UNIQUE (snapshot_date, location_id, sku_id)
);

COMMENT ON TABLE blinkit_inventory_snapshots IS
  'Blinkit SOH (Stock on Hand) snapshots. '
  'Replenishment formula: effective_wh_stock = units_wh + units_incoming. '
  'units_incoming represents stock already dispatched from our warehouse but not yet '
  'inwarded at Blinkit WH — prevents double-shipping when a recent dispatch is in flight. '
  'Download SOH report on the day of running replenishment; load before running engine.';


-- ── 4. Performance summary (SKU-level, per cycle) ────────────────────────────
-- One row per SKU per assessment period. From Blinkit summary CSV.
-- Not used in replenishment formula; useful for SKU-level health monitoring.

CREATE TABLE IF NOT EXISTS blinkit_performance_summary (
    id                       SERIAL  PRIMARY KEY,
    assessment_start         DATE    NOT NULL,
    assessment_end           DATE    NOT NULL,
    sku_id                   TEXT    NOT NULL REFERENCES skus(sku_id),
    download_date            DATE    NOT NULL,

    present_level            TEXT,
    total_live_darkstores    INTEGER,
    total_new_darkstores     INTEGER,   -- DS eligible in last 10 days
    total_closed_darkstores  INTEGER,
    ads_units                NUMERIC,   -- Blinkit's cycle-level ADS across all DS
    ads_value                NUMERIC,   -- ₹ GMV equivalent
    availability_pct         NUMERIC,
    complaint_pct            NUMERIC,
    total_orders             INTEGER,

    UNIQUE (assessment_start, assessment_end, sku_id)
);

COMMENT ON TABLE blinkit_performance_summary IS
  'SKU-level aggregate per assessment cycle. Source: Blinkit performance summary CSV. '
  'Use for trend analysis and availability/complaint monitoring, not replenishment calculations.';


-- ── 5. Ageing snapshots (deferred — load after business rule is defined) ──────
-- Rule: flag rows where age_slab = '>60' AND units are stable/growing across dates → "Consider recall".
-- inventory_type: Frontend = dark store shelf stock; Backend = WH-level stock at that DS.

CREATE TABLE IF NOT EXISTS blinkit_ageing_snapshots (
    report_date      DATE    NOT NULL,
    location_id      INTEGER NOT NULL REFERENCES partner_locations(location_id),  -- DS rows
    sku_id           TEXT    NOT NULL REFERENCES skus(sku_id),
    inventory_type   TEXT    NOT NULL CHECK (inventory_type IN ('Frontend', 'Backend')),
    age_slab         TEXT    NOT NULL CHECK (age_slab IN ('0-30 Days', '30-60 Days', '>60 Days')),
    units            INTEGER NOT NULL DEFAULT 0,
    per_unit_fee     NUMERIC,       -- ageing fee ₹ per unit per day

    PRIMARY KEY (report_date, location_id, sku_id, inventory_type, age_slab)
);

COMMENT ON TABLE blinkit_ageing_snapshots IS
  'Ageing fee data per DS × SKU × inventory type × age slab. '
  'Replenishment flag rule: if age_slab=''>60 Days'' AND units not declining across '
  'recent report_dates for same DS-SKU → flag ''Consider recall — stale stock'' in output. '
  'Frontend = DS shelf inventory. Backend = DS back-storage / WH-level at that DS. '
  'Table created but loader deferred — define ageing recall threshold before building loader.';
