-- Full reset of batch/cost/supplier data before re-seeding
-- Must delete in this order (FK constraints: inventory → item_batches → suppliers)
DELETE FROM inventory;
DELETE FROM item_batches;
DELETE FROM suppliers;
