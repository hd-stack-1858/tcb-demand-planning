-- Migration: rename type -> business_model, fix values, mark OWN_WH as location

-- Step 1: Drop the old CHECK constraint on type
ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_type_check;

-- Step 2: Rename column
ALTER TABLE channels RENAME COLUMN type TO business_model;

-- Step 2b: Drop NOT NULL so OWN_WH/ZEPTO/INSTAMART can have NULL business_model
ALTER TABLE channels ALTER COLUMN business_model DROP NOT NULL;

-- Step 3: Add is_location flag (TRUE only for OWN_WH)
ALTER TABLE channels ADD COLUMN IF NOT EXISTS is_location BOOLEAN DEFAULT FALSE;
UPDATE channels SET is_location = TRUE WHERE code = 'OWN_WH';

-- Step 4: Update business_model values to correct ones
UPDATE channels SET business_model = 'FBA'       WHERE code = 'AZ_FBA';
UPDATE channels SET business_model = 'DROP_SHIP'  WHERE code IN ('AZ_FBM', 'FNP', 'FC');
UPDATE channels SET business_model = 'SOR'        WHERE code IN ('BLK', 'OZI');
UPDATE channels SET business_model = 'OUTRIGHT'   WHERE code IN ('PEEKO', 'KIDDO');
UPDATE channels SET business_model = 'DIRECT'     WHERE code = 'D2C';
UPDATE channels SET business_model = NULL         WHERE code IN ('ZEPTO', 'INSTAMART', 'OWN_WH');

-- Step 5: Add new CHECK constraint with correct values
ALTER TABLE channels ADD CONSTRAINT channels_business_model_check
  CHECK (business_model IN ('DROP_SHIP','FBA','SOR','OUTRIGHT','DIRECT') OR business_model IS NULL);
