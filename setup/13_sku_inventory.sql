-- SKU-level assembled stock (packed hampers ready to ship)
CREATE TABLE IF NOT EXISTS sku_inventory (
  sku_inv_id   SERIAL PRIMARY KEY,
  sku_id       TEXT NOT NULL REFERENCES skus(sku_id),
  channel_id   INT  NOT NULL REFERENCES channels(channel_id),
  qty_on_hand  INT  NOT NULL DEFAULT 0,
  qty_reserved INT  NOT NULL DEFAULT 0,  -- allocated to pending orders, not yet physically moved
  last_updated TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(sku_id, channel_id)
);

-- Audit log for all assembled SKU stock movements
CREATE TABLE IF NOT EXISTS sku_inventory_transactions (
  txn_id          SERIAL PRIMARY KEY,
  txn_date        TIMESTAMPTZ DEFAULT NOW(),
  type            TEXT NOT NULL CHECK (type IN (
                    'ASSEMBLY',      -- items consumed → SKU packed in OWN_WH
                    'DISPATCH',      -- SKU sent to customer (direct order fulfillment)
                    'TRANSFER_OUT',  -- SKU leaving a location (to FBA / darkstore / partner)
                    'TRANSFER_IN',   -- SKU arriving at a location
                    'ADJUSTMENT',    -- manual correction
                    'RETURN'         -- customer return back into WH
                  )),
  sku_id          TEXT NOT NULL REFERENCES skus(sku_id),
  from_channel_id INT REFERENCES channels(channel_id),
  to_channel_id   INT REFERENCES channels(channel_id),
  quantity        INT NOT NULL,
  reference       TEXT,   -- PO#, order#, transfer note
  notes           TEXT,
  created_by      TEXT DEFAULT 'system',
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Link item-level assembly transactions back to the SKU being assembled
ALTER TABLE inventory_transactions ADD COLUMN IF NOT EXISTS sku_id TEXT REFERENCES skus(sku_id);

-- Add ASSEMBLY to item-level transaction types (items consumed during packing)
ALTER TABLE inventory_transactions DROP CONSTRAINT IF EXISTS inventory_transactions_type_check;
ALTER TABLE inventory_transactions ADD CONSTRAINT inventory_transactions_type_check
  CHECK (type IN (
    'RECEIPT',          -- goods received from supplier
    'ASSEMBLY',         -- items consumed to assemble a SKU (sku_id column populated)
    'DISPATCH',         -- direct order fulfillment from loose stock (rare)
    'TRANSFER_OUT',
    'TRANSFER_IN',
    'ADJUSTMENT',
    'RTO',
    'SALE_RETURN',
    'DAMAGE_WRITE_OFF'
  ));
