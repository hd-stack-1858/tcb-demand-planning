-- 017: Drop blinkit_performance_ads
-- Superseded by blinkit_performance_detail (migration 016).
-- blinkit_performance_detail uses Column Q (inventory_available) as the DS-level OOS signal
-- instead of the WH-level wh_oos_flag derived from the Remarks column.
-- All downstream consumers (replenishment engine, forecasting, UI) already use
-- blinkit_performance_detail. Trigger 2 updated to check Column Q integrity.

DROP TABLE IF EXISTS blinkit_performance_ads;
