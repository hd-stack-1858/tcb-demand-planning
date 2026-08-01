# Procurement L0 — Pure Functions (`tcb/procurement.py`)

Added by issue [#67](https://github.com/hd-stack-1858/tcb-demand-planning/issues/67).
This is the pure-logic layer of the procurement module — no I/O, no DB.
The storage layer it reads is built by migration 029 ([`docs/procurement.md`](./procurement.md)).

---

## Overview

`tcb/procurement.py` contains three public functions:

| Function | Purpose |
|---|---|
| `advance_due(contract_terms, po_value)` | How much ₹ to pay a supplier at PO issuance |
| `effective_terms(item_id, supplier_id, item_suppliers, supplier_defaults)` | Resolve commercial terms for an item×supplier pair |
| `preferred_supplier(item_id, item_suppliers)` | Which supplier is preferred for an item |

All inputs are plain Python dicts matching DB row shapes. Callers are responsible for fetching from the DB and passing the data in. This layer is tested exhaustively without a DB (see `tests/test_procurement_terms.py`).

---

## `advance_due(contract_terms, po_value) -> Decimal`

Returns the advance amount (₹ INR) to pay when a PO is issued.

Design reference: §5 of `ims_oms_v0.3_workflow_design.md` — vendor advance payments.

### `contract_terms` keys

| Key | Type | Notes |
|---|---|---|
| `advance_type` | `str` | Required. One of `"none"`, `"percent"`, `"fixed"` |
| `advance_value` | `Decimal\|float\|None` | Required when `advance_type` ≠ `"none"` |

### Resolution rules

| `advance_type` | Result |
|---|---|
| `"none"` | `Decimal("0.00")` |
| `"percent"` | `po_value × (advance_value / 100)`, rounded to 2 dp (ROUND_HALF_UP) |
| `"fixed"` | `advance_value` (absolute ₹ amount, regardless of PO size) |

### Validation (raises `ProcurementError`)

- `advance_type` must be one of `"none"`, `"percent"`, `"fixed"`
- When `advance_type` ≠ `"none"`, `advance_value` must be provided
- `percent` advance_value must be in `[0, 100]`
- `fixed` advance_value must be `≥ 0`

### Example

```python
from tcb.procurement import advance_due
from decimal import Decimal

terms = {"advance_type": "percent", "advance_value": Decimal("30")}
advance_due(terms, 50000)  # → Decimal("15000.00")

terms = {"advance_type": "fixed", "advance_value": Decimal("5000")}
advance_due(terms, 50000)  # → Decimal("5000.00")

terms = {"advance_type": "none"}
advance_due(terms, 50000)  # → Decimal("0.00")
```

---

## `effective_terms(item_id, supplier_id, item_suppliers, supplier_defaults) -> dict`

Resolves the effective commercial terms (COGS, lead time, MOQ) for a specific item × supplier pair.

### Resolution order (per §2 of design doc)

1. **Per-pair override** — the `item_suppliers` row where `item_id` and `supplier_id` match (non-None values take precedence)
2. **Supplier default** — the `supplier_defaults` dict (the `suppliers` table row)

Each of `cogs`, `lead_time_days`, `moq` falls back to the supplier default if the per-pair value is `None` or no pair row exists.

### Parameters

| Param | Type | Notes |
|---|---|---|
| `item_id` | `int` | |
| `supplier_id` | `int` | |
| `item_suppliers` | `list[dict]` | All `item_suppliers` rows (caller fetches; zero I/O here) |
| `supplier_defaults` | `dict` | The `suppliers` row for this supplier |

### Returns

```python
{
    "cogs":          Decimal | None,   # resolved cost per unit
    "lead_time_days": int | None,
    "moq":           int | None,
    "advance_type":  str,              # always from supplier_defaults
    "advance_value": Decimal | None,   # always from supplier_defaults
    "payment_terms": str | None,       # always from supplier_defaults
    "is_preferred":  bool,             # from pair row; False if no pair
    "is_active":     bool,             # from pair row; False if no pair
}
```

Advance terms (`advance_type`, `advance_value`, `payment_terms`) always come from the supplier level — they are never overridden per item.

### Validation (raises `ProcurementError`)

- Resolved `moq` must be `> 0` if not `None`
- Resolved `lead_time_days` must be `> 0` if not `None`
- `None` is valid for both — means "not yet configured"

### Example

```python
from tcb.procurement import effective_terms
from decimal import Decimal

item_suppliers = [
    {"item_id": 10, "supplier_id": 1, "cogs": Decimal("45.00"),
     "lead_time_days": 5, "moq": 50, "is_preferred": True, "is_active": True},
]
supplier_defaults = {
    "advance_type": "percent", "advance_value": Decimal("10"),
    "payment_terms": "Net 30", "cogs": Decimal("50.00"),
    "lead_time_days": 7, "moq": 100,
}

terms = effective_terms(10, 1, item_suppliers, supplier_defaults)
# → {"cogs": Decimal("45.00"), "lead_time_days": 5, "moq": 50,
#    "advance_type": "percent", "advance_value": Decimal("10"),
#    "payment_terms": "Net 30", "is_preferred": True, "is_active": True}
```

---

## `preferred_supplier(item_id, item_suppliers) -> int | None`

Returns the `supplier_id` of the preferred, active supplier for `item_id`, or `None`.

A supplier is preferred if `is_preferred=True` **and** `is_active=True`. At most one per item (enforced by partial unique index in migration 029).

---

## `ProcurementError`

`tcb.procurement.ProcurementError` (subclass of `ValueError`) is raised for all business-rule violations. Callers should catch this to surface user-readable errors.

---

## What is NOT here (by design)

- **Pro-rata advance clearing at GRN** — blocked on #89 (CA sign-off on accounting treatment). This goes in #59 once #89 is resolved.
- **DB access** — all reads/writes for this module are in `tcb/db.py` (L1, #68).
- **Validation of advance_type/advance_value in DB CHECK constraints** — these are enforced in this L0 layer instead, where errors can give meaningful messages and be tested without a DB.

---

## Running the tests

```bash
python -m pytest tests/test_procurement_terms.py -q
```

No DB required — pure Python, 48 tests, 100% branch coverage on validation edge cases.
