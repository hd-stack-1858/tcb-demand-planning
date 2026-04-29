-- Migration 004: inventory_transactions cleanup
-- Drop unit_cost column — never populated, redundant with item_batches.cost_per_unit.
-- from_channel_id is now populated for SALE_RETURN rows (passed from app).

ALTER TABLE inventory_transactions DROP COLUMN unit_cost;
