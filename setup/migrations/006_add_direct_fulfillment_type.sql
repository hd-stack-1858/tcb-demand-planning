-- Add DIRECT to fulfillment_type check constraint (for D2C / Own Website orders)
ALTER TABLE orders DROP CONSTRAINT orders_fulfillment_type_check;
ALTER TABLE orders ADD CONSTRAINT orders_fulfillment_type_check
  CHECK (fulfillment_type IN ('DROP_SHIP', 'OUTRIGHT', 'SOR', 'DIRECT'));
