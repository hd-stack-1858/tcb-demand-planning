-- 016: Create blinkit_performance_detail
-- Replaces blinkit_performance_ads as the primary source for DS-level ADS.
-- Key differences from old table:
--   inventory_available (Column Q, DS-level) replaces wh_oos_flag (Column S, WH-level)
--   city and serving_wh stored per row for city-level aggregations
--   orders_with_complaint (Column Y) captured
--   assessment_start/end dropped; rolling 30-day window used instead
-- blinkit_performance_ads is retained during the validation period.

CREATE TABLE IF NOT EXISTS blinkit_performance_detail (
    data_date              DATE     NOT NULL,
    location_id            INTEGER  NOT NULL,
    sku_id                 TEXT     NOT NULL,
    ds_name                TEXT,
    city                   TEXT,
    serving_wh             TEXT,
    inventory_available    BOOLEAN  NOT NULL DEFAULT FALSE,
    total_orders           INTEGER  NOT NULL DEFAULT 0,
    orders_with_complaint  INTEGER  NOT NULL DEFAULT 0,
    download_date          DATE     NOT NULL,
    CONSTRAINT blinkit_performance_detail_pkey
        PRIMARY KEY (data_date, location_id, sku_id)
);

CREATE INDEX IF NOT EXISTS idx_bpd_sku_date
    ON blinkit_performance_detail (sku_id, data_date);

CREATE INDEX IF NOT EXISTS idx_bpd_loc_sku
    ON blinkit_performance_detail (location_id, sku_id);
