# Procurement L0 — Pure Functions

`tcb/procurement.py` — zero I/O, no DB. Added by issue [#67](https://github.com/hd-stack-1858/tcb-demand-planning/issues/67).

## Functions

- `advance_due(contract_terms, po_value) -> Decimal` — advance ₹ to pay at PO issuance (`none` / `percent` / `fixed`)
- `effective_terms(item_id, supplier_id, item_suppliers, supplier_defaults) -> dict` — per-pair override → supplier default resolution for COGS / lead-time / MOQ
- `preferred_supplier(item_id, item_suppliers) -> int | None`
- `ProcurementError(ValueError)` — raised on invalid inputs

Full signatures, resolution rules, and validation behaviour are in the module docstrings.

## Tests

```bash
python -m pytest tests/test_procurement_terms.py -q
```

No DB required. 48 tests, 100% branch coverage on validation edge cases.

## Scope boundaries

**Pro-rata advance clearing at GRN is not here** — gated on issue #89 (CA sign-off on accounting treatment). Builds in #59 once #89 resolves.

**DB CRUD is not here** — that is #68 (L1 repo).
