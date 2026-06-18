-- Rename Blinkit WH partner_locations.name to exactly match Blinkit's
-- serving_wh strings in the performance detail report.
-- Required for the new WH-level COGS finalization (K1 Phase G2c).

UPDATE partner_locations SET name = 'Bengaluru B3 - Feeder'    WHERE name = 'Bengaluru B3';
UPDATE partner_locations SET name = 'Kundli - Feeder'           WHERE name = 'Kundli Feeder';
UPDATE partner_locations SET name = 'Pune P3 - Feeder'          WHERE name = 'Pune P3 - Feeder Warehouse';
UPDATE partner_locations SET name = 'Rajpura R2 - Feeder'       WHERE name = 'Rajpura R2 - Feeder Warehouse';
UPDATE partner_locations SET name = 'Super Store Lucknow L4'    WHERE name = 'Lucknow L4';
