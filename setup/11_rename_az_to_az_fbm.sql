UPDATE channels SET name = 'Amazon FBM', code = 'AZ_FBM' WHERE code = 'AZ';
UPDATE sku_channel_ids SET channel_code = 'AZ_FBM' WHERE channel_code = 'AZ';
