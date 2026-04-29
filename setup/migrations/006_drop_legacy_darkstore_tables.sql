-- Migration 006: drop legacy darkstore tables and dependent views
-- darkstore_sales and darkstore_inventory are superseded by:
--   orders (sell-out, with partner_location_id for darkstore granularity)
--   partner_soh_snapshots (inventory snapshots, Phase B)
-- Reconciliation views will be rebuilt in Phase B against the new tables.

DROP VIEW  IF EXISTS v_darkstore_doc;
DROP VIEW  IF EXISTS v_blinkit_reconciliation;
DROP TABLE IF EXISTS darkstore_sales;
DROP TABLE IF EXISTS darkstore_inventory;
