-- Dev catch-up: add batch_id FK column + drop the old single-row-per-item
-- unique constraint from the inventory table.
-- Prod already has this schema (batch_id column present, no item_channel_uq constraint).
-- This migration only needs to run on dev (or fresh environments cloned from old schema).

ALTER TABLE inventory ADD COLUMN IF NOT EXISTS batch_id INTEGER REFERENCES item_batches(batch_id);

ALTER TABLE inventory DROP CONSTRAINT IF EXISTS inventory_item_channel_uq;
