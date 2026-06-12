-- Add "Ribbon (20 cms)" as a new packaging item and wire it into BOM
-- for TCB001/002 (2 per SKU = 40cm to tie washcloth)
-- and TCB003/TCB004 (3 per SKU = 60cm to tie swaddle)
-- Stock starts at 0 — Himanshu will inward current batch separately

INSERT INTO items (item_code, name, item_type, unit, is_active)
VALUES ('TCBP00042', 'Ribbon (20 cms)', 'PACKAGING', 'piece', TRUE);

INSERT INTO bom (sku_id, item_id, quantity_per_sku)
SELECT t.sku_id,
       (SELECT item_id FROM items WHERE item_code = 'TCBP00042'),
       t.qty
FROM (VALUES
    ('TCB001', 2::numeric(10,3)),
    ('TCB002', 2::numeric(10,3)),
    ('TCB003', 3::numeric(10,3)),
    ('TCB004', 3::numeric(10,3))
) AS t(sku_id, qty);
