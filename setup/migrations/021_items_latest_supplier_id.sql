-- Rename items.supplier_id → latest_supplier_id
-- Semantics: this is a display-only snapshot of the most recent supplier used
-- for this item. The authoritative multi-supplier relationship lives in
-- item_batches.supplier_id. receive_item() keeps this column in sync on every receipt.

ALTER TABLE items RENAME COLUMN supplier_id TO latest_supplier_id;
