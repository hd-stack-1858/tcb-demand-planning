-- Migration 020 — Fix blinkit_inventory_snapshots: add unsellable + recalled columns
--
-- Context: loader had wrong column names so total_sellable, units_incoming,
-- and last_Xd_sales were always stored as 0. Reprocessing SOH files after this
-- migration will backfill all rows correctly via the loader's upsert.
--
-- Run on BOTH dev and prod.

ALTER TABLE blinkit_inventory_snapshots
  ADD COLUMN IF NOT EXISTS units_unsellable INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS units_recalled   INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN blinkit_inventory_snapshots.units_unsellable IS
  'Total unsellable at Blinkit (damaged + lost + expired + near expiry). SOH col: Total unsellable.';

COMMENT ON COLUMN blinkit_inventory_snapshots.units_recalled IS
  'Units in recall process — being returned to us. SOH col: Recalled inventory.
   These are still in our sku_cogs_lots until return_sku() is processed.';
