-- Mark permanently-closed Blinkit WHs as inactive in partner_locations.
--
-- Confirmed 2026-07-10/11: these WHs show zero dark stores with any
-- non-closed eligibility status (Total DS == DS Closed, or 0 DS entirely) —
-- Blinkit itself has told us they are closed for good, not a temporary gap.
-- If Blinkit relaunches service in any of these cities, it comes under a new
-- WH code, which the performance loader's ensure_whs_exist() now auto-creates
-- (see docs/plans/humble-questing-graham.md) — so there is no need to leave
-- these rows active "just in case."
--
-- This does NOT affect the "Warehouse — City Mapping" table's own defensive
-- filter (Total DS == DS Closed) in ui/growthspurt_app.py — that stays in
-- place as a self-healing safety net for any WH that goes fully dark in the
-- future without anyone manually flagging it here.

UPDATE partner_locations SET is_active = FALSE
WHERE location_type = 'WH' AND channel_id = 4
  AND name IN (
    'Chennai C5 - Feeder',
    'Coimbatore C1 - Feeder',
    'Guwahati G1 - Feeder Warehouse',
    'Kolkata K4 - Feeder',
    'Patna P1 - Feeder',
    'Visakhapatnam V1 - Feeder'
  );
