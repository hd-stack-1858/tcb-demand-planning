-- Migration 010 — Rename AZ_FBA → AZ
--
-- AZ_FBA was a redundant suffix — TCB only has one Amazon FBA channel.
-- AZ_FBM (drop-ship from OWN_WH) keeps its code as it's a distinct fulfillment model.
-- sku_channel_ids was incorrectly tagged AZ_FBM; those rows belong to the AZ channel.
--
-- Run on dev and prod.

UPDATE channels
   SET code = 'AZ', name = 'Amazon'
 WHERE code = 'AZ_FBA';

UPDATE sku_channel_ids
   SET channel_code = 'AZ'
 WHERE channel_code = 'AZ_FBM';
