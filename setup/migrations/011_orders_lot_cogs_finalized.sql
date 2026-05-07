-- Migration 011: add lot_cogs_finalized flag to orders
-- Tracks whether FIFO lot consumption has been applied to an order's COGS.
-- Set TRUE by load_blinkit_payout.py (and future Amazon payout loader) after
-- consuming sku_cogs_lots and writing the actual lot-derived COGS to orders.cogs.
-- Prevents double-consumption if a payout script is re-run.

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS lot_cogs_finalized BOOLEAN NOT NULL DEFAULT FALSE;
