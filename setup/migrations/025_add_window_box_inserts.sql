-- Add "Window Box Small - Insert" and "Window Box Medium - Insert" packaging items.
-- Toys (bunny/rattle) inside the window box were shaking loose in transit, damaging
-- presentation on delivery. Insert holds the toy in place. Wired into BOM for the
-- same SKUs the corresponding Window Box already serves.
-- Stock starts at 0 — Himanshu will inward the first batch separately.

INSERT INTO items (item_code, name, item_type, unit, latest_supplier_id, reorder_point, safety_stock, lead_time_days, moq, is_active)
VALUES
    ('TCBP00043', 'Window Box Small - Insert',  'PACKAGING', 'piece', 28, 52, 0, 15, 250, TRUE),
    ('TCBP00044', 'Window Box Medium - Insert', 'PACKAGING', 'piece', 28, 32, 0, 15, 500, TRUE);

INSERT INTO bom (sku_id, item_id, quantity_per_sku)
SELECT t.sku_id,
       (SELECT item_id FROM items WHERE item_code = t.item_code),
       t.qty
FROM (VALUES
    ('TCB008', 'TCBP00043', 1::numeric(10,3)),
    ('TCB012', 'TCBP00043', 1::numeric(10,3)),
    ('TCB011', 'TCBP00044', 1::numeric(10,3))
) AS t(sku_id, item_code, qty);
