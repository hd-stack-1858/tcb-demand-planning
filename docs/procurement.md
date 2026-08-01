# Procurement Module — Schema Reference

The schema is defined in
[`setup/migrations/029_procurement.sql`](../setup/migrations/029_procurement.sql)
(issue [#66](https://github.com/hd-stack-1858/tcb-demand-planning/issues/66)).
That file is the source of truth for columns and constraints — this doc covers
the non-obvious decisions and cross-table invariants the SQL does not explain.

Companion docs: [`procurement_workflow.md`](procurement_workflow.md) (how the
module is used, for operator review) and
[`procurement_design.md`](procurement_design.md) (why the schema is shaped the
way it is).

---

## Key decisions & invariants

- **`vendor_invoices` / `vendor_invoice_items` are distinct from the existing
  customer-facing `invoices` / `invoice_items` tables (migration 01).** "vendor
  invoice" = money we owe a supplier; "invoice" = money a customer channel owes
  us. Do not cross-reference them.
- **Validation lives in L0, not DB CHECKs.** MOQ > 0, lead_time > 0,
  advance 0–100% are business rules enforced in `tcb/procurement.py` (#67),
  where they can return meaningful errors and be tested without a DB. DB
  CHECKs here cover structural integrity only (enums, FKs, uniqueness).
- **One preferred supplier per item** is a DB-enforced invariant (partial
  unique index on `item_suppliers(item_id) WHERE is_preferred`).
- **PO contract terms are a snapshot.** `purchase_orders.advance_type` /
  `advance_value` / `payment_terms` are frozen at PO creation; later supplier
  changes don't affect existing POs.
- **`CLOSED` is a terminal PO state** for abandoned POs, distinct from fully
  `RECEIVED`; pairs with `terminal_date`.
- **`received_by` audit column** on `goods_receipts` mirrors the
  `inventory_transactions` pattern, set at GRN POST time by the posting logic
  (#59).
- **`advance_paid` / `balance_due` on `purchase_orders` are deliberately left
  untouched** (PV decision 2026-08-01). `mcp/server.py` still reads/writes them
  (`get_po_status`, `create_purchase_order`, `receive_po`) — dropping them would
  break those tools. They stay until the `vendor_advances` ledger is live and
  proven, then get deprecated in a later migration.
- **Advance ledger is schema only.** `vendor_advances` / `vendor_advance_allocations`
  get their tables now but pro-rata clearing at GRN is gated on #89
  (vendor-advance accounting) and belongs to a later epic (#59/#61).
  `advance_due()` — how much to pay up front — is safe to build in #67.
- **Renumbered 028 → 029** because `028_feature_flags.sql` already exists on dev.

---

## Tests

`tests/test_procurement_schema.py` (integration tier, `pytest -m integration`)
asserts the tables exist, column types are correct, constraints hold, and the
behavioral invariants actually bite (duplicate preferred supplier rejected,
duplicate pair rejected, invalid `advance_type` rejected, `CLOSED` accepted /
`BOGUS` rejected, `advance_paid` / `balance_due` still writable). 38 tests pass
against a real Postgres 16.

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
3. **Safety properties** (2026-08-01): migration 029 is wrapped in
   `BEGIN`/`COMMIT` so a partial failure rolls back cleanly, every `ALTER` uses
   `ADD COLUMN IF NOT EXISTS` so re-running is safe, and its prologue recreates
   the `purchase_orders` / `purchase_order_items` skeleton (empty Phase F tables
   dropped in the DB cleanup) so the FKs resolve against a fresh dev DB. The
   prologue defines the `purchase_orders.status` CHECK in its final form
   (`CLOSED` included); section 13 upgrades a pre-existing table's CHECK only
   when it lacks `CLOSED`, so the migration never creates, drops, and recreates
   the same constraint.
   `setup/sync_dev_with_prod.py` no longer drops those two tables in its
   stale-table sweep.
