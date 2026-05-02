-- Seed sku_channel_ids for Blinkit channel (channel_code = 'BLK').
-- Run on dev DB only — prod is already populated.
-- platform_pid          = Blinkit PID (product-level)
-- platform_pid_additional = Blinkit Item ID (used in sales/payout reports)
-- platform_upc          = barcode
INSERT INTO sku_channel_ids (sku_id, channel_code, platform_sku, platform_pid, platform_pid_additional, platform_upc)
VALUES
  ('TCB001',   'BLK', 'TCB001',   '729524', '10271993', '8904492301572'),
  ('TCB002',   'BLK', 'TCB002',   '728981', '10271630', '8904492390002'),
  ('TCB003',   'BLK', 'TCB003',   '730250', '10272608', '8904492390040'),
  ('TCB004',   'BLK', 'TCB004',   '729548', '10272017', '8904492390019'),
  ('TCB005',   'BLK', 'TCB005',   '730293', '10272641', '8904492390057'),
  ('TCB006',   'BLK', 'TCB006',   '730230', '10272588', '8904492390064'),
  ('TCB007',   'BLK', 'TCB007',   'Not listed', 'Not listed', 'Not registered with GS1'),
  ('TCB008',   'BLK', 'TCB008',   '731714', '10273430', '8904492390026'),
  ('TCB009',   'BLK', 'TCB009',   '732471', '10274008', '8904492390071'),
  ('TCB009_1', 'BLK', 'TCB009_1', '732471', '10274008', '8904492390071'),
  ('TCB010',   'BLK', 'TCB010',   '749746', '10285562', '21449631'),
  ('TCB011',   'BLK', 'TCB011',   '745246', '10282817', '21449585'),
  ('TCB012',   'BLK', 'TCB012',   '745249', '10282820', '21449608')
ON CONFLICT (sku_id, channel_code) DO NOTHING;
