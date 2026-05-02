-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 008 — SKU COGS lots + schema gap fixes
-- Run on BOTH dev and prod.
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Fix dev/prod schema gap: sku_pricing was missing sp + updated_at
ALTER TABLE sku_pricing
  ADD COLUMN IF NOT EXISTS sp         NUMERIC(10,2),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- 2. Enable per-WH tracking on SKU inventory transfers (needed for Blinkit WH lots)
ALTER TABLE sku_inventory_transactions
  ADD COLUMN IF NOT EXISTS partner_location_id INT
    REFERENCES blinkit_locations(location_id);

-- 3. FIFO COGS lot table
--    One row per (sku, channel, [blinkit_wh], assembled_date, unit_cogs).
--    Two partial unique indexes replace a single NULLS NOT DISTINCT constraint
--    for clarity and broad PG compatibility.
CREATE TABLE IF NOT EXISTS sku_cogs_lots (
  lot_id              SERIAL PRIMARY KEY,
  sku_id              TEXT NOT NULL REFERENCES skus(sku_id),
  channel_id          INT  NOT NULL REFERENCES channels(channel_id),
  partner_location_id INT  REFERENCES blinkit_locations(location_id),
  assembled_at        DATE NOT NULL,
  unit_cogs           NUMERIC(10,4) NOT NULL,
  qty_assembled       INT  NOT NULL DEFAULT 0,
  qty_remaining       INT  NOT NULL DEFAULT 0,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Uniqueness: rows without a Blinkit WH (OWN_WH + non-Blinkit partners)
CREATE UNIQUE INDEX IF NOT EXISTS ux_sku_cogs_lots_no_loc
  ON sku_cogs_lots (sku_id, channel_id, assembled_at, unit_cogs)
  WHERE partner_location_id IS NULL;

-- Uniqueness: rows tied to a specific Blinkit WH
CREATE UNIQUE INDEX IF NOT EXISTS ux_sku_cogs_lots_with_loc
  ON sku_cogs_lots (sku_id, channel_id, partner_location_id, assembled_at, unit_cogs)
  WHERE partner_location_id IS NOT NULL;

-- FIFO scan index: quickly find and sort open lots per SKU × location
CREATE INDEX IF NOT EXISTS idx_sku_cogs_lots_fifo
  ON sku_cogs_lots (sku_id, channel_id, partner_location_id, assembled_at);
