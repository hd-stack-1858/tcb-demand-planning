# Procurement Design Doc — why the schema is shaped the way it is

Records the decisions behind the procurement schema added by migration 029
(issue [#66](https://github.com/hd-stack-1858/tcb-demand-planning/issues/66)).
This is the document future tasks should cite when they need to know *why* a
table or column exists — the schema reference ([`procurement.md`](procurement.md))
answers *what* it is, and the workflow guide
([`procurement_workflow.md`](procurement_workflow.md)) answers *how* it's used.

---

## Context: where the design comes from

The procurement module is a **reimplementation of ERPNext's domain model**, not
a copy of its code. The ERPNext procurement spike
(`landscape_tech_study/erpnext_procurement_spike.md`, v4, 1 Aug 2026) settled
the question:

- **Fork ERPNext / repoint it at our DB** — not viable (Frappe's DocType layer
  *generates* the schema; you fight the framework).
- **Lift ERPNext's procurement code into `tcb-demand-planning`** — not
  practical (700-line `PurchaseReceipt(BuyingController)` classes, `frappe.db`
  calls and ORM domain rules threaded through; extraction pulls the framework
  in behind it).
- **Reuse the domain model** — yes. ERPNext's state machine (Material Request →
  Supplier Quotation → PO → Purchase Receipt → Purchase Invoice → Debit Note,
  plus advance allocation and billing-status lifecycle) is battle-tested. The
  design is freely studiable and amounts to roughly 6 tables plus a status
  lifecycle. **Option B was selected** — build in-house, ERPNext's design as
  reference only.

Requirement source: `ims_oms_v0.3_workflow_design.md` §2 (inward flow,
PI → GRN) and §5 (vendor advance payments).

---

## Design points inherited from v0.3

### GRN is the inventory-valuation event

> GRN, not PO issuance or invoice receipt, is the moment inventory value
> actually changes on the books (except where an advance was paid).

Consequence: the schema models GRN as a first-class document (header + lines
linking back to PO lines), with `quantity_received` and `reject_qty` at line
level. The PO tracks pending quantity; a GRN reduces it proportionally on
partial receipt.

### Vendor advance is an asset, not an expense

> Advance payment is not an expense. It creates a new asset — "Advance to
> Vendor" — a claim against the vendor for future goods.

Consequence: `vendor_advances` is a ledger (supplier, date, amount, method,
reference, status), separate from the PO. **Deliberately not** denormalized
onto `purchase_orders` as a running paid/balance figure.

### Advance terms are contract-aware, not PO-aware

> Advance terms (percentage, fixed sum, or none) must be stored per vendor and
> applied automatically when a PO is raised for that vendor.

Consequence: `suppliers` gets `advance_type` / `advance_value`; `item_suppliers`
gets the per-pair overrides. A PO created for a vendor computes its up-front
payment from those terms — no manual re-entry.

### PO↔invoice is many-to-many

> One invoice can cover several POs (bundled billing), and one PO can be split
> across several invoices (partial/staged delivery).

Consequence: a join table (`po_invoice_allocations`) with `UNIQUE(po_id,
invoice_id)` so a given PO↔invoice pair can only allocate once — amounts can
never become ambiguous.

### Debit notes arise from GRN rejections

Consequence: `debit_notes` links to the source document — `po_id`, `invoice_id`,
and crucially `grn_id` (most debit notes are born from short-ship/quality
reject at receiving).

---

## Decisions made in review (2026-08-01)

These supersede earlier thread statements where they conflict.

| # | Decision | Rationale |
|---|---|---|
| A | `goods_receipts.received_by TEXT DEFAULT 'system'` | Mirrors the `inventory_transactions` audit pattern; who received is tracked for the GRN posting logic (L2, #59). |
| B | `debit_notes.grn_id` nullable FK → `goods_receipts` | Short-ship/reject claims most commonly originate at receiving; the link is as important as PO/invoice links. |
| C | `po_invoice_allocations UNIQUE(po_id, invoice_id)` | One PO appears at most once per vendor invoice; prevents ambiguous allocation amounts on the many-to-many join. |
| D | PO contract-terms snapshot includes `payment_terms` (plus `advance_type`, `advance_value`) | Freeze all three contract terms at PO creation. If a supplier's terms change later, existing POs don't retroactively change. |

### `advance_paid` / `balance_due` on `purchase_orders` — kept, for now

The original plan was to drop these in 029 in favor of the `vendor_advances`
ledger. **PV decision: keep them.** They've never been populated, but
`mcp/server.py` still reads/writes them (`get_po_status`,
`create_purchase_order`, `receive_po`) — dropping them would break those tools.
They stay until the advance ledger is live and proven, then get deprecated in a
later migration. 029 leaves them untouched and notes this explicitly in the
migration header.

### `CLOSED` added to the PO status enum

`purchase_orders.status` gained `CLOSED` as a terminal state for POs where the
remaining quantity is intentionally abandoned — distinct from fully `RECEIVED`,
and paired with the new `terminal_date` column. `PARTIAL` is re-documented to
mean **partial receipt** (not partial send). The enum change landed in the same
migration rather than a second ALTER later.

### Validation lives in L0, not DB CHECKs

Business rules — MOQ > 0, lead_time > 0, advance percent 0–100% — are **not**
DB CHECKs. They belong in `tcb/procurement.py` (L0, #67) where they can return
meaningful error messages and be tested without a DB. DB CHECKs in 029 cover
structural integrity only: status enums, FK uniqueness, the one-preferred-
supplier invariant.

---

## What's in scope and what's deferred

**In 029 (schema only, no logic):**

- `item_suppliers` + `suppliers` extension (advance terms)
- `goods_receipts` / `goods_receipt_items` (GRN)
- `vendor_invoices` / `vendor_invoice_items`
- `po_invoice_allocations`
- `debit_notes` / `debit_note_items`
- `vendor_advances` / `vendor_advance_allocations`
- `purchase_orders` extension + `CLOSED` status

**Deferred by design:**

- **Purchase Indent (PI)** — no table in 029. v0.3 §2 starts the flow at PI,
  but PI + budget + intelligent generation is issue
  [#63](https://github.com/hd-stack-1858/tcb-demand-planning/issues/63)
  (P2, medium priority). The PO is currently the first persisted entity.
- **Advance clearing logic** — pro-rata clearing at GRN is gated on
  [#89](https://github.com/hd-stack-1858/tcb-demand-planning/issues/89)
  (vendor-advance accounting, needs CA input). `advance_due()` (how much to pay
  up front) is *not* gated and is safe to build in #67.
- **E-way bill / GST e-invoicing** — bought, not built
  ([#65](https://github.com/hd-stack-1858/tcb-demand-planning/issues/65)).
  Building statutory document generation in-house is genuinely unattractive —
  it's externally-versioned with a demonstrated pattern of spec churn (GSTN
  announced, deferred, confirmed, then shelved its e-way bill changes inside
  seven weeks).

---

## Deviations from ERPNext's model (deliberate)

| ERPNext | Here | Why |
|---|---|---|
| Material Request (PI) | No table (deferred #63) | Out of epic scope; P2 |
| Supplier Quotation / Proforma Invoice | Not modeled | Not a requirement in this epic |
| Purchase Order | `purchase_orders` | Extant table extended, not replaced |
| Purchase Receipt | `goods_receipts` / `goods_receipt_items` | Same concept, TCB naming |
| Purchase Invoice | `vendor_invoices` / `vendor_invoice_items` | Renamed to avoid collision with the existing customer `invoices` tables |
| Debit Note | `debit_notes` / `debit_note_items` | Native |
| Advance allocation (manual/selective in ERPNext) | `vendor_advances` + `vendor_advance_allocations` | Automatic pro-rata at GRN requires custom logic in ERPNext too — here it's just a later epic, not a plugin |

---

## Naming and collisions

- **`vendor_invoices` vs `invoices`** — distinct. `vendor_invoices` = money we
  owe a supplier; `invoices` / `invoice_items` (migration 01) = money a customer
  channel owes us. Do not cross-reference them.
- All monetary values are `NUMERIC` (₹ INR); surrogate `SERIAL` PKs named
  `*_id` per existing schema style.

---

## Renumbering note

Originally planned as **028**, renamed to **029** because
`setup/migrations/028_feature_flags.sql` already exists on dev (feature-flag
system, merged via PR #30). Issue #66 and #69 bodies reflect 029.

---

## Sources

- `landscape_tech_study/erpnext_procurement_spike.md` — v4 decision memo
  (Option B selected)
- `ims_oms_v0.3_workflow_design.md` — §2 inward flow, §5 vendor advances
- Issue [#66](https://github.com/hd-stack-1858/tcb-demand-planning/issues/66)
  and this epic's review thread
