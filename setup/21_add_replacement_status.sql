-- Add REPLACEMENT to orders.status allowed values.
-- Replacement orders: Amazon ships a free unit to the customer;
-- TPC = 0 in a single Order Payment row (no Refund row exists).
-- Original order stays FULFILLED. The replacement order is tagged REPLACEMENT.

ALTER TABLE orders DROP CONSTRAINT orders_status_check;

ALTER TABLE orders ADD CONSTRAINT orders_status_check
  CHECK (status IN ('PENDING','FULFILLED','CANCELLED','RTO','SALE_RETURN','REPLACEMENT'));
