-- Migration 002: Add UUID default to orders.order_id
-- orders.order_id is TEXT NOT NULL but had no default — inserts from
-- the app were failing. Run in both prod and dev.

-- NOTE: orders_order_id is TEXT (not int), so no sequence is needed.
ALTER TABLE orders ALTER COLUMN order_id SET DEFAULT gen_random_uuid()::text;
