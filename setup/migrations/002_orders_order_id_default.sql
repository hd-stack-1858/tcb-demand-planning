-- Migration 002: Add UUID default to orders.order_id
-- orders.order_id is TEXT NOT NULL but had no default — inserts from
-- the app were failing. Run in both prod and dev.

CREATE SEQUENCE IF NOT EXISTS orders_order_id_seq;
ALTER TABLE orders ALTER COLUMN order_id SET DEFAULT gen_random_uuid()::text;
