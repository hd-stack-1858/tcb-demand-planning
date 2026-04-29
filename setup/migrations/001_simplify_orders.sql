-- Migration 001: Simplify orders table for Sales MIS
-- Remove P&L columns that belong in a future dedicated P&L table.
-- Run this in BOTH prod and dev Supabase SQL editors.

ALTER TABLE orders
    DROP COLUMN IF EXISTS commission_pct,
    DROP COLUMN IF EXISTS commission_amt,
    DROP COLUMN IF EXISTS logistics_cost,
    DROP COLUMN IF EXISTS ad_spend_allocated,
    DROP COLUMN IF EXISTS net_margin;
