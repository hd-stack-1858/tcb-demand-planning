"""Unit tests for migration 029 (procurement) safety properties.

No DB, no network — asserts on the SQL text itself that the migration is
transactional (BEGIN/COMMIT), idempotent (IF NOT EXISTS guards on every
ALTER), and that it recreates the purchase_orders / purchase_order_items
skeleton tables that 029's foreign keys depend on (both were dropped during
the DB cleanup and are restored as a prologue).
"""

from pathlib import Path

import pytest

MIGRATION_029 = (
    Path(__file__).resolve().parent.parent.parent
    / "setup" / "migrations" / "029_procurement.sql"
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION_029.read_text()


def test_029_is_transactional(sql):
    assert "\nBEGIN;\n" in sql, "migration must open a transaction with BEGIN;"
    assert sql.rstrip().endswith("COMMIT;"), "migration must close with COMMIT;"


def test_029_alters_are_idempotent(sql):
    suppliers = sql.split("-- 1. suppliers", 1)[1].split("-- 2. item_suppliers", 1)[0]
    assert "ADD COLUMN IF NOT EXISTS advance_type" in suppliers
    assert "ADD COLUMN IF NOT EXISTS advance_value" in suppliers
    po_extension = sql.split("-- 12. purchase_orders", 1)[1].split("-- 13.", 1)[0]
    for col in ("terminal_date", "advance_type", "advance_value", "payment_terms"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in po_extension


def test_029_recreates_purchase_orders_skeleton(sql):
    assert sql.index("BEGIN;") < sql.index("CREATE TABLE IF NOT EXISTS purchase_orders")
    for table in ("purchase_orders", "purchase_order_items"):
        block = sql.split(f"CREATE TABLE IF NOT EXISTS {table} (", 1)[1].split(");", 1)[0]
        assert "updated_at" in block
        assert "TIMESTAMPTZ DEFAULT NOW()" in block
