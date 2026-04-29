-- Migration 007: drop amazon_fba_inventory and dependent view
-- Superseded by partner_soh_snapshots (Phase B).
-- Reconciliation view will be rebuilt in Phase B against partner_soh_snapshots.

DROP VIEW  IF EXISTS v_amazon_reconciliation;
DROP TABLE IF EXISTS amazon_fba_inventory;
