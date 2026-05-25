-- Migration 014: add lot_id and supply_state to orders
-- lot_id: FK to sku_cogs_lots — set when COGS is finalized from a single lot (NULL for multi-lot).
--         Enables direct order → lot traceability for Blinkit (finalize_blk_cogs) and future channels.
-- supply_state: state the WH that supplied the order is in — captured from Blinkit sales CSV col 11.
--               Used for tier-1 state-level lot FIFO in consume_sor_sale().

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS lot_id        INT  REFERENCES sku_cogs_lots(lot_id),
  ADD COLUMN IF NOT EXISTS supply_state  TEXT;

CREATE INDEX IF NOT EXISTS idx_orders_lot_id
  ON orders (lot_id)
  WHERE lot_id IS NOT NULL;
