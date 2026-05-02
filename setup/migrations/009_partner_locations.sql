-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 009 — Unified partner_locations table for SOR channels
--
-- Consolidates blinkit_locations + amazon_locations + any future SOR partner WHs
-- into a single table so adding a new SOR channel (Zepto, Instamart, etc.)
-- needs no schema change — just new rows.
--
-- The channel-specific tables (blinkit_locations, amazon_locations) are KEPT
-- for their partner-specific metadata. Only the FKs on inventory tracking
-- tables are re-pointed to partner_locations.
--
-- Run on BOTH dev and prod after migration 008.
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Unified table
CREATE TABLE IF NOT EXISTS partner_locations (
  location_id        SERIAL PRIMARY KEY,
  channel_id         INT  NOT NULL REFERENCES channels(channel_id),
  name               TEXT NOT NULL,
  code               TEXT,
  city               TEXT,
  state              TEXT,
  location_type      TEXT,                -- 'WH', 'DARKSTORE', 'FC'
  parent_location_id INT  REFERENCES partner_locations(location_id),
  external_id        TEXT,               -- partner's own facility ID (as text)
  is_active          BOOLEAN NOT NULL DEFAULT TRUE,
  address            TEXT,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Migrate Blinkit locations preserving existing IDs so existing
--    sku_cogs_lots / sku_inventory_transactions rows stay valid with no data fix.
INSERT INTO partner_locations
  (location_id, channel_id, name, code, city, state, location_type,
   external_id, is_active, address, created_at)
SELECT
  location_id,
  channel_id,
  name,
  code,
  city,
  state,
  location_type,
  blinkit_facility_id::TEXT,
  is_active,
  address,
  created_at
FROM blinkit_locations
ON CONFLICT (location_id) DO NOTHING;

-- 3. Migrate Amazon FBA WH.
--    amazon_locations.wh_id=2 collides with blinkit location_id=2, so no
--    explicit ID — SERIAL assigns the next free value.
INSERT INTO partner_locations
  (channel_id, name, code, city, state, location_type,
   external_id, is_active, address, created_at)
SELECT
  channel_id,
  name,
  code,
  city,
  state,
  location_type,
  amazon_facility_id,
  is_active,
  address,
  created_at
FROM amazon_locations
ON CONFLICT DO NOTHING;

-- 4. Placeholder Ozi WH — update name/address on next physical shipment to Ozi.
INSERT INTO partner_locations
  (channel_id, name, code, city, state, location_type, is_active)
VALUES
  (8, 'Ozi Warehouse (Placeholder)', 'OZI_WH_001', 'Bengaluru', 'Karnataka', 'WH', TRUE)
ON CONFLICT DO NOTHING;

-- 5. Reset SERIAL sequence to MAX(location_id) so future inserts don't collide
--    with the explicitly-inserted Blinkit rows.
SELECT setval(
  'partner_locations_location_id_seq',
  (SELECT MAX(location_id) FROM partner_locations)
);

-- 6. Re-point sku_inventory_transactions.partner_location_id → partner_locations
ALTER TABLE sku_inventory_transactions
  DROP CONSTRAINT IF EXISTS sku_inventory_transactions_partner_location_id_fkey;
ALTER TABLE sku_inventory_transactions
  ADD CONSTRAINT sku_inventory_transactions_partner_location_id_fkey
  FOREIGN KEY (partner_location_id) REFERENCES partner_locations(location_id);

-- 7. Re-point sku_cogs_lots.partner_location_id → partner_locations
ALTER TABLE sku_cogs_lots
  DROP CONSTRAINT IF EXISTS sku_cogs_lots_partner_location_id_fkey;
ALTER TABLE sku_cogs_lots
  ADD CONSTRAINT sku_cogs_lots_partner_location_id_fkey
  FOREIGN KEY (partner_location_id) REFERENCES partner_locations(location_id);
