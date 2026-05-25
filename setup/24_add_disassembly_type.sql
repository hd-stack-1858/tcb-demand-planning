-- Migration 24: Add DISASSEMBLY as a valid transaction type
-- Needed for disassembling assembled SKUs back into component items.
-- Applied to: sku_inventory_transactions, inventory_transactions

-- sku_inventory_transactions
ALTER TABLE sku_inventory_transactions DROP CONSTRAINT IF EXISTS sku_inventory_transactions_type_check;
ALTER TABLE sku_inventory_transactions ADD CONSTRAINT sku_inventory_transactions_type_check
  CHECK (type IN (
    'ASSEMBLY',       -- items consumed -> SKU packed in OWN_WH
    'DISPATCH',       -- SKU sent to customer (direct order fulfillment)
    'TRANSFER_OUT',   -- SKU leaving a location (to FBA / darkstore / partner)
    'TRANSFER_IN',    -- SKU arriving at a location
    'ADJUSTMENT',     -- manual correction
    'RETURN',         -- customer return back into WH
    'DISASSEMBLY'     -- assembled SKU broken back into component items
  ));

-- inventory_transactions
ALTER TABLE inventory_transactions DROP CONSTRAINT IF EXISTS inventory_transactions_type_check;
ALTER TABLE inventory_transactions ADD CONSTRAINT inventory_transactions_type_check
  CHECK (type IN (
    'RECEIPT',          -- goods received from supplier
    'ASSEMBLY',         -- items consumed to assemble a SKU (sku_id column populated)
    'DISASSEMBLY',      -- items returned to stock when a SKU is broken down
    'DISPATCH',         -- direct order fulfillment from loose stock (rare)
    'TRANSFER_OUT',
    'TRANSFER_IN',
    'ADJUSTMENT',
    'RTO',
    'SALE_RETURN',
    'DAMAGE_WRITE_OFF'
  ));
