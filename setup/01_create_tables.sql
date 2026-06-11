-- THE CRADLE BOX -- DEMAND PLANNING SYSTEM
-- Full schema v2: Sales MIS + Inventory + Distribution + Forecasting + PO + Invoicing
-- Run this entire file in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id     SERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  contact_name    TEXT,
  phone           TEXT,
  email           TEXT,
  city            TEXT,
  gstin           TEXT,
  lead_time_days  INT DEFAULT 7,
  moq             INT DEFAULT 1,
  payment_terms   TEXT,
  notes           TEXT,
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS items (
  item_id         SERIAL PRIMARY KEY,
  item_code       TEXT UNIQUE NOT NULL,
  name            TEXT NOT NULL,
  item_type       TEXT NOT NULL CHECK (item_type IN ('PRODUCT','PACKAGING')),
  latest_supplier_id INT REFERENCES suppliers(supplier_id),
  unit            TEXT DEFAULT 'piece',
  reorder_point   INT DEFAULT 0,
  safety_stock    INT DEFAULT 0,
  lead_time_days  INT DEFAULT 7,
  moq             INT DEFAULT 1,
  notes           TEXT,
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS skus (
  sku_id            TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  hsn_code          TEXT,
  gst_pct           NUMERIC(5,2) DEFAULT 5.0,
  is_active         BOOLEAN DEFAULT TRUE,
  is_discontinued   BOOLEAN DEFAULT FALSE,
  discontinued_note TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sku_pricing (
  pricing_id      SERIAL PRIMARY KEY,
  sku_id          TEXT NOT NULL REFERENCES skus(sku_id),
  effective_date  DATE NOT NULL,
  mrp             NUMERIC(10,2) NOT NULL,
  cogs            NUMERIC(10,2),
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(sku_id, effective_date)
);

CREATE TABLE IF NOT EXISTS sku_channel_sp (
  sp_id           SERIAL PRIMARY KEY,
  sku_id          TEXT NOT NULL REFERENCES skus(sku_id),
  channel_code    TEXT NOT NULL,
  effective_date  DATE NOT NULL,
  selling_price   NUMERIC(10,2) NOT NULL,
  transfer_price  NUMERIC(10,2),
  notes           TEXT,
  UNIQUE(sku_id, channel_code, effective_date)
);

CREATE TABLE IF NOT EXISTS channels (
  channel_id          SERIAL PRIMARY KEY,
  name                TEXT NOT NULL,
  code                TEXT UNIQUE NOT NULL,
  type                TEXT NOT NULL CHECK (type IN ('OWN_WH','DIRECT','FBA','DARKSTORE','PARTNER','OUTRIGHT')),
  fulfillment_from    TEXT,
  commission_pct      NUMERIC(5,2) DEFAULT 0,
  storage_fee_monthly NUMERIC(10,2) DEFAULT 0,
  gst_on_commission   BOOLEAN DEFAULT FALSE,
  notes               TEXT,
  is_active           BOOLEAN DEFAULT TRUE,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sku_channel_ids (
  id                  SERIAL PRIMARY KEY,
  sku_id              TEXT NOT NULL REFERENCES skus(sku_id),
  channel_code        TEXT NOT NULL,
  platform_sku        TEXT,
  platform_asin       TEXT,
  platform_pid        TEXT,
  platform_item_id    TEXT,
  platform_upc        TEXT,
  platform_product_id TEXT,
  notes               TEXT,
  UNIQUE(sku_id, channel_code)
);

CREATE TABLE IF NOT EXISTS bom (
  bom_id           SERIAL PRIMARY KEY,
  sku_id           TEXT NOT NULL REFERENCES skus(sku_id),
  item_id          INT NOT NULL REFERENCES items(item_id),
  quantity_per_sku NUMERIC(10,3) DEFAULT 1,
  UNIQUE(sku_id, item_id)
);

CREATE TABLE IF NOT EXISTS item_batches (
  batch_id        SERIAL PRIMARY KEY,
  item_id         INT NOT NULL REFERENCES items(item_id),
  batch_code      TEXT NOT NULL,
  received_date   DATE NOT NULL,
  supplier_id     INT REFERENCES suppliers(supplier_id),
  cost_per_unit   NUMERIC(10,4) NOT NULL,
  qty_received    INT NOT NULL,
  qty_remaining   INT NOT NULL,
  po_reference    TEXT,
  notes           TEXT,
  is_current      BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(item_id, batch_code)
);

CREATE TABLE IF NOT EXISTS inventory (
  inv_id             SERIAL PRIMARY KEY,
  item_id            INT NOT NULL REFERENCES items(item_id),
  batch_id           INT NOT NULL REFERENCES item_batches(batch_id),
  channel_id         INT NOT NULL REFERENCES channels(channel_id),
  quantity_on_hand   INT DEFAULT 0,
  quantity_reserved  INT DEFAULT 0,
  quantity_intransit INT DEFAULT 0,
  last_updated       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(item_id, batch_id, channel_id)
);

CREATE TABLE IF NOT EXISTS inventory_transactions (
  txn_id          SERIAL PRIMARY KEY,
  txn_date        TIMESTAMPTZ DEFAULT NOW(),
  type            TEXT NOT NULL CHECK (type IN (
                    'RECEIPT','DISPATCH','TRANSFER_OUT','TRANSFER_IN',
                    'ADJUSTMENT','RTO','SALE_RETURN','DAMAGE_WRITE_OFF'
                  )),
  item_id         INT NOT NULL REFERENCES items(item_id),
  batch_id        INT REFERENCES item_batches(batch_id),
  from_channel_id INT REFERENCES channels(channel_id),
  to_channel_id   INT REFERENCES channels(channel_id),
  quantity        INT NOT NULL,
  unit_cost       NUMERIC(10,4),
  reference       TEXT,
  notes           TEXT,
  created_by      TEXT DEFAULT 'system',
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS darkstores (
  darkstore_id    SERIAL PRIMARY KEY,
  channel_id      INT NOT NULL REFERENCES channels(channel_id),
  name            TEXT NOT NULL,
  code            TEXT UNIQUE,
  city            TEXT,
  hub_name        TEXT,
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS darkstore_inventory (
  ds_inv_id       SERIAL PRIMARY KEY,
  darkstore_id    INT NOT NULL REFERENCES darkstores(darkstore_id),
  sku_id          TEXT NOT NULL REFERENCES skus(sku_id),
  qty_on_hand     INT DEFAULT 0,
  report_date     DATE NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(darkstore_id, sku_id, report_date)
);

CREATE TABLE IF NOT EXISTS darkstore_sales (
  ds_sale_id      SERIAL PRIMARY KEY,
  darkstore_id    INT NOT NULL REFERENCES darkstores(darkstore_id),
  sale_date       DATE NOT NULL,
  sku_id          TEXT NOT NULL REFERENCES skus(sku_id),
  qty_sold        INT DEFAULT 0,
  gross_value     NUMERIC(10,2),
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(darkstore_id, sale_date, sku_id)
);

CREATE TABLE IF NOT EXISTS distribution_rules (
  rule_id             SERIAL PRIMARY KEY,
  darkstore_id        INT NOT NULL REFERENCES darkstores(darkstore_id),
  sku_id              TEXT NOT NULL REFERENCES skus(sku_id),
  target_days_cover   INT DEFAULT 14,
  min_replenish_qty   INT DEFAULT 5,
  trigger_days_cover  INT DEFAULT 7,
  is_active           BOOLEAN DEFAULT TRUE,
  UNIQUE(darkstore_id, sku_id)
);

CREATE TABLE IF NOT EXISTS orders (
  order_id            TEXT NOT NULL,
  channel_id          INT NOT NULL REFERENCES channels(channel_id),
  order_date          DATE NOT NULL,
  sku_id              TEXT NOT NULL REFERENCES skus(sku_id),
  quantity            INT NOT NULL DEFAULT 1,
  mrp                 NUMERIC(10,2),
  selling_price       NUMERIC(10,2),
  gross_value         NUMERIC(10,2),
  discount_pct        NUMERIC(5,2),
  commission_pct      NUMERIC(5,2),
  commission_amt      NUMERIC(10,2),
  logistics_cost      NUMERIC(10,2),
  ad_spend_allocated  NUMERIC(10,2),
  cogs                NUMERIC(10,2),
  net_margin          NUMERIC(10,2),
  fulfillment_type    TEXT,
  city                TEXT,
  state               TEXT,
  darkstore_id        INT REFERENCES darkstores(darkstore_id),
  platform_order_id   TEXT,
  status              TEXT DEFAULT 'FULFILLED' CHECK (status IN (
                        'PENDING','FULFILLED','CANCELLED','RTO','SALE_RETURN'
                      )),
  return_date         DATE,
  return_reason       TEXT,
  source_file         TEXT,
  PRIMARY KEY (order_id, channel_id)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
  po_id           SERIAL PRIMARY KEY,
  po_number       TEXT UNIQUE,
  supplier_id     INT NOT NULL REFERENCES suppliers(supplier_id),
  created_date    DATE DEFAULT CURRENT_DATE,
  expected_date   DATE,
  received_date   DATE,
  status          TEXT DEFAULT 'DRAFT' CHECK (status IN (
                    'DRAFT','SENT','CONFIRMED','PARTIAL','RECEIVED','CANCELLED'
                  )),
  total_value     NUMERIC(10,2),
  advance_paid    NUMERIC(10,2),
  balance_due     NUMERIC(10,2),
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
  poi_id              SERIAL PRIMARY KEY,
  po_id               INT NOT NULL REFERENCES purchase_orders(po_id),
  item_id             INT NOT NULL REFERENCES items(item_id),
  quantity_ordered    INT NOT NULL,
  cost_per_unit       NUMERIC(10,4),
  line_total          NUMERIC(10,2),
  quantity_received   INT DEFAULT 0,
  batch_code_received TEXT,
  notes               TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
  invoice_id      SERIAL PRIMARY KEY,
  invoice_number  TEXT UNIQUE,
  channel_id      INT NOT NULL REFERENCES channels(channel_id),
  invoice_date    DATE DEFAULT CURRENT_DATE,
  due_date        DATE,
  our_gstin       TEXT,
  partner_gstin   TEXT,
  partner_name    TEXT,
  partner_address TEXT,
  subtotal        NUMERIC(10,2),
  cgst_amt        NUMERIC(10,2),
  sgst_amt        NUMERIC(10,2),
  igst_amt        NUMERIC(10,2),
  total_amount    NUMERIC(10,2),
  status          TEXT DEFAULT 'DRAFT' CHECK (status IN (
                    'DRAFT','SENT','PAID','PARTIALLY_PAID','OVERDUE','CANCELLED'
                  )),
  payment_date    DATE,
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invoice_items (
  inv_item_id     SERIAL PRIMARY KEY,
  invoice_id      INT NOT NULL REFERENCES invoices(invoice_id),
  sku_id          TEXT NOT NULL REFERENCES skus(sku_id),
  hsn_code        TEXT,
  description     TEXT,
  quantity        INT NOT NULL,
  mrp             NUMERIC(10,2),
  rate            NUMERIC(10,2),
  line_total      NUMERIC(10,2),
  gst_pct         NUMERIC(5,2),
  gst_amt         NUMERIC(10,2),
  cogs            NUMERIC(10,2)
);

CREATE TABLE IF NOT EXISTS replenishment_recommendations (
  rec_id              SERIAL PRIMARY KEY,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  rec_type            TEXT NOT NULL CHECK (rec_type IN (
                        'DARKSTORE_REPLENISHMENT','FBA_REPLENISHMENT','SUPPLIER_PO'
                      )),
  sku_id              TEXT REFERENCES skus(sku_id),
  item_id             INT REFERENCES items(item_id),
  from_channel_id     INT REFERENCES channels(channel_id),
  to_darkstore_id     INT REFERENCES darkstores(darkstore_id),
  recommended_qty     INT,
  current_stock       INT,
  days_of_cover       NUMERIC(5,1),
  avg_daily_velocity  NUMERIC(8,3),
  trigger_reason      TEXT,
  status              TEXT DEFAULT 'OPEN' CHECK (status IN (
                        'OPEN','APPROVED','DISPATCHED','REJECTED'
                      )),
  approved_at         TIMESTAMPTZ,
  dispatched_at       TIMESTAMPTZ,
  notes               TEXT
);

CREATE TABLE IF NOT EXISTS demand_forecasts (
  forecast_id     SERIAL PRIMARY KEY,
  sku_id          TEXT NOT NULL REFERENCES skus(sku_id),
  channel_id      INT NOT NULL REFERENCES channels(channel_id),
  forecast_month  DATE NOT NULL,
  forecast_units  INT,
  confidence_lo   INT,
  confidence_hi   INT,
  model           TEXT DEFAULT '3M_WEIGHTED',
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(sku_id, channel_id, forecast_month)
);

CREATE TABLE IF NOT EXISTS company_config (
  config_id   SERIAL PRIMARY KEY,
  key         TEXT UNIQUE NOT NULL,
  value       TEXT,
  notes       TEXT,
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO company_config (key, notes) VALUES
  ('company_name',       'Legal company name for invoices'),
  ('gstin',              'Our GSTIN'),
  ('pan',                'Company PAN'),
  ('registered_address', 'Full registered address'),
  ('bank_name',          'Bank name'),
  ('bank_account',       'Account number'),
  ('bank_ifsc',          'IFSC code'),
  ('invoice_prefix',     'e.g. TCB/2026-27/'),
  ('invoice_counter',    'Current invoice number counter (integer as text)')
ON CONFLICT (key) DO NOTHING;

-- VIEWS

CREATE OR REPLACE VIEW v_inventory_summary AS
SELECT
  i.item_code, i.name AS item_name, i.item_type,
  c.name AS location, c.code AS location_code, c.type AS location_type,
  SUM(inv.quantity_on_hand) AS qty_on_hand,
  SUM(inv.quantity_reserved) AS qty_reserved,
  SUM(inv.quantity_intransit) AS qty_intransit,
  SUM(inv.quantity_on_hand - inv.quantity_reserved) AS qty_available,
  i.reorder_point, i.safety_stock,
  CASE WHEN SUM(inv.quantity_on_hand - inv.quantity_reserved) <= i.reorder_point
       THEN TRUE ELSE FALSE END AS below_reorder_point,
  MAX(inv.last_updated) AS last_updated
FROM inventory inv
JOIN items i ON i.item_id = inv.item_id
JOIN channels c ON c.channel_id = inv.channel_id
GROUP BY i.item_id, i.item_code, i.name, i.item_type,
         c.channel_id, c.name, c.code, c.type, i.reorder_point, i.safety_stock;

CREATE OR REPLACE VIEW v_assemblable_skus AS
SELECT
  b.sku_id, s.name AS sku_name, s.is_discontinued,
  MIN(FLOOR(COALESCE(avail.qty_available, 0) / b.quantity_per_sku))::INT AS max_assemblable
FROM bom b
JOIN skus s ON s.sku_id = b.sku_id
LEFT JOIN (
  SELECT i.item_id, SUM(inv.quantity_on_hand - inv.quantity_reserved) AS qty_available
  FROM inventory inv
  JOIN items i ON i.item_id = inv.item_id
  JOIN channels c ON c.channel_id = inv.channel_id AND c.code = 'OWN_WH'
  GROUP BY i.item_id
) avail ON avail.item_id = b.item_id
WHERE s.is_active = TRUE
GROUP BY b.sku_id, s.name, s.is_discontinued;

CREATE OR REPLACE VIEW v_item_current_cost AS
SELECT DISTINCT ON (b.item_id)
  i.item_id, i.item_code, i.name AS item_name,
  b.batch_code, b.received_date, b.cost_per_unit, b.qty_remaining,
  s.name AS supplier_name
FROM item_batches b
JOIN items i ON i.item_id = b.item_id
LEFT JOIN suppliers s ON s.supplier_id = b.supplier_id
WHERE b.is_current = TRUE
ORDER BY b.item_id, b.received_date DESC;

CREATE OR REPLACE VIEW v_sku_live_cogs AS
SELECT
  b.sku_id, sk.name AS sku_name,
  ROUND(SUM(b.quantity_per_sku * COALESCE(c.cost_per_unit, 0)), 2) AS live_cogs,
  COUNT(CASE WHEN c.cost_per_unit IS NULL THEN 1 END) AS items_missing_cost
FROM bom b
JOIN skus sk ON sk.sku_id = b.sku_id
LEFT JOIN v_item_current_cost c ON c.item_id = b.item_id
GROUP BY b.sku_id, sk.name;

CREATE OR REPLACE VIEW v_monthly_mis AS
SELECT
  DATE_TRUNC('month', o.order_date)::DATE AS month,
  c.name AS channel, c.type AS channel_type,
  o.sku_id, s.name AS sku_name,
  COUNT(DISTINCT o.order_id || o.channel_id::TEXT) AS order_count,
  SUM(o.quantity) AS units_sold,
  SUM(CASE WHEN o.status IN ('RTO','SALE_RETURN') THEN o.quantity ELSE 0 END) AS units_returned,
  SUM(o.gross_value) AS gross_revenue,
  ROUND(AVG(o.selling_price), 2) AS avg_sp,
  SUM(o.commission_amt) AS total_commission,
  SUM(o.logistics_cost) AS total_logistics,
  SUM(o.cogs) AS total_cogs,
  SUM(o.ad_spend_allocated) AS total_ad_spend,
  SUM(o.net_margin) AS total_net_margin,
  ROUND(100.0 * SUM(o.net_margin) / NULLIF(SUM(o.gross_value), 0), 1) AS net_margin_pct
FROM orders o
JOIN channels c ON c.channel_id = o.channel_id
JOIN skus s ON s.sku_id = o.sku_id
WHERE o.status != 'CANCELLED'
GROUP BY 1,2,3,4,5
ORDER BY 1 DESC, gross_revenue DESC;

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
  d.code AS darkstore_code, d.name AS darkstore_name, d.city, d.hub_name,
  li.sku_id, sk.name AS sku_name,
  li.qty_on_hand AS current_stock,
  COALESCE(v.avg_daily_qty, 0) AS avg_daily_velocity,
  CASE WHEN COALESCE(v.avg_daily_qty,0) > 0
       THEN ROUND(li.qty_on_hand / v.avg_daily_qty, 1) END AS days_of_cover,
  li.report_date AS stock_as_of,
  dr.trigger_days_cover, dr.target_days_cover,
  GREATEST(
    COALESCE(dr.min_replenish_qty, 5),
    CEIL(COALESCE(
      (dr.target_days_cover - li.qty_on_hand / NULLIF(v.avg_daily_qty,0)) * v.avg_daily_qty, 0
    ))
  )::INT AS recommended_replenish_qty,
  CASE
    WHEN li.qty_on_hand = 0 THEN 'OOS'
    WHEN COALESCE(v.avg_daily_qty,0) = 0 THEN 'NO_VELOCITY'
    WHEN (li.qty_on_hand / v.avg_daily_qty) < dr.trigger_days_cover THEN 'REPLENISH_NOW'
    WHEN (li.qty_on_hand / v.avg_daily_qty) < dr.trigger_days_cover * 1.5 THEN 'WATCH'
    ELSE 'OK'
  END AS replenishment_status
FROM last_inv li
JOIN darkstores d ON d.darkstore_id = li.darkstore_id
JOIN skus sk ON sk.sku_id = li.sku_id
LEFT JOIN velocity_14d v ON v.darkstore_id = li.darkstore_id AND v.sku_id = li.sku_id
LEFT JOIN distribution_rules dr ON dr.darkstore_id = li.darkstore_id AND dr.sku_id = li.sku_id
ORDER BY days_of_cover ASC NULLS FIRST;
