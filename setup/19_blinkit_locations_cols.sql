-- Add Blinkit-specific columns to blinkit_locations
ALTER TABLE blinkit_locations ADD COLUMN IF NOT EXISTS blinkit_facility_id INT UNIQUE;
ALTER TABLE blinkit_locations ADD COLUMN IF NOT EXISTS state               TEXT;
ALTER TABLE blinkit_locations ADD COLUMN IF NOT EXISTS address             TEXT;
ALTER TABLE blinkit_locations ADD COLUMN IF NOT EXISTS stock_sent          BOOLEAN DEFAULT FALSE;
