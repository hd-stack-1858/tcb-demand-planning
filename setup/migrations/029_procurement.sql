-- ============================================================================
-- Migration 029 — Procurement schema
--
-- Covers the whole procurement module in one migration:
--   * item_suppliers            — item<->supplier mapping with per-pair terms
--   * suppliers extension       — advance terms (advance_type / advance_value)
--   * goods_receipts/_items     — GRN header/lines, linked to PO
--   * vendor_invoices/_items    — vendor invoice capture
--   * po_invoice_allocations    — PO <-> vendor invoice join
--   * debit_notes/_items        — short/reject claims
--   * vendor_advances/_alloc    — advance ledger and allocations
--   * purchase_orders extension — terminal_date + contract-terms snapshot
--
-- Notes:
--   * advance_paid / balance_due on purchase_orders are intentionally LEFT
--     UNTOUCHED (PV 2026-08-01): they stay until the vendor_advances ledger is
--     live and proven, then get deprecated in a later migration.
--   * No advance-clearing logic here — pro-rata clearing at GRN is gated on
--     #89 (CA input) and belongs to a later epic (#59/#61).
--   * Business validation (MOQ > 0, lead_time > 0, advance 0-100%) belongs in
--     tcb/procurement.py (L0, #67), not DB CHECKs.
--   * Transactional + idempotent (PV/Archie 2026-08-01): wrapped in BEGIN/COMMIT
--     so a partial failure rolls back cleanly, and every ALTER uses IF NOT
--     EXISTS so a re-run is safe. Prologue restores the PO skeleton below.
--
-- Renamed 028 -> 029 (2026-08-01): 028_feature_flags.sql already exists on dev.
-- ============================================================================

BEGIN;

-- 0. purchase_orders / purchase_order_items — restore skeleton ---------------
-- Both were empty Phase F skeletons dropped during the DB cleanup; 029 and its
-- FKs reference them. Recreated verbatim from 01_create_tables.sql, plus the
-- updated_at columns from 08_add_updated_at.sql. IF NOT EXISTS keeps this safe
-- if a DB already has either table.
CREATE TABLE IF NOT EXISTS purchase_orders (
  po_id           SERIAL PRIMARY KEY,
  po_number       TEXT UNIQUE,
  supplier_id     INT NOT NULL REFERENCES suppliers(supplier_id),
  created_date    DATE DEFAULT CURRENT_DATE,
  expected_date   DATE,
  received_date   DATE,
  status          TEXT DEFAULT 'DRAFT' CHECK (status IN (
                    'DRAFT','SENT','CONFIRMED','PARTIAL','RECEIVED','CANCELLED'
                  )),
  total_value     NUMERIC(10,2),
  advance_paid    NUMERIC(10,2),
  balance_due     NUMERIC(10,2),
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
  poi_id              SERIAL PRIMARY KEY,
  po_id               INT NOT NULL REFERENCES purchase_orders(po_id),
  item_id             INT NOT NULL REFERENCES items(item_id),
  quantity_ordered    INT NOT NULL,
  cost_per_unit       NUMERIC(10,4),
  line_total          NUMERIC(10,2),
  quantity_received   INT DEFAULT 0,
  batch_code_received TEXT,
  notes               TEXT,
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 1. suppliers — advance terms ------------------------------------------------
ALTER TABLE suppliers
  ADD COLUMN IF NOT EXISTS advance_type  TEXT DEFAULT 'none' CHECK (advance_type IN ('none','percent','fixed')),
  ADD COLUMN IF NOT EXISTS advance_value NUMERIC(10,2);

-- 2. item_suppliers -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS item_suppliers (
  item_supplier_id SERIAL PRIMARY KEY,
  item_id          INT NOT NULL REFERENCES items(item_id),
  supplier_id      INT NOT NULL REFERENCES suppliers(supplier_id),
  cogs             NUMERIC(10,4),
  lead_time_days   INT,
  moq              INT,
  is_preferred     BOOLEAN DEFAULT FALSE,
  is_active        BOOLEAN DEFAULT TRUE,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(item_id, supplier_id)
);

-- At most one preferred supplier per item.
CREATE UNIQUE INDEX IF NOT EXISTS item_suppliers_one_preferred_idx
  ON item_suppliers(item_id) WHERE is_preferred;
CREATE INDEX IF NOT EXISTS item_suppliers_supplier_id_idx ON item_suppliers(supplier_id);

-- 3. goods_receipts -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS goods_receipts (
  grn_id        SERIAL PRIMARY KEY,
  grn_number    TEXT UNIQUE,
  po_id         INT NOT NULL REFERENCES purchase_orders(po_id),
  received_date DATE DEFAULT CURRENT_DATE,
  received_by   TEXT DEFAULT 'system',
  status        TEXT DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','POSTED','CANCELLED')),
  notes         TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS goods_receipts_po_id_idx ON goods_receipts(po_id);

-- 4. goods_receipt_items ------------------------------------------------------
CREATE TABLE IF NOT EXISTS goods_receipt_items (
  grn_item_id       SERIAL PRIMARY KEY,
  grn_id            INT NOT NULL REFERENCES goods_receipts(grn_id),
  poi_id            INT REFERENCES purchase_order_items(poi_id),
  item_id           INT NOT NULL REFERENCES items(item_id),
  quantity_received INT NOT NULL,
  cost_per_unit     NUMERIC(10,4),
  line_total        NUMERIC(10,2),
  reject_qty        INT DEFAULT 0,
  notes             TEXT
);
CREATE INDEX IF NOT EXISTS goods_receipt_items_grn_id_idx ON goods_receipt_items(grn_id);
CREATE INDEX IF NOT EXISTS goods_receipt_items_poi_id_idx ON goods_receipt_items(poi_id);

-- 5. vendor_invoices ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_invoices (
  invoice_id     SERIAL PRIMARY KEY,
  invoice_number TEXT UNIQUE,
  supplier_id    INT NOT NULL REFERENCES suppliers(supplier_id),
  invoice_date   DATE DEFAULT CURRENT_DATE,
  due_date       DATE,
  total_value    NUMERIC(10,2),
  tax_amount     NUMERIC(10,2),
  status         TEXT DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','POSTED','PAID','PARTIALLY_PAID','CANCELLED')),
  notes          TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS vendor_invoices_supplier_id_idx ON vendor_invoices(supplier_id);

-- 6. vendor_invoice_items -----------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_invoice_items (
  inv_item_id   SERIAL PRIMARY KEY,
  invoice_id    INT NOT NULL REFERENCES vendor_invoices(invoice_id),
  item_id       INT NOT NULL REFERENCES items(item_id),
  quantity      INT NOT NULL,
  cost_per_unit NUMERIC(10,4),
  line_total    NUMERIC(10,2),
  gst_pct       NUMERIC(5,2),
  gst_amt       NUMERIC(10,2)
);
CREATE INDEX IF NOT EXISTS vendor_invoice_items_invoice_id_idx ON vendor_invoice_items(invoice_id);

-- 7. po_invoice_allocations ---------------------------------------------------
CREATE TABLE IF NOT EXISTS po_invoice_allocations (
  allocation_id SERIAL PRIMARY KEY,
  po_id         INT NOT NULL REFERENCES purchase_orders(po_id),
  invoice_id    INT NOT NULL REFERENCES vendor_invoices(invoice_id),
  amount        NUMERIC(10,2) NOT NULL,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(po_id, invoice_id)
);
CREATE INDEX IF NOT EXISTS po_invoice_allocations_invoice_id_idx ON po_invoice_allocations(invoice_id);

-- 8. debit_notes --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS debit_notes (
  debit_note_id     SERIAL PRIMARY KEY,
  debit_note_number TEXT UNIQUE,
  supplier_id       INT NOT NULL REFERENCES suppliers(supplier_id),
  po_id             INT REFERENCES purchase_orders(po_id),
  invoice_id        INT REFERENCES vendor_invoices(invoice_id),
  grn_id            INT REFERENCES goods_receipts(grn_id),
  debit_date        DATE DEFAULT CURRENT_DATE,
  reason            TEXT,
  status            TEXT DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','POSTED','CANCELLED')),
  total_value       NUMERIC(10,2),
  created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS debit_notes_supplier_id_idx ON debit_notes(supplier_id);

-- 9. debit_note_items ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS debit_note_items (
  dn_item_id    SERIAL PRIMARY KEY,
  debit_note_id INT NOT NULL REFERENCES debit_notes(debit_note_id),
  item_id       INT NOT NULL REFERENCES items(item_id),
  quantity      INT NOT NULL,
  cost_per_unit NUMERIC(10,4),
  line_total    NUMERIC(10,2),
  reason        TEXT
);
CREATE INDEX IF NOT EXISTS debit_note_items_debit_note_id_idx ON debit_note_items(debit_note_id);

-- 10. vendor_advances ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_advances (
  advance_id   SERIAL PRIMARY KEY,
  supplier_id  INT NOT NULL REFERENCES suppliers(supplier_id),
  advance_date DATE DEFAULT CURRENT_DATE,
  amount       NUMERIC(10,2) NOT NULL,
  method       TEXT,
  reference    TEXT,
  status       TEXT DEFAULT 'OPEN' CHECK (status IN ('OPEN','ALLOCATED','CLOSED','CANCELLED')),
  notes        TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS vendor_advances_supplier_id_idx ON vendor_advances(supplier_id);

-- 11. vendor_advance_allocations ----------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_advance_allocations (
  allocation_id  SERIAL PRIMARY KEY,
  advance_id     INT NOT NULL REFERENCES vendor_advances(advance_id),
  po_id          INT NOT NULL REFERENCES purchase_orders(po_id),
  grn_id         INT REFERENCES goods_receipts(grn_id),
  amount         NUMERIC(10,2) NOT NULL,
  allocated_date DATE DEFAULT CURRENT_DATE,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS vendor_advance_allocations_advance_id_idx ON vendor_advance_allocations(advance_id);
CREATE INDEX IF NOT EXISTS vendor_advance_allocations_po_id_idx ON vendor_advance_allocations(po_id);

-- 12. purchase_orders — extension ---------------------------------------------
-- advance_paid / balance_due deliberately left as-is (see header note).
ALTER TABLE purchase_orders
  ADD COLUMN IF NOT EXISTS terminal_date DATE,
  ADD COLUMN IF NOT EXISTS advance_type  TEXT,
  ADD COLUMN IF NOT EXISTS advance_value NUMERIC(10,2),
  ADD COLUMN IF NOT EXISTS payment_terms TEXT;

-- 13. purchase_orders.status — add CLOSED terminal state ----------------------
-- Drop any existing CHECK on the status column by name lookup (Postgres
-- auto-names an inline column CHECK `purchase_orders_status_check`, but resolve
-- it from pg_constraint rather than assuming) and re-add with CLOSED included.
DO $$
DECLARE _con text;
BEGIN
  SELECT c.conname INTO _con
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
   WHERE c.conrelid = 'purchase_orders'::regclass
     AND c.contype = 'c'
     AND a.attname = 'status'
   LIMIT 1;
  IF _con IS NOT NULL THEN
    EXECUTE format('ALTER TABLE purchase_orders DROP CONSTRAINT %I', _con);
  END IF;
END $$;

ALTER TABLE purchase_orders ADD CONSTRAINT purchase_orders_status_check
  CHECK (status IN ('DRAFT','SENT','CONFIRMED','PARTIAL','RECEIVED','CANCELLED','CLOSED'));

COMMIT;
