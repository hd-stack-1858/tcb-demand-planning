-- Migration 25: Add lot_id FK to sku_inventory_transactions
-- Provides traceability: which COGS lot funded each dispatch/disassembly.
-- Nullable — stamped on DISPATCH/TRANSFER_OUT/DISASSEMBLY; NULL on ASSEMBLY/RETURN/ADJUSTMENT.
-- Single-lot dispatches get lot_id; multi-lot dispatches (rare) get NULL.

ALTER TABLE sku_inventory_transactions
  ADD COLUMN IF NOT EXISTS lot_id INT REFERENCES sku_cogs_lots(lot_id);

CREATE INDEX IF NOT EXISTS idx_sku_inv_txns_lot_id
  ON sku_inventory_transactions (lot_id)
  WHERE lot_id IS NOT NULL;
