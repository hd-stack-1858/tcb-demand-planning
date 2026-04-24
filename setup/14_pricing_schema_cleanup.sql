-- 1. Drop sku_channel_sp (SP is uniform across channels, lives in sku_pricing)
DROP TABLE IF EXISTS sku_channel_sp;

-- 2. Remove cogs from sku_pricing (COGS is batch-derived, not static)
--    Add sp (selling price) since it belongs here alongside MRP
ALTER TABLE sku_pricing DROP COLUMN IF EXISTS cogs;
ALTER TABLE sku_pricing ADD COLUMN IF NOT EXISTS sp NUMERIC(10,2);

-- 3. Create sku_channel_tp — transfer price per SKU × channel (TP channels only)
CREATE TABLE IF NOT EXISTS sku_channel_tp (
  tp_id          SERIAL PRIMARY KEY,
  sku_id         TEXT NOT NULL REFERENCES skus(sku_id),
  channel_code   TEXT NOT NULL CHECK (channel_code IN ('FNP','FC','PEEKO','KIDDO','OZI')),
  transfer_price NUMERIC(10,2) NOT NULL,
  effective_date DATE NOT NULL,
  notes          TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  updated_at     TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(sku_id, channel_code, effective_date)
);

-- 4. Add unit_cogs to sku_inventory_transactions (actual COGS at assembly time)
ALTER TABLE sku_inventory_transactions ADD COLUMN IF NOT EXISTS unit_cogs NUMERIC(10,4);
