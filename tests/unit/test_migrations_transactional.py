"""Unit tests for migration 029 (procurement) safety properties.

No DB, no network — asserts on the SQL/text itself that the migration is
transactional (BEGIN/COMMIT), idempotent (IF NOT EXISTS guards on every
ALTER), defines the status CHECK once in its final form (CLOSED included), and
recreates the purchase_orders / purchase_order_items skeleton tables that 029's
foreign keys depend on. Also guards that setup/sync_dev_with_prod.py no longer
drops those two restored tables in its stale-table sweep.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

MIGRATION_029 = ROOT / "setup" / "migrations" / "029_procurement.sql"
SYNC_TOOL = ROOT / "setup" / "sync_dev_with_prod.py"

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION_029.read_text()


@pytest.fixture(scope="module")
def sync_tool() -> str:
    return SYNC_TOOL.read_text()


def test_029_is_transactional(sql):
    assert "\nBEGIN;\n" in sql, "migration must open a transaction with BEGIN;"
    assert sql.rstrip().endswith("COMMIT;"), "migration must close with COMMIT;"


def test_029_alters_are_idempotent(sql):
    suppliers = re.search(
        r"ALTER TABLE suppliers\n(?P<body>.*?);", sql, re.S
    ).group("body")
    assert "ADD COLUMN IF NOT EXISTS advance_type" in suppliers
    assert "ADD COLUMN IF NOT EXISTS advance_value" in suppliers
    po_extension = re.search(
        r"ALTER TABLE purchase_orders\n(?P<body>.*?);", sql, re.S
    ).group("body")
    for col in ("terminal_date", "advance_type", "advance_value", "payment_terms"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in po_extension


def test_029_status_check_defined_once_with_closed(sql):
    """CLOSED lives in the prologue CHECK; section 13 only upgrades pre-existing
    tables that lack it — no create-then-drop-then-recreate of the same CHECK."""
    po_table = re.search(
        r"CREATE TABLE IF NOT EXISTS purchase_orders \((?P<body>.*?)\);", sql, re.S
    ).group("body")
    assert "'CLOSED'" in po_table
    assert "NOT LIKE '%CLOSED%'" in sql


def test_029_recreates_purchase_orders_skeleton(sql):
    assert sql.index("BEGIN;") < sql.index("CREATE TABLE IF NOT EXISTS purchase_orders")
    for table in ("purchase_orders", "purchase_order_items"):
        block = sql.split(f"CREATE TABLE IF NOT EXISTS {table} (", 1)[1].split(");", 1)[0]
        assert "updated_at" in block
        assert "TIMESTAMPTZ DEFAULT NOW()" in block


def test_po_tables_not_in_stale_drop_list(sync_tool):
    """sync_dev_with_prod.py must not drop the tables 029 restores (PR #105)."""
    block = sync_tool.split("STALE_TABLES = [", 1)[1].split("]", 1)[0]
    assert "purchase_orders" not in block
    assert "purchase_order_items" not in block
    assert "DROP TABLE IF EXISTS purchase_orders" not in sync_tool
    assert "DROP TABLE IF EXISTS purchase_order_items" not in sync_tool
