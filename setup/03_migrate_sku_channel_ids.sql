-- Migration: simplify sku_channel_ids table
-- Run in Supabase SQL Editor

-- Step 1: Add new columns
ALTER TABLE sku_channel_ids ADD COLUMN IF NOT EXISTS blinkit_item_id TEXT;

-- Step 2: Migrate data into merged platform_pid
-- Amazon: move ASIN into platform_pid (where pid is null)
UPDATE sku_channel_ids
SET platform_pid = platform_asin
WHERE channel_code = 'AZ' AND platform_asin IS NOT NULL AND platform_pid IS NULL;

-- First Cry: move product_id into platform_pid
UPDATE sku_channel_ids
SET platform_pid = platform_product_id
WHERE channel_code = 'FC' AND platform_product_id IS NOT NULL AND platform_pid IS NULL;

-- Blinkit: move item_id into blinkit_item_id
UPDATE sku_channel_ids
SET blinkit_item_id = platform_item_id
WHERE channel_code = 'BLK' AND platform_item_id IS NOT NULL;

-- Step 3: Drop old columns
ALTER TABLE sku_channel_ids DROP COLUMN IF EXISTS platform_asin;
ALTER TABLE sku_channel_ids DROP COLUMN IF EXISTS platform_product_id;
ALTER TABLE sku_channel_ids DROP COLUMN IF EXISTS platform_item_id;
