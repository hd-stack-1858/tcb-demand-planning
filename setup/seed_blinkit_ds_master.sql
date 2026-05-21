-- Blinkit Dark Store Master Seed
-- Generated 2026-05-21 from performance detail CSVs + May 1-15 ageing file.
-- Run AFTER migration 22 is applied to prod.
--
-- Matching: (1) exact name vs ageing Outlet Names;
--   (2) prefix-stripped match (SS/LT/ES/Super Store = store-type tag, not identity).
--
-- DS marked NEEDS_OUTLET_ID: shipped to after May 15 (ageing predates shipment).
-- Fix: download May 16-31 ageing report, then:
--   UPDATE partner_locations SET external_id=<outlet_id> WHERE code=<code>;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Ballari Bhagat Singh Nagar ES6', 'BLK_DS_ES6', 'Ballari', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru BTM 2nd Stage ES189', 'BLK_DS_5572', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '5572', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Electronic City ES251', 'BLK_DS_6804', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '6804', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru HSR Layout ES261', 'BLK_DS_7038', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7038', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Horamavu Vibgyor ES269', 'BLK_DS_7181', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7181', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Hulimavu ES199', 'BLK_DS_5637', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '5637', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Jayanagar ES205', 'BLK_DS_ES205', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Kaggadasapura ES276', 'BLK_DS_7326', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7326', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Lalbagh Road ES244', 'BLK_DS_6659', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '6659', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Purnapragnya Uttarahalli ES279', 'BLK_DS_7369', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7369', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Tavarekere SG Palya ES304', 'BLK_DS_7775', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7775', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Thanisandra Kannuru ES295', 'BLK_DS_7670', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7670', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Whitefield ES242', 'BLK_DS_ES242', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'GS Bengaluru Jayanagar GS7', 'BLK_DS_GS_BENGALURU_JAYANAG', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru BTM 2nd Stage ES189', 'BLK_DS_5572', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '5572', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Balagere Road ES36', 'BLK_DS_2778', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '2778', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Devarabisanahalli ES273', 'BLK_DS_7262', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7262', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Doddakanneli ES314', 'BLK_DS_7949', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7949', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Electronic City ES251', 'BLK_DS_6804', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '6804', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Frazer Town ES318', 'BLK_DS_8109', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '8109', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru HSR Layout ES261', 'BLK_DS_7038', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7038', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Hebbal RT Nagar ES252', 'BLK_DS_6828', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '6828', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Horamavu Vibgyor ES269', 'BLK_DS_7181', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7181', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Hulimavu ES199', 'BLK_DS_5637', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '5637', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Hulimavu ES315', 'BLK_DS_8009', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '8009', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Kaggadasapura ES276', 'BLK_DS_7326', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7326', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Lalbagh Road ES244', 'BLK_DS_6659', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '6659', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Lingarajapuram ES256', 'BLK_DS_6877', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '6877', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Marathalli ES19 PR', 'BLK_DS_2149', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '2149', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Purnapragnya Uttarahalli ES279', 'BLK_DS_7369', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7369', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Rajajinagar ES312', 'BLK_DS_7927', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7927', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Tavarekere SG Palya ES304', 'BLK_DS_7775', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7775', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Thanisandra Kannuru ES295', 'BLK_DS_7670', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7670', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Whitefield ES242', 'BLK_DS_ES242', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Belathur ES141', 'BLK_DS_4767', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '4767', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Devarabisanahalli Bellandur ES273', 'BLK_DS_ES273', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Doddakannelli ES154', 'BLK_DS_5072', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '5072', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Doddanekundi ES138', 'BLK_DS_4764', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '4764', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Gopalan Colony Whitefield ES282', 'BLK_DS_7485', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7485', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Hoodi 3 ES294', 'BLK_DS_7655', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7655', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Lingarajapuram ES256', 'BLK_DS_6877', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '6877', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru New City Yelahanka ES187', 'BLK_DS_5505', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '5505', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Rashad Nagar ES252', 'BLK_DS_ES252', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Sarjapura ES310', 'BLK_DS_7912', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7912', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Talghattapura ES155', 'BLK_DS_5237', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '5237', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'Super Store Bengaluru Balagere Road ES36', 'BLK_DS_2778', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '2778', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'Super Store Bengaluru Marathalli ES19 PR', 'BLK_DS_2149', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '2149', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bidar Devi Nagar ES5', 'BLK_DS_ES5', 'Bidar', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Chennai Mogapair ES104', 'BLK_DS_7708', 'Chennai', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7708', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Chennai Madhavaram ES110', 'BLK_DS_7869', 'Chennai', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    '7869', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hosur Thally Road ES4', 'BLK_DS_ES4', 'Hosur', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Kurnool Bhagya Nagar ES16', 'BLK_DS_ES16', 'Kurnool', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_1873'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bahadurgarh Sector 6 ES4', 'BLK_DS_8001', 'Bahadurgarh', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '8001', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Paschim Vihar ES413', 'BLK_DS_7892', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '7892', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Adarsh Nagar ES223', 'BLK_DS_4452', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '4452', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Chattarpur ES396', 'BLK_DS_7669', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '7669', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Durga Puri ES422', 'BLK_DS_8064', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '8064', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Karol Bagh ES301', 'BLK_DS_5101', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '5101', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Keshavpuram ES296', 'BLK_DS_5043', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '5043', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Manglapuri ES256', 'BLK_DS_4648', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '4648', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Narela ES322', 'BLK_DS_5928', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '5928', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Nawada ES408', 'BLK_DS_ES408', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Rohini Sector 16 ES366', 'BLK_DS_7034', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '7034', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Rohini Sector 21 ES340', 'BLK_DS_6531', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '6531', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Sangam Vihar ES183', 'BLK_DS_ES183', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Sector 40 ES194', 'BLK_DS_ES194', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Aravali Hills ES192', 'BLK_DS_7953', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    '7953', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Gwal Pahari ES192', 'BLK_DS_ES192', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Karnal Friends Colony ES8', 'BLK_DS_ES8', 'Karnal', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Kurukshetra Pipli Road ES4', 'BLK_DS_ES4', 'Kurukshetra', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Meerut Ganga Nagar ES146', 'BLK_DS_ES146', 'Meerut', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Meerut Kankerkhera ES139', 'BLK_DS_ES139', 'Meerut', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Meerut Subedar Narendra Singh ES110', 'BLK_DS_ES110', 'Meerut', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2010'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Charkop Estate ES268', 'BLK_DS_ES268', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Dadar TT Circle ES228', 'BLK_DS_ES228', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Kalyan Khadakpada ES244', 'BLK_DS_ES244', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Kamothe ES272', 'BLK_DS_ES272', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Khargar Sector 19 ES142', 'BLK_DS_ES142', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Koparkhairane Sec 7 ES238', 'BLK_DS_ES238', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Lower Oshiwara ES190', 'BLK_DS_ES190', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Magathane ES234', 'BLK_DS_ES234', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Nerul West ES267', 'BLK_DS_ES267', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Seepz ES274', 'BLK_DS_ES274', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Thakurli ES222', 'BLK_DS_ES222', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Ulwe Kharkopar ES241', 'BLK_DS_ES241', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Mumbai Virar Peninsula ES269', 'BLK_DS_ES269', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Charkop Estate ES268', 'BLK_DS_ES268', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Dadar TT Circle ES228', 'BLK_DS_ES228', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Dahisar Maratha Colony ES212', 'BLK_DS_ES212', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai GMLR Nahur ES294', 'BLK_DS_ES294', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Govind Nagar ES261', 'BLK_DS_ES261', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Kalyan Khadakpada ES244', 'BLK_DS_ES244', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Kamothe ES272', 'BLK_DS_ES272', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Khargar Sector 19 ES142', 'BLK_DS_ES142', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Koparkhairane Sec 7 ES238', 'BLK_DS_ES238', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Lower Oshiwara ES190', 'BLK_DS_ES190', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Lower Parel ES165', 'BLK_DS_ES165', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING; -- !! NEEDS_OUTLET_ID

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Magathane ES234', 'BLK_DS_ES234', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Mira Road Ghoddev ES251', 'BLK_DS_ES251', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Nalasopara North ES290', 'BLK_DS_ES290', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Nerul West ES267', 'BLK_DS_ES267', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Seepz ES274', 'BLK_DS_ES274', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Thakurli ES222', 'BLK_DS_ES222', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Thane Kapurbawdi ES220', 'BLK_DS_ES220', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING; -- !! NEEDS_OUTLET_ID

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Thane Ovale ES256', 'BLK_DS_ES256', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Ulwe Kharkopar ES241', 'BLK_DS_ES241', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Mumbai Virar Peninsula ES269', 'BLK_DS_ES269', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Badlapur ES107', 'BLK_DS_ES107', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Chandivali Milan Colony ES246', 'BLK_DS_ES246', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Colaba ES180', 'BLK_DS_ES180', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Dahisar Maratha Colony ES212', 'BLK_DS_ES212', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Digha ES198', 'BLK_DS_ES198', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Dombivli West ES143', 'BLK_DS_ES143', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Goregaon East Churiwadi ES152', 'BLK_DS_ES152', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Govind Nagar ES261', 'BLK_DS_ES261', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Jogeshwari West ES221', 'BLK_DS_ES221', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Kamatghar Bhiwandi ES184', 'BLK_DS_ES184', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Khar Bandra ES224', 'BLK_DS_ES224', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Kurla West ES210', 'BLK_DS_ES210', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING; -- !! NEEDS_OUTLET_ID

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Lodha Palava 2 ES74', 'BLK_DS_ES74', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Lower Parel ES165', 'BLK_DS_ES165', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Marol ES105', 'BLK_DS_ES105', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Mira Road Ghoddev ES251', 'BLK_DS_ES251', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Mulund West ES108', 'BLK_DS_ES108', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Nahar Amritshakti ES287', 'BLK_DS_ES287', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Naigaon East ES159', 'BLK_DS_ES159', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Nalasopara East ES99', 'BLK_DS_ES99', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Nalasopara West ES218', 'BLK_DS_ES218', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Nilije Pada ES119', 'BLK_DS_ES119', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Nilje Palava ES278', 'BLK_DS_ES278', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Orlem Malad ES223', 'BLK_DS_ES223', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING; -- !! NEEDS_OUTLET_ID

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Runwal Kalyan ES167', 'BLK_DS_ES167', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Silphata ES177', 'BLK_DS_ES177', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Subhash Nagar ES273', 'BLK_DS_ES273', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Thane Kapurbawdi ES220', 'BLK_DS_ES220', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Thane Ovale ES256', 'BLK_DS_ES256', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Thane Waghle Industrial ES271', 'BLK_DS_ES271', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Tilak Nagar ES90', 'BLK_DS_ES90', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Ulhasnagar Kailash ES172', 'BLK_DS_ES172', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Vasai South ES229', 'BLK_DS_ES229', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Vikhroli ES85', 'BLK_DS_ES85', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Vile Parle West ES104', 'BLK_DS_ES104', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Vinay Nagar ES254', 'BLK_DS_ES254', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mumbai Virar East ES173', 'BLK_DS_ES173', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'Super Store Mumbai Mazgaon ES2', 'BLK_DS_ES2', 'Mumbai', 'Maharashtra', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Nashik Adgaon ES9', 'BLK_DS_ES9', 'Nashik', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Nashik Deolali Village ES10', 'BLK_DS_ES10', 'Nashik', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Nashik Gangapur Rd ES12', 'BLK_DS_ES12', 'Nashik', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Nashik Kamatwade ES13', 'BLK_DS_ES13', 'Nashik', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_2123'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gulbarga Dargah Road ES3', 'BLK_DS_ES3', 'Gulbarga', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Anjaiah Nagar ES176', 'BLK_DS_ES176', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Ayyappa Society ES189', 'BLK_DS_ES189', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Chikkadpally ES139', 'BLK_DS_ES139', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Domalguda ES192', 'BLK_DS_ES192', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Gautami Enclave ES191', 'BLK_DS_ES191', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Gowlidoddy ES171', 'BLK_DS_ES171', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Madhapur ES140', 'BLK_DS_ES140', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Madhura Nagar ES146', 'BLK_DS_ES146', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Masabtank ES148', 'BLK_DS_6260', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    '6260', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Moula Ali ES170', 'BLK_DS_ES170', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Narsingi ES186', 'BLK_DS_ES186', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Hyderabad Raj Bhavan Road ES193', 'BLK_DS_ES193', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Anjaiah Nagar ES176', 'BLK_DS_ES176', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Ayyappa Society ES189', 'BLK_DS_ES189', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Chikkadpally ES139', 'BLK_DS_ES139', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Domalguda ES192', 'BLK_DS_ES192', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Gautami Enclave ES191', 'BLK_DS_ES191', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Gowlidoddy ES171', 'BLK_DS_ES171', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING; -- !! NEEDS_OUTLET_ID

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Madhura Nagar ES146', 'BLK_DS_ES146', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Masabtank ES148', 'BLK_DS_6260', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    '6260', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Moula Ali ES170', 'BLK_DS_ES170', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Narsingi ES186', 'BLK_DS_ES186', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Raj Bhavan Road ES193', 'BLK_DS_ES193', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Hyderabad Regimental Bazar ES199', 'BLK_DS_ES199', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Attapur ES166', 'BLK_DS_ES166', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Bachupally ES63', 'BLK_DS_ES63', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Charminar ES112', 'BLK_DS_ES112', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Dammaiguda ES64', 'BLK_DS_ES64', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Gajularamaram ES122', 'BLK_DS_ES122', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Golden Mile Road ES131', 'BLK_DS_ES131', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad HMT Hills ES120', 'BLK_DS_ES120', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Hafeezpet ES74', 'BLK_DS_ES74', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Kondapur ES45 PR', 'BLK_DS_ES45_PR', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Kothapet ES111', 'BLK_DS_ES111', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Manikonda ES118', 'BLK_DS_ES118', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Moosapet ES81', 'BLK_DS_ES81', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Nagole ES62', 'BLK_DS_ES62', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Pbel City ES161', 'BLK_DS_ES161', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Pocharam ES116', 'BLK_DS_ES116', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Ramachandrapuram ES114', 'BLK_DS_ES114', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Rasoolpura ES153', 'BLK_DS_ES153', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Sabza Colony ES187', 'BLK_DS_ES187', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Saroornagar ES73', 'BLK_DS_ES73', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Suraram ES137', 'BLK_DS_ES137', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Tirumalagiri ES168', 'BLK_DS_ES168', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Uppal ES56', 'BLK_DS_ES56', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Upperpally ES80', 'BLK_DS_ES80', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Vasanth Nagar Colony ES190', 'BLK_DS_ES190', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING; -- !! NEEDS_OUTLET_ID

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Vijay Nagar ES175', 'BLK_DS_ES175', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Hyderabad Yakutpura ES179', 'BLK_DS_ES179', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'Super Store Hyderabad Kompally ES27', 'BLK_DS_ES27', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'Super Store Hyderabad Nalagandla ES3', 'BLK_DS_ES3', 'Hyderabad', 'Telangana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Rajahmundry Prakash Nagar ES1', 'BLK_DS_ES1', 'Rajahmundry', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Visakhapatnam Dwarka Nagar ES25', 'BLK_DS_ES25', 'Visakhapatnam', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_3201'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Agra Bardoli ES14', 'BLK_DS_ES14', 'Agra', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Agra Sikandra ES2', 'BLK_DS_ES2', 'Agra', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Aligarh Bypass ES5', 'BLK_DS_ES5', 'Aligarh', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bahadurgarh Sector 6 ES1', 'BLK_DS_ES1', 'Bahadurgarh', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bhiwadi Ashiana Village ES8', 'BLK_DS_ES8', 'Bhiwadi', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bhiwadi Thara ES6', 'BLK_DS_ES6', 'Bhiwadi', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, ' ES Delhi Kamla Nagar ES383', 'BLK_DS_7331', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7331', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi East Patel Nagar ES372', 'BLK_DS_7151', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7151', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Kalu Sarai ES371', 'BLK_DS_7133', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7133', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Kotla Village ES321', 'BLK_DS_5927', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '5927', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Laxmi Nagar ES374', 'BLK_DS_7192', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7192', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Model Town ES392', 'BLK_DS_7631', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7631', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Palam ES377', 'BLK_DS_7286', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7286', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Rajouri Garden ES353', 'BLK_DS_6856', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6856', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Rithala ES293', 'BLK_DS_5032', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '5032', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Sainik Farm ES394', 'BLK_DS_7646', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7646', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Sangam Vihar ES406', 'BLK_DS_7789', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7789', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Sant Nagar ES279', 'BLK_DS_ES279', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Sant Nagar ES391', 'BLK_DS_7629', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7629', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Sarita Vihar ES368', 'BLK_DS_7041', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7041', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Uttam Nagar Phase 1 ES352', 'BLK_DS_6812', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6812', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Vasant Kunj ES290', 'BLK_DS_ES290', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Delhi Vishnu Garden ES287', 'BLK_DS_4968', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '4968', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'GS Delhi Vasant Kunj GS8', 'BLK_DS_GS_DELHI_VASANT_KUNJ', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Dwarka Sector 12 ES424', 'BLK_DS_8052', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '8052', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi East Patel Nagar ES372', 'BLK_DS_7151', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7151', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Kakrola Village ES89', 'BLK_DS_2693', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '2693', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Kalu Sarai ES371', 'BLK_DS_7133', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7133', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Kamla Nagar ES383', 'BLK_DS_7331', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7331', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Kotla Village ES321', 'BLK_DS_5927', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '5927', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Laxmi Nagar ES374', 'BLK_DS_7192', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7192', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Model Town ES392', 'BLK_DS_7631', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7631', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Palam ES377', 'BLK_DS_7286', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7286', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Phool Bagh ES418', 'BLK_DS_ES418', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Rajouri Garden ES353', 'BLK_DS_6856', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6856', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Rithala ES293', 'BLK_DS_5032', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '5032', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Safdarjung ES398', 'BLK_DS_7682', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7682', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Sainik Farm ES394', 'BLK_DS_7646', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7646', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Sangam Vihar ES406', 'BLK_DS_7789', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7789', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Sant Nagar ES391', 'BLK_DS_7629', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7629', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Sarita Vihar ES368', 'BLK_DS_7041', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7041', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Tilak Nagar ES411', 'BLK_DS_7873', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7873', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Uttam Nagar Phase 1 ES352', 'BLK_DS_6812', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6812', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Vasant Kunj ES290', 'BLK_DS_ES290', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Vasant Kunj ES412', 'BLK_DS_7889', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7889', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Delhi Vishnu Garden ES287', 'BLK_DS_4968', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '4968', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Asaf Ali Road ES252', 'BLK_DS_4614', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '4614', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Burari ES277', 'BLK_DS_4705', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '4705', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Jamia ES284', 'BLK_DS_4963', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '4963', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Kakrola Village ES89', 'BLK_DS_2693', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '2693', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Kalkaji ES362', 'BLK_DS_6948', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6948', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi New Basant Gaon ES210', 'BLK_DS_3514', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '3514', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi New Green Park ES298', 'BLK_DS_ES298', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING; -- !! NEEDS_OUTLET_ID

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Pochanpur ES233', 'BLK_DS_ES233', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Prashant Vihar ES395', 'BLK_DS_7668', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7668', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi SSN Marg ES82', 'BLK_DS_3234', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '3234', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Sainik Farm ES219', 'BLK_DS_ES219', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Shahpurjat ES248', 'BLK_DS_4598', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '4598', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Shakti Vihar ES274', 'BLK_DS_ES274', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Southex ES370', 'BLK_DS_7082', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7082', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Delhi Vasant Kunj D Block ES347', 'BLK_DS_6741', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6741', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'Super Store Delhi Paschim Vihar ES32 PR', 'BLK_DS_ES32_PR', 'Delhi', 'Delhi', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Faridabad Sector 16 ES41', 'BLK_DS_6882', 'Faridabad', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6882', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Faridabad Sec 37 ES50', 'BLK_DS_8108', 'Faridabad', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '8108', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Faridabad Sector 16 ES41', 'BLK_DS_6882', 'Faridabad', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6882', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Faridabad Greenfield ES45', 'BLK_DS_7040', 'Faridabad', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7040', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Faridabad Sector 7 ES48', 'BLK_DS_7481', 'Faridabad', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7481', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Faridabad Sector 88 ES49', 'BLK_DS_7709', 'Faridabad', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7709', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES UP-NCR Gr. Noida Delta 1 ES194', 'BLK_DS_6911', 'Ghaziabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6911', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES UP-NCR Indirapuram ES193', 'BLK_DS_6921', 'Ghaziabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6921', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES UP-NCR Noida Sector 46 ES188', 'BLK_DS_6850', 'Ghaziabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6850', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT UP-NCR Avantika Colony ES220', 'BLK_DS_7725', 'Ghaziabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7725', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT UP-NCR Gr. Noida Delta 1 ES194', 'BLK_DS_6911', 'Ghaziabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6911', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT UP-NCR Noida Sector 46 ES188', 'BLK_DS_6850', 'Ghaziabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6850', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS UP-NCR Avantika Colony ES220', 'BLK_DS_7725', 'Ghaziabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7725', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS UP-NCR Indirapuram ES193', 'BLK_DS_6921', 'Ghaziabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6921', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS UP-NCR Noida Ithera ES191', 'BLK_DS_6871', 'Ghaziabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6871', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS UP-NCR Sector 141 ES217', 'BLK_DS_7567', 'Ghaziabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7567', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Gurgaon DLF Phase 3 ES185', 'BLK_DS_7621', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7621', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Gurgaon Manesar ES188', 'BLK_DS_7705', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7705', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Gurgaon Palam Vihar ES191', 'BLK_DS_7767', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7767', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Gurgaon Sarasvati Vihar ES183', 'BLK_DS_7489', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7489', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Gurgaon Sector 106 ES169', 'BLK_DS_6924', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6924', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Gurgaon Sector 22 ES181', 'BLK_DS_7353', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7353', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Gurgaon Sector 66 ES168', 'BLK_DS_6601', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6601', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Gurgaon Sushant Lok ES190', 'BLK_DS_7746', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7746', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Ardee ES189', 'BLK_DS_7733', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7733', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon DLF Phase 3 ES185', 'BLK_DS_7621', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7621', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Manesar ES188', 'BLK_DS_7705', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7705', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Palam Vihar ES191', 'BLK_DS_7767', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7767', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Sarasvati Vihar ES183', 'BLK_DS_7489', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7489', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Sector 106 ES169', 'BLK_DS_6924', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6924', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Sector 22 ES181', 'BLK_DS_7353', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7353', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Sector 33 ES104', 'BLK_DS_3596', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '3596', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Sector 40 ES194', 'BLK_DS_ES194', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Sector 66 ES168', 'BLK_DS_6601', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6601', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Sector 85 ES155', 'BLK_DS_ES155', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Gurgaon Sushant Lok ES190', 'BLK_DS_7746', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7746', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon New Gwal Pahari ES114', 'BLK_DS_4096', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '4096', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Nirvana Country ES44', 'BLK_DS_2909', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '2909', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sector 12 ES174', 'BLK_DS_7002', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7002', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sector 33 ES104', 'BLK_DS_3596', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '3596', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sector 37 D ES171', 'BLK_DS_6955', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '6955', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sector 48 ES180', 'BLK_DS_7230', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '7230', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sector 49 ES3', 'BLK_DS_2346', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '2346', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sector 5 ES154', 'BLK_DS_5612', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '5612', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sector 54 ES108', 'BLK_DS_3901', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '3901', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sector 56 ES144', 'BLK_DS_5049', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '5049', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sector 77 ES134', 'BLK_DS_4640', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    '4640', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sector 82 ES52', 'BLK_DS_ES52', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Gurgaon Sushant Lok B Block ES152', 'BLK_DS_ES152', 'Gurgaon', 'Haryana', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Haldwani Heera Nagar ES5', 'BLK_DS_ES5', 'Haldwani', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Haldwani Dhanpuri ES4', 'BLK_DS_ES4', 'Haldwani', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Haldwani Heera Nagar ES5', 'BLK_DS_ES5', 'Haldwani', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mathura Goverdhan Crossing ES5', 'BLK_DS_ES5', 'Mathura', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Meerut Suraj Kund ES212', 'BLK_DS_ES212', 'Meerut', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Moradabad Parashuram Chowk ES1', 'BLK_DS_ES1', 'Moradabad', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Panipat Model Town ES1', 'BLK_DS_ES1', 'Panipat', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Panipat Sector 13 ES2', 'BLK_DS_ES2', 'Panipat', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Rampur Elahi Bagh ES4', 'BLK_DS_ES4', 'Rampur', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Rohtak Shastri Nagar ES3', 'BLK_DS_ES3', 'Rohtak', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Rudrapur Jagatpura ES2', 'BLK_DS_ES2', 'Rudrapur', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Sonipat Levan ES57', 'BLK_DS_ES57', 'Sonipat', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Sonipat Sector 12 ES1', 'BLK_DS_ES1', 'Sonipat', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5096'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Domlur ES255', 'BLK_DS_ES255', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru SD Bed Koramangala ES185', 'BLK_DS_ES185', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'ES Bengaluru Sampighehalli ES245', 'BLK_DS_ES245', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'GS Bengaluru SD Bed Koramangala GS4', 'BLK_DS_GS_BENGALURU_SD_BED_', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Devarabisanahalli ES273', 'BLK_DS_7262', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '7262', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Domlur ES255', 'BLK_DS_ES255', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Frazer Town ES318', 'BLK_DS_8109', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '8109', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Sampighehalli ES245', 'BLK_DS_ES245', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Tavarekere SG Palya ES304', 'BLK_DS_7775', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '7775', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Bengaluru Thanisandra Kannuru ES295', 'BLK_DS_7670', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '7670', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Abbigere ES175', 'BLK_DS_5286', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '5286', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Agara Village ES158', 'BLK_DS_ES158', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru BTM Layout 2nd Stage ES233', 'BLK_DS_6307', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '6307', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Bagalur Sathanur ES303', 'BLK_DS_7773', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '7773', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Basavangudi Puttana Rd ES263', 'BLK_DS_7045', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '7045', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Bilekahalli ES218', 'BLK_DS_6049', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '6049', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Brookefield AECS Layout ES202', 'BLK_DS_5673', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '5673', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Cheemasandra ES270', 'BLK_DS_7191', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '7191', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Chikkabidrakallu ES165', 'BLK_DS_5347', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '5347', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru E-City Phase-2 ES47', 'BLK_DS_3142', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '3142', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Hagadur Whitefield ES169', 'BLK_DS_ES169', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Haralur 2 ES193', 'BLK_DS_5485', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '5485', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Jayanagar 4th Block ES271', 'BLK_DS_7161', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '7161', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru KR Puram ES118', 'BLK_DS_ES118', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Kannamangala ES58', 'BLK_DS_3375', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '3375', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Kodigehalli Devinagar ES266', 'BLK_DS_7140', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '7140', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Konanakunte ES259', 'BLK_DS_6932', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '6932', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Koramangala 6th Block ES291', 'BLK_DS_7574', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '7574', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Mailasandra ES117', 'BLK_DS_3117', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '3117', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Marathahalli ES88', 'BLK_DS_3790', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '3790', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Nandini Layout ES250', 'BLK_DS_ES250', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Provident Welworth ES157', 'BLK_DS_5240', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '5240', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Sarjapur Dommasandra ES214', 'BLK_DS_5991', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '5991', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Sarjapur Kodathi ES234', 'BLK_DS_6308', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '6308', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Thanisandra ES90', 'BLK_DS_3788', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '3788', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Vasanth Nagar ES198', 'BLK_DS_5632', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '5632', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Vidyaranyapura ES112', 'BLK_DS_4510', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '4510', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Vijay Nagar ES92', 'BLK_DS_3952', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '3952', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Whitefield Nallurhalli ES122', 'BLK_DS_ES122', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Whitefield Palm Meadows ES293', 'BLK_DS_7619', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '7619', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Bengaluru Yelahanka Anantapura ES307', 'BLK_DS_ES307', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'Super Store Bengaluru Kamakshipalya ES15 PR', 'BLK_DS_1887', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '1887', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'Super Store Bengaluru Manipal County Rd ES20', 'BLK_DS_2151', 'Bengaluru', 'Karnataka', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    '2151', TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Chikkamagaluru Joythinagar ES1', 'BLK_DS_ES1', 'Chikkamagaluru', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Coimbatore Gandhipuram ES11', 'BLK_DS_ES11', 'Coimbatore', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Coimbatore Maskalipalayam ES4', 'BLK_DS_ES4', 'Coimbatore', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Coimbatore Saravanampatti ES5', 'BLK_DS_ES5', 'Coimbatore', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Davanagere MCC B Block ES188', 'BLK_DS_ES188', 'Davanagere', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'LT Kochi Kakkanad ES10', 'BLK_DS_ES10', 'Kochi', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Kochi Edapally ES5', 'BLK_DS_ES5', 'Kochi', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Kochi Kadavanthra ES7', 'BLK_DS_ES7', 'Kochi', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Kochi Pachalam ES3', 'BLK_DS_ES3', 'Kochi', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mangaluru Attavar ES3', 'BLK_DS_ES3', 'Mangalore', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Manipal Vidyaratna Nagar ES1', 'BLK_DS_ES1', 'Manipal', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mysore Ansaar Hospital ES7', 'BLK_DS_ES7', 'Mysore', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Mysore Kuvempunagar ES5', 'BLK_DS_ES5', 'Mysore', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;

INSERT INTO partner_locations
    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)
SELECT 4, 'SS Trivandrum Vazhuthacaud ES7', 'BLK_DS_ES7', 'Trivandrum', '', 'DARKSTORE',
    (SELECT location_id FROM partner_locations WHERE code = 'BLK_WH_5397'),
    NULL, TRUE
ON CONFLICT (code) DO NOTHING;
