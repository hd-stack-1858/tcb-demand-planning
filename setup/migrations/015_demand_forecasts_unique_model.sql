-- Phase D: allow VELOCITY_BASE + USER_FINAL rows to coexist per (sku, channel, month)
-- The original UNIQUE(sku_id, channel_id, forecast_month) only allows one row per cell,
-- which blocks storing both the engine output and the user override simultaneously.
-- New constraint: UNIQUE(sku_id, channel_id, forecast_month, model)

DO $$
DECLARE
  _c text;
BEGIN
  SELECT constraint_name INTO _c
  FROM information_schema.table_constraints
  WHERE table_name = 'demand_forecasts'
    AND constraint_type = 'UNIQUE'
    AND constraint_name NOT LIKE '%pkey%';

  IF _c IS NOT NULL THEN
    EXECUTE format('ALTER TABLE demand_forecasts DROP CONSTRAINT %I', _c);
    RAISE NOTICE 'Dropped old constraint: %', _c;
  ELSE
    RAISE NOTICE 'No existing UNIQUE constraint found (table may already be migrated)';
  END IF;
END $$;

ALTER TABLE demand_forecasts
  ADD CONSTRAINT demand_forecasts_sku_channel_month_model_key
  UNIQUE (sku_id, channel_id, forecast_month, model);
