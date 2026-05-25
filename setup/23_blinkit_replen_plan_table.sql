-- ── Migration 23: Blinkit replenishment plan cache ────────────────────────────
-- Stores the computed replenishment plan in DB so the Streamlit dashboard can
-- read it even when the local parquet file is unavailable (e.g. Streamlit Cloud).
-- One row per plan_date × wh_code × sku_id. Dashboard reads the latest plan_date.

CREATE TABLE IF NOT EXISTS blinkit_replen_plan (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_date         DATE          NOT NULL,
    wh_code           TEXT          NOT NULL,
    wh_name           TEXT          NOT NULL,
    wh_location_id    INTEGER       NOT NULL,
    sku_id            TEXT          NOT NULL REFERENCES skus(sku_id),
    sku_name          TEXT,
    active_ds_count   INTEGER       NOT NULL DEFAULT 0,
    ds_choked_count   INTEGER       NOT NULL DEFAULT 0,
    ds_with_data      INTEGER       NOT NULL DEFAULT 0,
    ds_with_oos       INTEGER       NOT NULL DEFAULT 0,
    avg_ads_per_ds    NUMERIC(10,4) NOT NULL DEFAULT 0,
    total_ads         NUMERIC(10,2) NOT NULL DEFAULT 0,
    total_demand_30d  NUMERIC(10,2) NOT NULL DEFAULT 0,
    transit_buffer_7d NUMERIC(10,2) NOT NULL DEFAULT 0,
    target_stock      NUMERIC(10,2) NOT NULL DEFAULT 0,
    units_wh          INTEGER       NOT NULL DEFAULT 0,
    units_incoming    INTEGER       NOT NULL DEFAULT 0,
    units_transit     INTEGER       NOT NULL DEFAULT 0,
    units_ds          INTEGER       NOT NULL DEFAULT 0,
    effective_stock   INTEGER       NOT NULL DEFAULT 0,
    units_to_ship     INTEGER       NOT NULL DEFAULT 0,
    selling_price     NUMERIC(10,2),
    invoice_value     NUMERIC(10,2),
    priority          BOOLEAN       NOT NULL DEFAULT FALSE,
    assessment_start  DATE,
    assessment_end    DATE,
    notes             TEXT          NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (plan_date, wh_code, sku_id)
);
