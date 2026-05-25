-- ─────────────────────────────────────────────────────────────────────────────
-- THE CRADLE BOX — DEV DATABASE SCHEMA (consolidated, current as of Apr 2026)
-- Run this entire file in the Supabase SQL Editor of your DEV project.
-- This is the single source of truth for the dev DB schema.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Core reference tables ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id    SERIAL PRIMARY KEY,
  name           TEXT NOT NULL UNIQUE,
  contact_name   TEXT,
  phone          TEXT,
  email          TEXT,
  city           TEXT,
  gstin          TEXT,
  lead_time_days INT DEFAULT 7,
  moq            INT DEFAULT 1,
  payment_terms  TEXT,
  notes          TEXT,
  is_active      BOOLEAN DEFAULT TRUE,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS items (
  item_id        SERIAL PRIMARY KEY,
  item_code      TEXT UNIQUE NOT NULL,
  name           TEXT NOT NULL,
  item_type      TEXT NOT NULL CHECK (item_type IN ('PRODUCT','PACKAGING')),
  supplier_id    INT REFERENCES suppliers(supplier_id),
  unit           TEXT DEFAULT 'piece',
  reorder_point  INT DEFAULT 0,
  safety_stock   INT DEFAULT 0,
  lead_time_days INT DEFAULT 7,
  moq            INT DEFAULT 1,
  notes          TEXT,
  is_active      BOOLEAN DEFAULT TRUE,
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS skus (
  sku_id            TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  hsn_code          TEXT,
  gst_pct           NUMERIC(5,2) DEFAULT 5.0,
  is_active         BOOLEAN DEFAULT TRUE,
  is_discontinued   BOOLEAN DEFAULT FALSE,
  discontinued_note TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS channels (
  channel_id       SERIAL PRIMARY KEY,
  name             TEXT NOT NULL,
  code             TEXT UNIQUE NOT NULL,
  business_model   TEXT CHECK (business_model IN ('DROP_SHIP','FBA','SOR','OUTRIGHT','DIRECT')),
  fulfillment_from TEXT,
  is_location      BOOLEAN DEFAULT FALSE,
  is_active        BOOLEAN DEFAULT TRUE,
  legal_name       TEXT,
  notes            TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sku_channel_ids (
  id                     SERIAL PRIMARY KEY,
  sku_id                 TEXT NOT NULL REFERENCES skus(sku_id),
  channel_code           TEXT NOT NULL,
  platform_sku           TEXT,
  platform_pid           TEXT,
  platform_pid_additional TEXT,
  platform_upc           TEXT,
  notes                  TEXT,
  UNIQUE(sku_id, channel_code)
);

CREATE TABLE IF NOT EXISTS sku_pricing (
  pricing_id     SERIAL PRIMARY KEY,
  sku_id         TEXT NOT NULL REFERENCES skus(sku_id),
  effective_date DATE NOT NULL,
  mrp            NUMERIC(10,2) NOT NULL,
  sp             NUMERIC(10,2),
  cogs           NUMERIC(10,2),
  notes          TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  updated_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(sku_id, effective_date)
);

CREATE TABLE IF NOT EXISTS sku_channel_sp (
  sp_id          SERIAL PRIMARY KEY,
  sku_id         TEXT NOT NULL REFERENCES skus(sku_id),
  channel_code   TEXT NOT NULL,
  effective_date DATE NOT NULL,
  selling_price  NUMERIC(10,2) NOT NULL,
  transfer_price NUMERIC(10,2),
  notes          TEXT,
  UNIQUE(sku_id, channel_code, effective_date)
);

CREATE TABLE IF NOT EXISTS bom (
  bom_id           SERIAL PRIMARY KEY,
  sku_id           TEXT NOT NULL REFERENCES skus(sku_id),
  item_id          INT NOT NULL REFERENCES items(item_id),
  quantity_per_sku NUMERIC(10,3) DEFAULT 1,
  UNIQUE(sku_id, item_id)
);

-- ── Batch-level inventory ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS item_batches (
  batch_id       SERIAL PRIMARY KEY,
  item_id        INT NOT NULL REFERENCES items(item_id),
  batch_code     TEXT NOT NULL,
  received_date  DATE NOT NULL,
  supplier_id    INT REFERENCES suppliers(supplier_id),
  cost_per_unit  NUMERIC(10,4) NOT NULL,
  qty_received   INT NOT NULL,
  qty_remaining  INT NOT NULL,
  po_reference   TEXT,
  notes          TEXT,
  is_current     BOOLEAN DEFAULT TRUE,
  created_at     TIMESTAMPTZ DEFAULT NOW(),
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
                    'RECEIPT','ASSEMBLY','DISPATCH','TRANSFER_OUT','TRANSFER_IN',
                    'ADJUSTMENT','RTO','SALE_RETURN','DAMAGE_WRITE_OFF'
                  )),
  item_id         INT NOT NULL REFERENCES items(item_id),
  sku_id          TEXT REFERENCES skus(sku_id),
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

-- ── Partner WH locations (unified across all SOR channels) ───────────────────
-- One row per physical WH for Amazon FBA, Blinkit, Ozi, and future SOR partners.
-- Channel-specific tables (blinkit_locations, amazon_locations) are kept for
-- partner-specific metadata; this table is the FK target for inventory tracking.

CREATE TABLE IF NOT EXISTS partner_locations (
  location_id        SERIAL PRIMARY KEY,
  channel_id         INT  NOT NULL REFERENCES channels(channel_id),
  name               TEXT NOT NULL,
  code               TEXT,
  city               TEXT,
  state              TEXT,
  location_type      TEXT,
  parent_location_id INT  REFERENCES partner_locations(location_id),
  external_id        TEXT,
  is_active          BOOLEAN NOT NULL DEFAULT TRUE,
  address            TEXT,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW()
);

-- ── SKU-level assembled stock ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sku_inventory (
  sku_inv_id   SERIAL PRIMARY KEY,
  sku_id       TEXT NOT NULL REFERENCES skus(sku_id),
  channel_id   INT  NOT NULL REFERENCES channels(channel_id),
  qty_on_hand  INT  NOT NULL DEFAULT 0,
  qty_reserved INT  NOT NULL DEFAULT 0,
  last_updated TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(sku_id, channel_id)
);

CREATE TABLE IF NOT EXISTS sku_inventory_transactions (
  txn_id              SERIAL PRIMARY KEY,
  txn_date            TIMESTAMPTZ DEFAULT NOW(),
  type                TEXT NOT NULL CHECK (type IN (
                        'ASSEMBLY','DISPATCH','TRANSFER_OUT','TRANSFER_IN',
                        'ADJUSTMENT','RETURN'
                      )),
  sku_id              TEXT NOT NULL REFERENCES skus(sku_id),
  from_channel_id     INT REFERENCES channels(channel_id),
  to_channel_id       INT REFERENCES channels(channel_id),
  partner_location_id INT REFERENCES partner_locations(location_id),
  quantity            INT NOT NULL,
  unit_cogs           NUMERIC(10,4),
  reference           TEXT,
  notes               TEXT,
  created_by          TEXT DEFAULT 'system',
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ── SKU COGS lots — FIFO cost layers ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sku_cogs_lots (
  lot_id              SERIAL PRIMARY KEY,
  sku_id              TEXT NOT NULL REFERENCES skus(sku_id),
  channel_id          INT  NOT NULL REFERENCES channels(channel_id),
  partner_location_id INT  REFERENCES partner_locations(location_id),
  assembled_at        DATE NOT NULL,
  unit_cogs           NUMERIC(10,4) NOT NULL,
  qty_assembled       INT  NOT NULL DEFAULT 0,
  qty_remaining       INT  NOT NULL DEFAULT 0,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_sku_cogs_lots_no_loc
  ON sku_cogs_lots (sku_id, channel_id, assembled_at, unit_cogs)
  WHERE partner_location_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_sku_cogs_lots_with_loc
  ON sku_cogs_lots (sku_id, channel_id, partner_location_id, assembled_at, unit_cogs)
  WHERE partner_location_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sku_cogs_lots_fifo
  ON sku_cogs_lots (sku_id, channel_id, partner_location_id, assembled_at);

-- ── Blinkit locations ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS blinkit_locations (
  location_id         SERIAL PRIMARY KEY,
  channel_id          INT REFERENCES channels(channel_id),
  name                TEXT NOT NULL,
  code                TEXT UNIQUE,
  city                TEXT,
  hub_name            TEXT,
  location_type       TEXT NOT NULL DEFAULT 'DARKSTORE'
                        CHECK (location_type IN ('WH','DARKSTORE')),
  parent_wh_id        INT REFERENCES blinkit_locations(location_id),
  blinkit_facility_id INT UNIQUE,
  state               TEXT,
  address             TEXT,
  stock_sent          BOOLEAN DEFAULT FALSE,
  is_active           BOOLEAN DEFAULT TRUE,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS darkstore_inventory (
  ds_inv_id   SERIAL PRIMARY KEY,
  location_id INT NOT NULL REFERENCES blinkit_locations(location_id),
  sku_id      TEXT NOT NULL REFERENCES skus(sku_id),
  qty_on_hand INT DEFAULT 0,
  report_date DATE NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(location_id, sku_id, report_date)
);

CREATE TABLE IF NOT EXISTS darkstore_sales (
  ds_sale_id  SERIAL PRIMARY KEY,
  location_id INT NOT NULL REFERENCES blinkit_locations(location_id),
  sale_date   DATE NOT NULL,
  sku_id      TEXT NOT NULL REFERENCES skus(sku_id),
  qty_sold    INT DEFAULT 0,
  gross_value NUMERIC(10,2),
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(location_id, sale_date, sku_id)
);

CREATE TABLE IF NOT EXISTS distribution_rules (
  rule_id            SERIAL PRIMARY KEY,
  location_id        INT NOT NULL REFERENCES blinkit_locations(location_id),
  sku_id             TEXT NOT NULL REFERENCES skus(sku_id),
  target_days_cover  INT DEFAULT 14,
  min_replenish_qty  INT DEFAULT 5,
  trigger_days_cover INT DEFAULT 7,
  is_active          BOOLEAN DEFAULT TRUE,
  UNIQUE(location_id, sku_id)
);

-- ── Amazon FBA ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS amazon_warehouses (
  wh_id      SERIAL PRIMARY KEY,
  name       TEXT NOT NULL,
  code       TEXT UNIQUE NOT NULL,
  city       TEXT,
  is_active  BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO amazon_warehouses (name, code, city)
VALUES ('Amazon FC (Primary)', 'AZ_FC_01', 'Mumbai')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS amazon_fba_inventory (
  fba_inv_id   SERIAL PRIMARY KEY,
  wh_id        INT NOT NULL REFERENCES amazon_warehouses(wh_id),
  sku_id       TEXT NOT NULL REFERENCES skus(sku_id),
  qty_on_hand  INT NOT NULL DEFAULT 0,
  qty_reserved INT NOT NULL DEFAULT 0,
  report_date  DATE NOT NULL,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(wh_id, sku_id, report_date)
);

-- ── Sales, POs, Invoices ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS orders (
  order_id           TEXT NOT NULL,
  channel_id         INT NOT NULL REFERENCES channels(channel_id),
  order_date         DATE NOT NULL,
  sku_id             TEXT NOT NULL REFERENCES skus(sku_id),
  quantity           INT NOT NULL DEFAULT 1,
  mrp                NUMERIC(10,2),
  selling_price      NUMERIC(10,2),
  gross_value        NUMERIC(10,2),
  discount_pct       NUMERIC(5,2),
  commission_pct     NUMERIC(5,2),
  commission_amt     NUMERIC(10,2),
  logistics_cost     NUMERIC(10,2),
  ad_spend_allocated NUMERIC(10,2),
  cogs               NUMERIC(10,2),
  net_margin         NUMERIC(10,2),
  fulfillment_type   TEXT,
  city               TEXT,
  state              TEXT,
  platform_order_id  TEXT,
  status             TEXT DEFAULT 'FULFILLED' CHECK (status IN (
                       'PENDING','FULFILLED','CANCELLED','RTO','SALE_RETURN'
                     )),
  return_date        DATE,
  return_reason      TEXT,
  source_file        TEXT,
  PRIMARY KEY (order_id, channel_id)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
  po_id         SERIAL PRIMARY KEY,
  po_number     TEXT UNIQUE,
  supplier_id   INT NOT NULL REFERENCES suppliers(supplier_id),
  created_date  DATE DEFAULT CURRENT_DATE,
  expected_date DATE,
  received_date DATE,
  status        TEXT DEFAULT 'DRAFT' CHECK (status IN (
                  'DRAFT','SENT','CONFIRMED','PARTIAL','RECEIVED','CANCELLED'
                )),
  total_value   NUMERIC(10,2),
  advance_paid  NUMERIC(10,2),
  balance_due   NUMERIC(10,2),
  notes         TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
  poi_id             SERIAL PRIMARY KEY,
  po_id              INT NOT NULL REFERENCES purchase_orders(po_id),
  item_id            INT NOT NULL REFERENCES items(item_id),
  quantity_ordered   INT NOT NULL,
  cost_per_unit      NUMERIC(10,4),
  line_total         NUMERIC(10,2),
  quantity_received  INT DEFAULT 0,
  batch_code_received TEXT,
  notes              TEXT
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
  inv_item_id SERIAL PRIMARY KEY,
  invoice_id  INT NOT NULL REFERENCES invoices(invoice_id),
  sku_id      TEXT NOT NULL REFERENCES skus(sku_id),
  hsn_code    TEXT,
  description TEXT,
  quantity    INT NOT NULL,
  mrp         NUMERIC(10,2),
  rate        NUMERIC(10,2),
  line_total  NUMERIC(10,2),
  gst_pct     NUMERIC(5,2),
  gst_amt     NUMERIC(10,2),
  cogs        NUMERIC(10,2)
);

-- ── Forecasting / replenishment ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS replenishment_recommendations (
  rec_id             SERIAL PRIMARY KEY,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  rec_type           TEXT NOT NULL CHECK (rec_type IN (
                       'DARKSTORE_REPLENISHMENT','FBA_REPLENISHMENT','SUPPLIER_PO'
                     )),
  sku_id             TEXT REFERENCES skus(sku_id),
  item_id            INT REFERENCES items(item_id),
  from_channel_id    INT REFERENCES channels(channel_id),
  to_location_id     INT REFERENCES blinkit_locations(location_id),
  recommended_qty    INT,
  current_stock      INT,
  days_of_cover      NUMERIC(5,1),
  avg_daily_velocity NUMERIC(8,3),
  trigger_reason     TEXT,
  status             TEXT DEFAULT 'OPEN' CHECK (status IN (
                       'OPEN','APPROVED','DISPATCHED','REJECTED'
                     )),
  approved_at        TIMESTAMPTZ,
  dispatched_at      TIMESTAMPTZ,
  notes              TEXT
);

CREATE TABLE IF NOT EXISTS demand_forecasts (
  forecast_id    SERIAL PRIMARY KEY,
  sku_id         TEXT NOT NULL REFERENCES skus(sku_id),
  channel_id     INT NOT NULL REFERENCES channels(channel_id),
  forecast_month DATE NOT NULL,
  forecast_units INT,
  confidence_lo  INT,
  confidence_hi  INT,
  model          TEXT DEFAULT '3M_WEIGHTED',
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(sku_id, channel_id, forecast_month)
);

-- ── Company config ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS company_config (
  config_id  SERIAL PRIMARY KEY,
  key        TEXT UNIQUE NOT NULL,
  value      TEXT,
  notes      TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO company_config (key, value, notes) VALUES
  ('company_name',       'Goodsense Trading India Private Limited',  'Legal company name for invoices'),
  ('gstin',              '29AALCG8970F1Z0',                           'Our GSTIN'),
  ('pan',                'AALCG8970F',                                'Company PAN'),
  ('registered_address', 'No. 2731, First Floor, HAL 3rd Stage, New Thippasandra, Bengaluru, Karnataka - 560075', 'Full registered address'),
  ('bank_name',          'HDFC Bank Ltd.',                           'Bank name'),
  ('account_name',       'GOODSENSE TRADING INDIA PRIVATE LIMITED',  'Bank account name as registered'),
  ('bank_account',       '50200107154878',                           'Account number'),
  ('bank_ifsc',          'HDFC0000075',                              'IFSC code'),
  ('invoice_prefix',     'GT_26-27_',                                'e.g. TCB/2026-27/'),
  ('invoice_counter',    '0',                                        'Current invoice number counter (integer as text)')
ON CONFLICT (key) DO NOTHING;

-- ── Views ─────────────────────────────────────────────────────────────────────

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
JOIN items i    ON i.item_id    = inv.item_id
JOIN channels c ON c.channel_id = inv.channel_id;

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
  c.name AS channel, c.code AS channel_code,
  o.sku_id, s.name AS sku_name,
  COUNT(DISTINCT o.order_id || o.channel_id::TEXT) AS order_count,
  SUM(o.quantity)          AS units_sold,
  SUM(o.gross_value)       AS gross_revenue,
  SUM(o.commission_amt)    AS total_commission,
  SUM(o.logistics_cost)    AS total_logistics,
  SUM(o.cogs)              AS total_cogs,
  SUM(o.ad_spend_allocated) AS total_ad_spend,
  SUM(o.net_margin)        AS total_net_margin
FROM orders o
JOIN channels c ON c.channel_id = o.channel_id
JOIN skus s     ON s.sku_id     = o.sku_id
WHERE o.status != 'CANCELLED'
GROUP BY 1,2,3,4,5;

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
  COALESCE(sh.total_shipped,    0) AS total_shipped,
  COALESCE(bs.total_at_blinkit, 0) AS stock_at_blinkit,
  COALESCE(bd.total_sold,       0) AS total_sold_by_blinkit,
  COALESCE(sh.total_shipped, 0)
    - COALESCE(bs.total_at_blinkit, 0)
    - COALESCE(bd.total_sold, 0)   AS discrepancy
FROM skus s
LEFT JOIN shipped       sh ON sh.sku_id = s.sku_id
LEFT JOIN blinkit_stock bs ON bs.sku_id = s.sku_id
LEFT JOIN blinkit_sold  bd ON bd.sku_id = s.sku_id
WHERE s.is_discontinued = FALSE;

-- ── Migration 23: Blinkit replenishment plan cache ────────────────────────────
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
