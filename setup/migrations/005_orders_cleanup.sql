-- Migration 005: orders table cleanup
-- 1. Rename darkstore_id → partner_location_id; drop FK to blinkit_locations.
--    Column is now a polymorphic reference: for BLK orders references
--    blinkit_locations.location_id; for AZ orders references amazon_locations.wh_id.
--    channel_id determines which table to join — no FK constraint needed.
-- 2. Add CHECK constraint on fulfillment_type: DROP_SHIP, OUTRIGHT, SOR only.

ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_darkstore_id_fkey;
ALTER TABLE orders RENAME COLUMN darkstore_id TO partner_location_id;

ALTER TABLE orders
  ADD CONSTRAINT orders_fulfillment_type_check
  CHECK (fulfillment_type IN ('DROP_SHIP', 'OUTRIGHT', 'SOR'));
