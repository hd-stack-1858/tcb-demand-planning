-- Migration 003: amazon_warehouses → amazon_locations
-- Renamed and expanded to match blinkit_locations structure.
-- Supports multiple Amazon FCs/WHs in future. BLR8 is the only active WH.

ALTER TABLE amazon_warehouses RENAME TO amazon_locations;

ALTER TABLE amazon_locations
  ADD COLUMN channel_id         INTEGER REFERENCES channels(channel_id),
  ADD COLUMN location_type      TEXT,
  ADD COLUMN parent_wh_id       INTEGER REFERENCES amazon_locations(wh_id),
  ADD COLUMN state              TEXT,
  ADD COLUMN address            TEXT,
  ADD COLUMN stock_sent         BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN amazon_facility_id TEXT;

DELETE FROM amazon_locations WHERE wh_id = 1;

INSERT INTO amazon_locations
  (channel_id, name, code, city, state, address, is_active,
   location_type, amazon_facility_id, stock_sent)
VALUES (
  2,
  'Amazon Seller Services Pvt Ltd BLR8',
  'AZ_BLR8',
  'Bengaluru',
  'Karnataka',
  'Building 2 Wh 2, Plot no 12/P2, IT Sector,Hitech, Defence and Aerospace Park, Devanahalli, Bengaluru-562149',
  TRUE,
  'Warehouse',
  'BLR8',
  TRUE
);
