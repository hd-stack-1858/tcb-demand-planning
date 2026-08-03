# Procurement Workflow Guide

How goods get bought, received, invoiced, and paid for — in plain terms. This
is the operational view of the procurement module. It exists so the real-world
flow can be reviewed against the intended design **before** the logic layers
(L0/L1/L2) are built on top of the schema. If any step here doesn't match how
The Cradle Box actually procures, that's the deviation to flag now.

Companion docs: [`procurement.md`](procurement.md) (schema reference) and
[`procurement_design.md`](procurement_design.md) (why the schema is shaped the
way it is).

---

## The lifecycle at a glance

```
Indent → PO → [Advance] → GRN → Vendor invoice → Match/Allocate → Debit note
         (contract fork)                        (short/reject)
```

| # | Step | What happens | Money/inventory impact |
|---|---|---|---|
| 1 | **Purchase Indent (PI)** | Demand is turned into an internal purchase request | None — a documented request only |
| 2 | **Purchase Order (PO)** | A PO is issued to a chosen supplier for an item + quantity | None (unless advance — step 3) |
| 3 | **Advance payment** *(only if the supplier's contract requires one)* | Cash paid to supplier up front | Cash ↓, new asset "advance to vendor" ↑ — **not an expense** |
| 4 | **Goods receipt (GRN)** | Physical goods counted in, item by item | Inventory value ↑ at what actually arrived |
| 5 | **Vendor invoice** | Supplier bills us | Accounts payable ↑ |
| 6 | **Match / allocate** | Invoice linked to the PO(s) it covers | Pending-payable reconciled against POs |
| 7 | **Debit note** *(only for short-ship or rejected goods)* | We claim money back from the supplier | Payable ↓ by the claim amount |

> [!IMPORTANT]
> **GRN is the moment inventory value changes on the books** — not PO issue and
> not invoice receipt. This comes straight from v0.3 §2 of the workflow design.

---

## Step-by-step

### 1. Purchase Indent (PI)

A documented internal request for stock, driven by demand/stockout risk. In
v0.3 the loop is: stockout risk → auto-draft the next PI → approve (budget
check) → vendor selection → PO.

**In this schema (029):** there is **no PI table**. PI is deferred to issue
[#63](https://github.com/hd-stack-1858/tcb-demand-planning/issues/63)
(P2, "Purchase Indent, budget & intelligent generation"). For now the PO is the
first thing that exists as data. This is an intentional scope cut, not an
oversight — flag it if the live process depends on tracking indents before POs.

### 2. Purchase Order (PO)

The commitment to a supplier. Each PO line references one item, an ordered
quantity, a unit cost.

- One demand can split into **multiple POs** (e.g. across suppliers).
- The PO carries a **contract-terms snapshot** (`advance_type`,
  `advance_value`, `payment_terms`) frozen at creation time — if the supplier's
  terms change later, existing POs don't retroactively change.

**Status flow:**

```
DRAFT → SENT → CONFIRMED → PARTIAL → RECEIVED
              ↘            ↘
                CANCELLED    CLOSED
```

- `PARTIAL` = partially **received** (not partially sent).
- `CLOSED` = remaining quantity intentionally abandoned — distinct from fully
  `RECEIVED`. Pairs with `terminal_date` (when it was closed).
- `advance_paid` / `balance_due` columns still exist on `purchase_orders` but
  are **legacy** — see the design doc. New advance tracking lives in the
  `vendor_advances` ledger.

### 3. Advance payment (contract fork)

Whether a PO pays cash up front is decided by the **supplier's** contract
terms, not per-PO guesswork (`advance_type`: none / percent of PO value /
fixed amount).

- The advance is **not an expense**. It creates an asset — a claim against the
  supplier for future goods.
- It is cleared against payables **pro-rata at GRN**: if a PO worth ₹10,000 had
  a 50% advance and only half the goods arrive, ₹2,500 of the advance is
  cleared and ₹2,500 stays held against the still-pending balance.

> [!WARNING]
> **Schema exists, clearing logic does not.** 029 creates the
> `vendor_advances` / `vendor_advance_allocations` tables only. Pro-rata
> clearing at GRN is gated on [#89](https://github.com/hd-stack-1858/tcb-demand-planning/issues/89)
> (vendor-advance accounting needs CA input) and lands in a later epic.
> `advance_due()` — how much to pay up front — is safe to build now (#67).

### 4. Goods receipt (GRN)

The physical receiving event, item by item. May be less than ordered, and may
arrive across several shipments/invoices.

- Each GRN links to a PO; each GRN line links back to a **PO line**
  (`poi_id`) and an item, with quantity actually received and `reject_qty`
  (short-shipped or quality-rejected).
- `received_by` records who performed the receipt (audit trail).
- GRN reduces the PO's pending quantity proportionally when partial.

**Status flow:** `DRAFT → POSTED` (or `CANCELLED`). `POSTED` is the point at
which inventory value moves.

> A GRN line with `reject_qty > 0` at POST time is what drives debit-note
> creation later (#61).

### 5. Vendor invoice

The supplier's bill. Distinct from the customer-facing `invoices` tables —
"vendor invoice" is money we owe, "invoice" is money a channel owes us.

**Status flow:** `DRAFT → POSTED → PARTIALLY_PAID → PAID` (or `CANCELLED`).

### 6. Match / allocate

PO↔invoice is **many-to-many** (v0.3 §2): one invoice can cover several POs,
one PO can be split across several invoices.

`po_invoice_allocations` records how much of a PO a given invoice covers.
`UNIQUE(po_id, invoice_id)` guarantees one allocation row per PO↔invoice pair,
so amounts are never ambiguous.

### 7. Debit note

A claim against the supplier for short-ship or rejected goods — most commonly
born from a GRN rejection. Links to the source: at least one of `po_id`,
`invoice_id`, or `grn_id` should be set.

**Status flow:** `DRAFT → POSTED` (or `CANCELLED`).

---

## Where the logic layers fit (L0 / L1 / L2)

| Layer | What it owns | Status |
|---|---|---|
| **L0** pure functions (`tcb/procurement.py`) | `advance_due()`, `effective_terms()`, lead-time/MOQ resolution, validation | #67 — next after schema |
| **L1** repo CRUD (`tcb/db.py`) | Read/write for `item_suppliers` + extended `suppliers` | #68 |
| **L2** posting logic | PO lifecycle (#58), GRN posting (#59), invoice matching + debit notes (#60), advance payment/clearing/exposure (#61) | later epics |

---

## Open decisions that shape these flows

1. **Excess receipt policy** — what happens when more goods arrive than
   ordered? ([#80](https://github.com/hd-stack-1858/tcb-demand-planning/issues/80))
2. **Vendor-advance accounting** — how advances clear pro-rata, needs CA
   input. ([#89](https://github.com/hd-stack-1858/tcb-demand-planning/issues/89))
3. **GST / e-way bill** — bought, not built (see design doc).
   ([#65](https://github.com/hd-stack-1858/tcb-demand-planning/issues/65))

---

## Review checklist for Himanshu

- Is the **order of events** right (indent → PO → advance → GRN → invoice →
  allocate → debit note)?
- Is GRN the true moment inventory value changes in the live process?
- Are the **status transitions** on PO / GRN / invoice / debit note complete?
- Is `PARTIAL` (partial receipt) and `CLOSED` (abandoned remainder) the right
  way to model incomplete POs?
- Is an advance ever treated as an expense in practice (it shouldn't be)?
- Is the **PI → PO split** acceptable, or do we need indents tracked before
  POs exist?
