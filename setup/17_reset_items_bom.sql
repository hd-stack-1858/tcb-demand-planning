-- Clean reset of items and bom with sequential item_ids
-- Safe to run as no inventory/batch data has been loaded yet

TRUNCATE TABLE bom        RESTART IDENTITY CASCADE;
TRUNCATE TABLE items      RESTART IDENTITY CASCADE;
