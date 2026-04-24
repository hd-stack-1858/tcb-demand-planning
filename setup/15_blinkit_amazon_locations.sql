-- ── 1. Rename darkstores → blinkit_locations with WH/DARKSTORE hierarchy ────

ALTER TABLE darkstore_inventory RENAME COLUMN darkstore_id TO location_id;
ALTER TABLE darkstore_sales     RENAME COLUMN darkstore_id TO location_id;

ALTER TABLE darkstores RENAME TO blinkit_locations;
ALTER TABLE blinkit_locations ADD COLUMN IF NOT EXISTS location_type TEXT NOT NULL DEFAULT 'DARKSTORE'
    CHECK (location_type IN ('WH', 'DARKSTORE'));
ALTER TABLE blinkit_locations ADD COLUMN IF NOT EXISTS parent_wh_id INT REFERENCES blinkit_locations(darkstore_id);

-- Rename primary key column for clarity
ALTER TABLE blinkit_locations RENAME COLUMN darkstore_id TO location_id;

-- ── 2. Amazon warehouses ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS amazon_warehouses (
    wh_id       SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,           -- e.g. "Amazon FC Mumbai BOM1"
    code        TEXT UNIQUE NOT NULL,    -- e.g. "AZ_FC_BOM1"
    city        TEXT,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Seed the one WH we currently use (code can be updated when known)
INSERT INTO amazon_warehouses (name, code, city)
VALUES ('Amazon FC (Primary)', 'AZ_FC_01', 'Mumbai')
ON CONFLICT (code) DO NOTHING;

-- ── 3. Amazon FBA inventory (from Amazon reports) ────────────────────────────

CREATE TABLE IF NOT EXISTS amazon_fba_inventory (
    fba_inv_id   SERIAL PRIMARY KEY,
    wh_id        INT NOT NULL REFERENCES amazon_warehouses(wh_id),
    sku_id       TEXT NOT NULL REFERENCES skus(sku_id),
    qty_on_hand  INT NOT NULL DEFAULT 0,
    qty_reserved INT NOT NULL DEFAULT 0,  -- pending orders at Amazon
    report_date  DATE NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(wh_id, sku_id, report_date)
);

-- ── 4. Reconciliation view: Blinkit ─────────────────────────────────────────
-- Compares cumulative units shipped to Blinkit vs what Blinkit accounts for

CREATE OR REPLACE VIEW v_blinkit_reconciliation AS
WITH shipped AS (
    SELECT sku_id, SUM(quantity) AS total_shipped
    FROM sku_inventory_transactions
    WHERE type = 'TRANSFER_OUT'
      AND to_channel_id = (SELECT channel_id FROM channels WHERE code = 'BLK')
    GROUP BY sku_id
),
blinkit_stock AS (
    SELECT sku_id, SUM(qty_on_hand) AS total_at_blinkit
    FROM darkstore_inventory di
    JOIN blinkit_locations bl ON bl.location_id = di.location_id
    GROUP BY sku_id
),
blinkit_sold AS (
    SELECT sku_id, SUM(qty_sold) AS total_sold
    FROM darkstore_sales
    GROUP BY sku_id
)
SELECT
    s.sku_id,
    COALESCE(sh.total_shipped,       0) AS total_shipped,
    COALESCE(bs.total_at_blinkit,    0) AS stock_at_blinkit,
    COALESCE(bsold.total_sold,       0) AS total_sold_by_blinkit,
    COALESCE(sh.total_shipped, 0)
        - COALESCE(bs.total_at_blinkit, 0)
        - COALESCE(bsold.total_sold, 0)  AS discrepancy,
    CASE WHEN (
        COALESCE(sh.total_shipped, 0)
        - COALESCE(bs.total_at_blinkit, 0)
        - COALESCE(bsold.total_sold, 0)
    ) <> 0 THEN TRUE ELSE FALSE END      AS has_discrepancy
FROM skus s
LEFT JOIN shipped       sh    ON sh.sku_id    = s.sku_id
LEFT JOIN blinkit_stock bs    ON bs.sku_id    = s.sku_id
LEFT JOIN blinkit_sold  bsold ON bsold.sku_id = s.sku_id
WHERE s.is_discontinued = FALSE;

-- ── 5. Reconciliation view: Amazon FBA ──────────────────────────────────────

CREATE OR REPLACE VIEW v_amazon_reconciliation AS
WITH shipped AS (
    SELECT sku_id, SUM(quantity) AS total_shipped
    FROM sku_inventory_transactions
    WHERE type = 'TRANSFER_OUT'
      AND to_channel_id = (SELECT channel_id FROM channels WHERE code = 'AZ_FBA')
    GROUP BY sku_id
),
fba_stock AS (
    SELECT sku_id, SUM(qty_on_hand) AS total_at_amazon
    FROM amazon_fba_inventory
    WHERE report_date = (SELECT MAX(report_date) FROM amazon_fba_inventory)
    GROUP BY sku_id
),
fba_sold AS (
    SELECT sku_id, SUM(quantity) AS total_sold
    FROM orders
    WHERE channel_id = (SELECT channel_id FROM channels WHERE code = 'AZ_FBA')
      AND status NOT IN ('CANCELLED', 'RETURNED')
    GROUP BY sku_id
)
SELECT
    s.sku_id,
    COALESCE(sh.total_shipped,    0) AS total_shipped,
    COALESCE(fs.total_at_amazon,  0) AS stock_at_amazon,
    COALESCE(fba_sold.total_sold, 0) AS total_sold_by_amazon,
    COALESCE(sh.total_shipped, 0)
        - COALESCE(fs.total_at_amazon, 0)
        - COALESCE(fba_sold.total_sold, 0) AS discrepancy,
    CASE WHEN (
        COALESCE(sh.total_shipped, 0)
        - COALESCE(fs.total_at_amazon, 0)
        - COALESCE(fba_sold.total_sold, 0)
    ) <> 0 THEN TRUE ELSE FALSE END         AS has_discrepancy
FROM skus s
LEFT JOIN shipped  sh      ON sh.sku_id      = s.sku_id
LEFT JOIN fba_stock fs     ON fs.sku_id      = s.sku_id
LEFT JOIN fba_sold         ON fba_sold.sku_id = s.sku_id
WHERE s.is_discontinued = FALSE;
