-- Recreate channels table with correct column order.
-- CASCADE drops dependent views; FK tables (inventory, orders, etc.) are unaffected
-- because their FK references channel_id (SERIAL) which is preserved.

-- Step 1: Drop dependent views
DROP VIEW IF EXISTS v_monthly_mis CASCADE;
DROP VIEW IF EXISTS v_darkstore_doc CASCADE;
DROP VIEW IF EXISTS v_inventory_summary CASCADE;
DROP VIEW IF EXISTS v_assemblable_skus CASCADE;
DROP VIEW IF EXISTS v_item_current_cost CASCADE;
DROP VIEW IF EXISTS v_sku_live_cogs CASCADE;

-- Step 2: Drop and recreate channels with correct column order
DROP TABLE channels CASCADE;

CREATE TABLE channels (
    channel_id      SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    code            TEXT UNIQUE NOT NULL,
    business_model  TEXT CHECK (business_model IN ('DROP_SHIP','FBA','SOR','OUTRIGHT','DIRECT')),
    fulfillment_from TEXT,
    is_location     BOOLEAN DEFAULT FALSE,
    is_active       BOOLEAN DEFAULT TRUE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Step 3: Recreate views (copied from 01_create_tables.sql)

CREATE OR REPLACE VIEW v_inventory_summary AS
SELECT
  i.item_id, i.name AS item_name, i.unit,
  c.code AS location_code, c.name AS location_name,
  inv.quantity_on_hand, inv.quantity_reserved,
  inv.quantity_on_hand - inv.quantity_reserved AS quantity_available,
  i.reorder_point,
  CASE WHEN (inv.quantity_on_hand - inv.quantity_reserved) <= i.reorder_point
       THEN TRUE ELSE FALSE END AS below_reorder_point
FROM inventory inv
JOIN items i   ON i.item_id   = inv.item_id
JOIN channels c ON c.channel_id = inv.channel_id;

CREATE OR REPLACE VIEW v_assemblable_skus AS
SELECT
  b.sku_id,
  MIN(FLOOR((inv.quantity_on_hand - inv.quantity_reserved) / b.quantity_per_sku))::INT AS max_assemblable
FROM bom b
JOIN inventory inv ON inv.item_id = inv.item_id
JOIN channels c    ON c.channel_id = inv.channel_id AND c.code = 'OWN_WH'
GROUP BY b.sku_id;

CREATE OR REPLACE VIEW v_item_current_cost AS
SELECT DISTINCT ON (item_id)
  item_id, batch_code, cost_per_unit, received_date
FROM item_batches
WHERE is_current = TRUE
ORDER BY item_id, received_date DESC;

CREATE OR REPLACE VIEW v_sku_live_cogs AS
SELECT
  b.sku_id,
  SUM(b.quantity_per_sku * c.cost_per_unit) AS live_cogs
FROM bom b
JOIN v_item_current_cost c ON c.item_id = b.item_id
GROUP BY b.sku_id;

CREATE OR REPLACE VIEW v_monthly_mis AS
SELECT
  DATE_TRUNC('month', o.order_date)::DATE AS month,
  ch.code  AS channel_code,
  ch.name  AS channel_name,
  o.sku_id,
  COUNT(*)                        AS orders,
  SUM(o.quantity)                 AS units_sold,
  SUM(o.quantity * o.selling_price) AS gross_revenue
FROM orders o
JOIN channels ch ON ch.channel_id = o.channel_id
WHERE o.status NOT IN ('CANCELLED','RETURNED')
GROUP BY 1, 2, 3, 4;

CREATE OR REPLACE VIEW v_darkstore_doc AS
WITH last_inv AS (
  SELECT DISTINCT ON (darkstore_id, sku_id)
    darkstore_id, sku_id, qty_on_hand, report_date
  FROM darkstore_inventory ORDER BY darkstore_id, sku_id, report_date DESC
),
velocity_14d AS (
  SELECT darkstore_id, sku_id,
    ROUND(SUM(qty_sold)::NUMERIC / 14, 3) AS avg_daily_qty
  FROM darkstore_sales WHERE sale_date >= CURRENT_DATE - 14
  GROUP BY darkstore_id, sku_id
)
SELECT
  ds.darkstore_id, ds.name AS darkstore_name, ds.city,
  li.sku_id,
  li.qty_on_hand AS stock_on_hand,
  COALESCE(v.avg_daily_qty, 0) AS avg_daily_sales,
  CASE WHEN COALESCE(v.avg_daily_qty, 0) = 0 THEN NULL
       ELSE ROUND(li.qty_on_hand / v.avg_daily_qty, 1)
  END AS days_of_cover
FROM darkstores ds
JOIN last_inv li      ON li.darkstore_id = ds.darkstore_id
JOIN skus s           ON s.sku_id = li.sku_id
LEFT JOIN velocity_14d v ON v.darkstore_id = ds.darkstore_id AND v.sku_id = li.sku_id;
