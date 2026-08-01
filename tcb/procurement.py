"""
L0 pure functions — vendor contract terms and advance calculation.

No I/O. All inputs are plain Python values; callers supply data fetched
from the DB. This layer is tested exhaustively with table-driven pytest
(tests/test_procurement_terms.py).

Design reference: ims_oms_v0.3_workflow_design.md §2/§5 — inward flow
and vendor advance payments.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


# ---------------------------------------------------------------------------
# Type aliases (plain dicts matching DB rows / dataclass-style callers)
# ---------------------------------------------------------------------------

# Represents a row from `item_suppliers` (or a dict with equivalent keys).
# Required keys: item_id, supplier_id, cogs, lead_time_days, moq, is_preferred, is_active.
ItemSupplierRow = dict[str, Any]

# Represents the advance-terms portion of a `suppliers` row.
# Required keys: advance_type ("none"|"percent"|"fixed"), advance_value (Decimal|float|None).
ContractTerms = dict[str, Any]


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

class ProcurementError(ValueError):
    """Raised when business-rule validation fails in this L0 module."""


def _validate_contract_terms(terms: ContractTerms) -> None:
    advance_type = terms.get("advance_type", "none")
    if advance_type not in ("none", "percent", "fixed"):
        raise ProcurementError(
            f"advance_type must be 'none', 'percent', or 'fixed'; got {advance_type!r}"
        )
    advance_value = terms.get("advance_value")
    if advance_type == "none":
        return
    if advance_value is None:
        raise ProcurementError(
            f"advance_value must be set when advance_type is {advance_type!r}"
        )
    advance_value = Decimal(str(advance_value))
    if advance_type == "percent":
        if advance_value < 0:
            raise ProcurementError("advance_value (percent) must be ≥ 0")
        if advance_value > 100:
            raise ProcurementError("advance_value (percent) must be ≤ 100")
    elif advance_type == "fixed":
        if advance_value < 0:
            raise ProcurementError("advance_value (fixed amount) must be ≥ 0")


def _validate_item_supplier_row(row: ItemSupplierRow) -> None:
    moq = row.get("moq")
    if moq is not None and moq <= 0:
        raise ProcurementError(
            f"moq must be > 0; got {moq}"
        )
    lead_time = row.get("lead_time_days")
    if lead_time is not None and lead_time <= 0:
        raise ProcurementError(
            f"lead_time_days must be > 0; got {lead_time}"
        )


# ---------------------------------------------------------------------------
# advance_due
# ---------------------------------------------------------------------------

def advance_due(contract_terms: ContractTerms, po_value: Decimal | float | int) -> Decimal:
    """
    Return the advance amount (₹) to pay at PO issuance for this supplier.

    Rules (§5 of v0.3 design):
      - advance_type == "none"    → ₹ 0
      - advance_type == "percent" → po_value × (advance_value / 100), rounded to 2 dp
      - advance_type == "fixed"   → advance_value (₹ amount), regardless of PO size

    Parameters
    ----------
    contract_terms : dict with keys ``advance_type`` and ``advance_value``
        Typically comes from a ``suppliers`` row (or the contract-snapshot
        columns on ``purchase_orders``).
    po_value : Decimal | float | int
        Total value of the PO in ₹ (INR).

    Raises
    ------
    ProcurementError
        If contract_terms contains invalid values.
    """
    _validate_contract_terms(contract_terms)
    po_value = Decimal(str(po_value))
    advance_type = contract_terms.get("advance_type", "none")

    if advance_type == "none":
        return Decimal("0.00")

    advance_value = Decimal(str(contract_terms["advance_value"]))

    if advance_type == "percent":
        result = po_value * (advance_value / Decimal("100"))
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # advance_type == "fixed"
    return advance_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# effective_terms — resolution for a single item×supplier pair
# ---------------------------------------------------------------------------

def effective_terms(
    item_id: int,
    supplier_id: int,
    item_suppliers: list[ItemSupplierRow],
    supplier_defaults: ContractTerms,
) -> dict[str, Any]:
    """
    Resolve the effective commercial terms for a given item × supplier pair.

    Resolution order (§2 of v0.3 design):
      1. Per-pair override from ``item_suppliers`` — the row where
         ``item_id`` and ``supplier_id`` match.
      2. Supplier-level defaults from ``supplier_defaults`` (the ``suppliers``
         row for this supplier).

    For each of ``cogs``, ``lead_time_days``, ``moq``: the per-pair value
    is used when non-None; otherwise the supplier default is used.

    Parameters
    ----------
    item_id : int
    supplier_id : int
    item_suppliers : list[ItemSupplierRow]
        All rows from ``item_suppliers`` (caller fetches; zero I/O here).
    supplier_defaults : ContractTerms
        The ``suppliers`` row for this supplier (advance_type, advance_value,
        payment_terms, plus any cogs/lead_time/moq defaults at supplier level).

    Returns
    -------
    dict with keys:
        ``cogs``, ``lead_time_days``, ``moq``, ``advance_type``,
        ``advance_value``, ``payment_terms``, ``is_preferred``, ``is_active``.

    Raises
    ------
    ProcurementError
        If the resolved row contains invalid moq or lead_time_days values.
    """
    # Find the per-pair row (there is at most one due to UNIQUE(item_id, supplier_id))
    pair_row: ItemSupplierRow | None = None
    for row in item_suppliers:
        if row.get("item_id") == item_id and row.get("supplier_id") == supplier_id:
            pair_row = row
            break

    def _resolve(key: str, pair_row: ItemSupplierRow | None, defaults: dict) -> Any:
        if pair_row is not None:
            val = pair_row.get(key)
            if val is not None:
                return val
        return defaults.get(key)

    resolved_moq = _resolve("moq", pair_row, supplier_defaults)
    resolved_lead = _resolve("lead_time_days", pair_row, supplier_defaults)

    # Validate resolved values before returning
    synthetic_row: ItemSupplierRow = {
        "moq": resolved_moq,
        "lead_time_days": resolved_lead,
    }
    _validate_item_supplier_row(synthetic_row)

    return {
        "cogs": _resolve("cogs", pair_row, supplier_defaults),
        "lead_time_days": resolved_lead,
        "moq": resolved_moq,
        "advance_type": supplier_defaults.get("advance_type", "none"),
        "advance_value": supplier_defaults.get("advance_value"),
        "payment_terms": supplier_defaults.get("payment_terms"),
        "is_preferred": pair_row.get("is_preferred", False) if pair_row else False,
        "is_active": pair_row.get("is_active", True) if pair_row else False,
    }


# ---------------------------------------------------------------------------
# preferred_supplier — convenience: which supplier is preferred for an item
# ---------------------------------------------------------------------------

def preferred_supplier(
    item_id: int,
    item_suppliers: list[ItemSupplierRow],
) -> int | None:
    """
    Return the supplier_id of the preferred supplier for item_id, or None.

    There is at most one preferred supplier per item (enforced by partial
    unique index on the DB).  Returns None when no preferred row exists or
    all rows are inactive.
    """
    for row in item_suppliers:
        if (
            row.get("item_id") == item_id
            and row.get("is_preferred") is True
            and row.get("is_active", True) is True
        ):
            return row.get("supplier_id")
    return None
