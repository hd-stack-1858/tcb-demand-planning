-- Rename Blinkit WH partner_locations.name to exactly match Blinkit's
-- serving_wh strings in the performance detail report.
-- Required for the new WH-level COGS finalization (K1 Phase G2c).
--
-- NEVER ACTUALLY APPLIED TO PROD (found 2026-07-10) — confirmed via dev
-- (freshly synced from prod) still showing all 6 old-style names below.
-- Kolkata K6 was also missing from the original version of this file —
-- added here so this migration is complete before it's finally run.

UPDATE partner_locations SET name = 'Bengaluru B3 - Feeder'    WHERE name = 'Bengaluru B3';
UPDATE partner_locations SET name = 'Kundli - Feeder'           WHERE name = 'Kundli Feeder';
UPDATE partner_locations SET name = 'Pune P3 - Feeder'          WHERE name = 'Pune P3 - Feeder Warehouse';
UPDATE partner_locations SET name = 'Rajpura R2 - Feeder'       WHERE name = 'Rajpura R2 - Feeder Warehouse';
UPDATE partner_locations SET name = 'Super Store Lucknow L4'    WHERE name = 'Lucknow L4';
UPDATE partner_locations SET name = 'Kolkata K6 - Feeder'       WHERE name = 'Kolkata K6 - Feeder Warehouse';
