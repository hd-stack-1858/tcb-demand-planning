"""
L1 repository — item↔supplier mapping and supplier CRUD (issue #68).

Single-concern DB access for the `item_suppliers` table and the extended
`suppliers` table. All DB access goes through `tcb/db.py` (get_client).

The Supabase client is injectable so downstream L2 work (PO issuance, GRN)
can fake it without a network connection.

Rows are returned shaped as the L0 types in `tcb/procurement`
(ItemSupplierRow, ContractTerms) so effective_terms() / preferred_supplier()
compose directly. Business validation reuses the L0 helpers and raises
ProcurementError.
"""

from __future__ import annotations

from typing import Any

from supabase import Client

from tcb.db import get_client
from tcb.procurement import (
    ContractTerms,
    ItemSupplierRow,
    ProcurementError,
    _validate_contract_terms,
    _validate_item_supplier_row,
)


class ProcurementRepo:
    """CRUD + lookup for `item_suppliers` and `suppliers`.

    Parameters
    ----------
    client : Client | None
        Supabase client to run queries against. Defaults to the project
        client from tcb/db.py. Pass a fake in tests / L2 callers.
    """

    def __init__(self, client: Client | None = None):
        self._client = client or get_client()

    # ------------------------------------------------------------------
    # suppliers
    # ------------------------------------------------------------------

    def list_suppliers(self, active_only: bool = True) -> list[ContractTerms]:
        """Return supplier rows (with advance terms), ordered by name.

        active_only=True filters to is_active rows.
        """
        q = self._client.table("suppliers").select("*")
        if active_only:
            q = q.eq("is_active", True)
        return q.order("name").execute().data

    def get_supplier(self, supplier_id: int) -> ContractTerms | None:
        """Return one supplier row, or None when the id is missing."""
        rows = (
            self._client.table("suppliers")
            .select("*")
            .eq("supplier_id", supplier_id)
            .limit(1)
            .execute().data
        )
        return rows[0] if rows else None

    def create_supplier(self, row: ContractTerms) -> int:
        """Insert a supplier and return its supplier_id.

        Raises ProcurementError if advance terms are invalid (L0 validation).
        """
        _validate_contract_terms(row)
        res = self._client.table("suppliers").insert(row).execute()
        return res.data[0]["supplier_id"]

    def update_supplier(self, supplier_id: int, updates: dict[str, Any]) -> None:
        """Patch a supplier row by supplier_id."""
        self._client.table("suppliers").update(updates).eq(
            "supplier_id", supplier_id
        ).execute()

    def deactivate_supplier(self, supplier_id: int) -> None:
        """Soft-delete a supplier (is_active=False)."""
        self.update_supplier(supplier_id, {"is_active": False})

    # ------------------------------------------------------------------
    # item_suppliers
    # ------------------------------------------------------------------

    def list_item_suppliers(
        self,
        item_id: int | None = None,
        supplier_id: int | None = None,
        active_only: bool = True,
    ) -> list[ItemSupplierRow]:
        """Return item↔supplier rows, optionally filtered.

        Every filter is optional: by item, by supplier, or active-only.
        Passing neither id returns all rows (subject to active_only).
        """
        q = self._client.table("item_suppliers").select("*")
        if item_id is not None:
            q = q.eq("item_id", item_id)
        if supplier_id is not None:
            q = q.eq("supplier_id", supplier_id)
        if active_only:
            q = q.eq("is_active", True)
        return q.execute().data

    def get_item_supplier(
        self, item_id: int, supplier_id: int
    ) -> ItemSupplierRow | None:
        """Return the single item↔supplier pair row, or None.

        At most one row exists per pair (UNIQUE(item_id, supplier_id)).
        """
        rows = (
            self._client.table("item_suppliers")
            .select("*")
            .eq("item_id", item_id)
            .eq("supplier_id", supplier_id)
            .limit(1)
            .execute().data
        )
        return rows[0] if rows else None

    def upsert_item_supplier(self, row: ItemSupplierRow) -> int:
        """Insert or update an item↔supplier pair and return its id.

        Conflict target is UNIQUE(item_id, supplier_id). On conflict the
        submitted fields are updated: cogs, lead_time_days, moq,
        is_preferred (and is_active when passed); is_active and created_at
        are left untouched when omitted. Setting is_preferred=True first
        demotes any other preferred pair for the same item (the partial
        unique index enforces at most one).

        Raises ProcurementError if moq or lead_time_days are invalid.
        """
        _validate_item_supplier_row(row)
        row = dict(row)
        if row.get("is_preferred"):
            self._clear_preferred(
                row["item_id"], exclude_supplier=row["supplier_id"])
        res = (
            self._client.table("item_suppliers")
            .upsert(row, on_conflict="item_id,supplier_id")
            .execute()
        )
        return res.data[0]["item_supplier_id"]

    def set_preferred(self, item_id: int, supplier_id: int) -> None:
        """Make the pair the preferred supplier for the item.

        Demotes every preferred row for the item (all rows where
        is_preferred=True), then promotes this pair — mirroring the
        item_suppliers_one_preferred_idx partial unique index.
        """
        self._clear_preferred(item_id)
        self._client.table("item_suppliers").update({"is_preferred": True}).eq(
            "item_id", item_id
        ).eq("supplier_id", supplier_id).execute()

    def deactivate_item_supplier(self, item_id: int, supplier_id: int) -> None:
        """Soft-delete an item↔supplier pair (is_active=False)."""
        self._client.table("item_suppliers").update({"is_active": False}).eq(
            "item_id", item_id
        ).eq("supplier_id", supplier_id).execute()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _clear_preferred(
        self, item_id: int, exclude_supplier: int | None = None
    ) -> None:
        """Set is_preferred=False on all preferred rows for an item.

        Scoped to the item and is_preferred=True so no other item's rows are
        touched. exclude_supplier (used by upsert, never by set_preferred)
        leaves the pair being (re)written out of the demotion.
        """
        q = (
            self._client.table("item_suppliers")
            .update({"is_preferred": False})
            .eq("item_id", item_id)
            .eq("is_preferred", True)
        )
        if exclude_supplier is not None:
            q = q.neq("supplier_id", exclude_supplier)
        q.execute()
