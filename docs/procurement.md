# Procurement Module — Schema Reference

Covers the procurement data model added by migration
[`setup/migrations/029_procurement.sql`](../setup/migrations/029_procurement.sql)
(issue [#66](https://github.com/hd-stack-1858/tcb-demand-planning/issues/66)).
This is the storage layer; the business-logic layers that read and write it
are built in follow-up issues (#67 L0 pure functions, #68 L1 repo CRUD,
#59 GRN posting, #61 debit notes).

---

## Overview

One migration adds the whole procurement module:

| Piece | Tables |
|---|---|
| Item ↔ supplier terms | `item_suppliers` (+ `suppliers` extension) |
| Goods receipt | `goods_receipts`, `goods_receipt_items` |
| Vendor invoices | `vendor_invoices`, `vendor_invoice_items` |
| PO ↔ invoice join | `po_invoice_allocations` |
| Debit notes | `debit_notes`, `debit_note_items` |
| Advance ledger | `vendor_advances`, `vendor_advance_allocations` |
| PO extension | `purchase_orders` + `purchase_orders.status` |

All monetary values are `NUMERIC` (₹ INR). All tables use `SERIAL` surrogate
PKs named after the entity (`*_id`), matching the existing schema style.

> [!NOTE]
> `vendor_invoices` / `vendor_invoice_items` are **distinct** from the
> existing customer-facing `invoices` / `invoice_items` tables (migration 01).
> "vendor invoice" = money we owe a supplier; "invoice" = money a customer
> channel owes us. Do not cross-reference them.

---

## 1. `suppliers` — advance terms extension

```sql
ADD COLUMN advance_type  TEXT DEFAULT 'none' CHECK (advance_type IN ('none','percent','fixed')),
ADD COLUMN advance_value NUMERIC(10,2);
```

- `advance_type` controls how an advance is computed for this supplier:
  `none` / `percent` (of PO value) / `fixed` (absolute amount).
- `advance_value` is the percent (0–100) or fixed ₹ amount; ignored when
  `advance_type = 'none'`.
- `payment_terms` already existed on `suppliers` — this migration does not
  touch it.
- Range validation (0–100%, non-negative fixed, none ⇒ no value) is **not** a
  DB CHECK — it belongs in `tcb/procurement.py` (L0, #67).

## 2. `item_suppliers` — per-pair terms

Item ↔ supplier mapping with per-pair commercial terms:

| Column | Type | Notes |
|---|---|---|
| `item_supplier_id` | SERIAL PK | |
| `item_id` | INT FK → `items` | NOT NULL |
| `supplier_id` | INT FK → `suppliers` | NOT NULL |
| `cogs` | NUMERIC(10,4) | Per-pair cost override |
| `lead_time_days` | INT | Per-pair lead time override |
| `moq` | INT | Per-pair minimum order quantity |
| `is_preferred` | BOOLEAN | Default `FALSE` |
| `is_active` | BOOLEAN | Default `TRUE` |
| `created_at` | TIMESTAMPTZ | Default `NOW()` |

Constraints:

- `UNIQUE(item_id, supplier_id)` — one row per pair.
- Partial unique index `item_suppliers_one_preferred_idx ON (item_id) WHERE is_preferred`
  — **at most one preferred supplier per item**, enforced at the DB level.
- `is_preferred` is a convenience flag, not a constraint on use; the
  `effective_terms` resolution logic in #67 decides which pair actually serves
  an item (item↔supplier override → supplier default).

The existing `items.latest_supplier_id` single FK is left as-is — it stays a
convenience pointer, not a source of truth.

## 3. `goods_receipts` / `goods_receipt_items` — GRN

Header:

| Column | Type | Notes |
|---|---|---|
| `grn_id` | SERIAL PK | |
| `grn_number` | TEXT UNIQUE | |
| `po_id` | INT FK → `purchase_orders` | NOT NULL |
| `received_date` | DATE | Default `CURRENT_DATE` |
| `received_by` | TEXT | Default `'system'` — audit column, mirrors `inventory_transactions.received_by` |
| `status` | TEXT | CHECK: `DRAFT` / `POSTED` / `CANCELLED` |
| `notes` | TEXT | |
| `created_at` | TIMESTAMPTZ | Default `NOW()` |

Lines (`goods_receipt_items`):

| Column | Type | Notes |
|---|---|---|
| `grn_item_id` | SERIAL PK | |
| `grn_id` | INT FK → `goods_receipts` | NOT NULL |
| `poi_id` | INT FK → `purchase_order_items` | Nullable — links GRN line to PO line |
| `item_id` | INT FK → `items` | NOT NULL |
| `quantity_received` | INT | NOT NULL |
| `cost_per_unit` | NUMERIC(10,4) | |
| `line_total` | NUMERIC(10,2) | |
| `reject_qty` | INT | Default `0` |
| `notes` | TEXT | |

Indexed on `grn_id` and `poi_id`. `reject_qty` > 0 at POST time is what
drives debit-note creation later (#61).

## 4. `vendor_invoices` / `vendor_invoice_items`

Header:

| Column | Type | Notes |
|---|---|---|
| `invoice_id` | SERIAL PK | |
| `invoice_number` | TEXT UNIQUE | |
| `supplier_id` | INT FK → `suppliers` | NOT NULL |
| `invoice_date` | DATE | Default `CURRENT_DATE` |
| `due_date` | DATE | |
| `total_value` | NUMERIC(10,2) | |
| `tax_amount` | NUMERIC(10,2) | |
| `status` | TEXT | CHECK: `DRAFT` / `POSTED` / `PAID` / `PARTIALLY_PAID` / `CANCELLED` |
| `notes` | TEXT | |
| `created_at` | TIMESTAMPTZ | Default `NOW()` |

Lines (`vendor_invoice_items`):

| Column | Type | Notes |
|---|---|---|
| `inv_item_id` | SERIAL PK | |
| `invoice_id` | INT FK → `vendor_invoices` | NOT NULL |
| `item_id` | INT FK → `items` | NOT NULL |
| `quantity` | INT | NOT NULL |
| `cost_per_unit` | NUMERIC(10,4) | |
| `line_total` | NUMERIC(10,2) | |
| `gst_pct` | NUMERIC(5,2) | |
| `gst_amt` | NUMERIC(10,2) | |

Indexed on `invoice_id`.

## 5. `po_invoice_allocations`

How much of a PO is covered by a given vendor invoice.

| Column | Type | Notes |
|---|---|---|
| `allocation_id` | SERIAL PK | |
| `po_id` | INT FK → `purchase_orders` | NOT NULL |
| `invoice_id` | INT FK → `vendor_invoices` | NOT NULL |
| `amount` | NUMERIC(10,2) | NOT NULL |
| `created_at` | TIMESTAMPTZ | Default `NOW()` |

`UNIQUE(po_id, invoice_id)` — a PO appears at most once per vendor invoice,
so allocation amounts can never be ambiguous. Indexed on `invoice_id`.

## 6. `debit_notes` / `debit_note_items`

Claims against a supplier for short-ship or quality rejections.

Header:

| Column | Type | Notes |
|---|---|---|
| `debit_note_id` | SERIAL PK | |
| `debit_note_number` | TEXT UNIQUE | |
| `supplier_id` | INT FK → `suppliers` | NOT NULL |
| `po_id` | INT FK → `purchase_orders` | Nullable |
| `invoice_id` | INT FK → `vendor_invoices` | Nullable |
| `grn_id` | INT FK → `goods_receipts` | Nullable — most debit notes arise from GRN rejections |
| `debit_date` | DATE | Default `CURRENT_DATE` |
| `reason` | TEXT | |
| `status` | TEXT | CHECK: `DRAFT` / `POSTED` / `CANCELLED` |
| `total_value` | NUMERIC(10,2) | |
| `created_at` | TIMESTAMPTZ | Default `NOW()` |

Lines (`debit_note_items`): `dn_item_id` PK, `debit_note_id` FK,
`item_id` FK, `quantity`, `cost_per_unit`, `line_total`, `reason`.

At least one of `po_id` / `invoice_id` / `grn_id` should normally be set;
the schema does not enforce it — the L2 creation logic (#61) should.

## 7. `vendor_advances` / `vendor_advance_allocations`

Advance ledger — schema only in this migration.

`vendor_advances`:

| Column | Type | Notes |
|---|---|---|
| `advance_id` | SERIAL PK | |
| `supplier_id` | INT FK → `suppliers` | NOT NULL |
| `advance_date` | DATE | Default `CURRENT_DATE` |
| `amount` | NUMERIC(10,2) | NOT NULL |
| `method` | TEXT | e.g. UPI / bank transfer |
| `reference` | TEXT | Payment reference |
| `status` | TEXT | CHECK: `OPEN` / `ALLOCATED` / `CLOSED` / `CANCELLED` |
| `notes` | TEXT | |
| `created_at` | TIMESTAMPTZ | Default `NOW()` |

`vendor_advance_allocations`:

| Column | Type | Notes |
|---|---|---|
| `allocation_id` | SERIAL PK | |
| `advance_id` | INT FK → `vendor_advances` | NOT NULL |
| `po_id` | INT FK → `purchase_orders` | NOT NULL |
| `grn_id` | INT FK → `goods_receipts` | Nullable |
| `amount` | NUMERIC(10,2) | NOT NULL |
| `allocated_date` | DATE | Default `CURRENT_DATE` |
| `created_at` | TIMESTAMPTZ | Default `NOW()` |

> [!IMPORTANT]
> This migration creates the **schema only**. Pro-rata advance clearing at GRN
> is deliberately not built — it is gated on #89 (vendor-advance accounting,
> needs Chartered-Accountant input) and belongs to a later epic (#59/#61).
> `advance_due()` — how much to pay up front — is safe to build in #67.

## 8. `purchase_orders` extension

```sql
ADD COLUMN terminal_date DATE,
ADD COLUMN advance_type  TEXT,
ADD COLUMN advance_value NUMERIC(10,2),
ADD COLUMN payment_terms TEXT;
```

- `terminal_date` pairs with the new `CLOSED` status: a PO where remaining
  quantity is intentionally abandoned, distinct from fully `RECEIVED`.
- `advance_type` / `advance_value` / `payment_terms` are a **contract-terms
  snapshot** frozen at PO creation. If the supplier's terms change later,
  existing POs are unaffected — that is the point of snapshotting them.

### Status enum

```sql
CHECK (status IN ('DRAFT','SENT','CONFIRMED','PARTIAL','RECEIVED','CANCELLED','CLOSED'))
```

- `CLOSED` added as the terminal state for abandoned POs.
- `PARTIAL` means **partial receipt** (not partial send).
- The migration resolves and drops the pre-existing status CHECK by name from
  `pg_constraint` (not assuming Postgres's auto-name) before re-adding.

> [!IMPORTANT]
> `advance_paid` / `balance_due` on `purchase_orders` are **deliberately left
> untouched** (PV decision 2026-08-01). `mcp/server.py` still reads/writes them
> (`get_po_status`, `create_purchase_order`, `receive_po`) — dropping them would
> break those tools. They stay until the `vendor_advances` ledger is live and
> proven, then get deprecated in a later migration.

---

## Conventions & decisions

- **Validation lives in L0, not DB CHECKs.** MOQ > 0, lead_time > 0,
  advance 0–100% are business rules enforced in `tcb/procurement.py` (#67),
  where they can return meaningful errors and be tested without a DB. DB
  CHECKs here cover structural integrity only (enums, FKs, uniqueness).
- **`received_by` audit pattern** mirrors `inventory_transactions` — set at
  GRN POST time by the posting logic (#59).
- **One preferred supplier per item** is a DB-enforced invariant.
- **Renumbering:** originally planned as 028, renamed to **029** because
  `028_feature_flags.sql` already exists on dev.

## Tests

`tests/test_procurement_schema.py` (integration tier, `pytest -m integration`)
asserts the tables exist, column types are correct, constraints hold, and the
behavioral invariants actually bite (duplicate preferred supplier rejected,
duplicate pair rejected, invalid `advance_type` rejected, `CLOSED` accepted /
`BOGUS` rejected, `advance_paid` / `balance_due` still writable). 38 tests pass
against a real Postgres 16.

Run:

```bash
python -m pytest tests/test_procurement_schema.py -q
```

Requires a DB URL via `TCB_TEST_DB_URL` or `DEV_DB_URL` in `.env.dev`; skips
cleanly when neither is configured.

## Deploying

1. Apply `setup/migrations/029_procurement.sql` to the **dev** Supabase
   instance, then run `./scripts/run_tests.sh integration` to confirm the
   migration works against dev. Only then merge the PR.
2. **Prod apply is human-only** (#69) — never run procurement DDL against prod
   from an agent.
