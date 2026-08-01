"""
Schema tests for migration 029 (procurement).

Asserts the tables, columns, types, and constraints created by
`setup/migrations/029_procurement.sql` actually hold in the database.

Connection: reads `TCB_TEST_DB_URL` env var, falling back to `DEV_DB_URL` in
`.env.dev`. Skips cleanly when neither is set so the module can be collected
in environments without a configured dev DB.

Run:
    python -m pytest tests/test_procurement_schema.py -q
"""
import os
from pathlib import Path

import psycopg2
import pytest

ROOT = Path(__file__).resolve().parent.parent


def _db_url() -> str:
    url = os.environ.get("TCB_TEST_DB_URL")
    if url:
        return url
    try:
        from dotenv import dotenv_values
        dev = dotenv_values(ROOT / ".env.dev")
    except Exception:
        dev = {}
    return dev.get("DEV_DB_URL", "")


def _parse_url(url: str) -> dict:
    s = url[len("postgresql://"):]
    ui, hi = s.rsplit("@", 1)
    user, pw = ui.split(":", 1)
    hp, db = hi.rsplit("/", 1)
    host, port = hp.rsplit(":", 1)
    # Supabase requires SSL; local Postgres (validation) does not.
    sslmode = "require" if host not in ("localhost", "127.0.0.1") else "prefer"
    return dict(host=host, port=int(port), dbname=db, user=user, password=pw, sslmode=sslmode)


@pytest.fixture(scope="module")
def conn():
    url = _db_url()
    if not url:
        pytest.skip("No DB URL — set TCB_TEST_DB_URL or DEV_DB_URL in .env.dev")
    conn = psycopg2.connect(**_parse_url(url))
    yield conn
    conn.close()


# ── introspection helpers ────────────────────────────────────────────────────

def _q(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def table_exists(conn, table):
    rows = _q(conn, """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
    """, (table,))
    return bool(rows)


def column(conn, table, col):
    """Return (data_type, is_nullable, column_default) or None."""
    rows = _q(conn, """
        SELECT data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
    """, (table, col))
    return rows[0] if rows else None


def numeric_scale(conn, table, col):
    rows = _q(conn, """
        SELECT numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
    """, (table, col))
    return rows[0] if rows else None


def check_constraint_defs(conn, table):
    """All CHECK constraint definitions on the table, as text."""
    return [d for (d,) in _q(conn, """
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = %s AND c.contype = 'c'
    """, (table,))]


def table_unique_keys(conn, table):
    """Set of frozensets of column names forming a UNIQUE constraint/index."""
    rows = _q(conn, """
        SELECT i.indexrelid::regclass::text, a.attname
        FROM pg_index i
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey)
        WHERE t.relname = %s AND i.indisunique
    """, (table,))
    by_index: dict[str, set] = {}
    for index_name, col in rows:
        by_index.setdefault(index_name, set()).add(col)
    return {frozenset(cols) for cols in by_index.values()}


def fk_targets(conn, table):
    """List of (local_cols, ref_table) for each FK constraint on the table."""
    fks = _q(conn, """
        SELECT c.conname,
               array_agg(a.attname ORDER BY k.ordinality) AS local_cols,
               cl.relname AS ref_table
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ordinality) ON true
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        JOIN pg_class cl ON cl.oid = c.confrelid
        WHERE t.relname = %s AND c.contype = 'f'
        GROUP BY c.conname, cl.relname
    """, (table,))
    return [(tuple(cols), ref) for (_name, cols, ref) in fks]


def index_is_unique(conn, index_name):
    rows = _q(conn, """
        SELECT i.indisunique
        FROM pg_index i
        JOIN pg_class t ON t.oid = i.indexrelid
        WHERE t.relname = %s
    """, (index_name,))
    return rows[0][0] if rows else None


def index_def(conn, index_name):
    rows = _q(conn, """
        SELECT pg_get_indexdef(i.indexrelid)
        FROM pg_index i
        JOIN pg_class t ON t.oid = i.indexrelid
        WHERE t.relname = %s
    """, (index_name,))
    return rows[0][0] if rows else None


def require_column(conn, table, col, data_type, scale=None):
    info = column(conn, table, col)
    assert info is not None, f"missing column {table}.{col}"
    assert info[0] == data_type, f"{table}.{col} type {info[0]} != {data_type}"
    if scale is not None:
        got = numeric_scale(conn, table, col)
        assert got == scale, f"{table}.{col} numeric scale {got} != {scale}"
    return info


# ══════════════════════════════════════════════════════════════════════════════
# tables exist
# ══════════════════════════════════════════════════════════════════════════════

NEW_TABLES = [
    "item_suppliers",
    "goods_receipts",
    "goods_receipt_items",
    "vendor_invoices",
    "vendor_invoice_items",
    "po_invoice_allocations",
    "debit_notes",
    "debit_note_items",
    "vendor_advances",
    "vendor_advance_allocations",
]


class TestNewTables:

    @pytest.mark.parametrize("tbl", NEW_TABLES)
    def test_table_exists(self, conn, tbl):
        assert table_exists(conn, tbl), f"table {tbl} missing"


# ══════════════════════════════════════════════════════════════════════════════
# suppliers extension
# ══════════════════════════════════════════════════════════════════════════════

class TestSuppliersExtension:

    def test_advance_columns(self, conn):
        info = require_column(conn, "suppliers", "advance_type", "text")
        assert info[2] == "'none'::text", f"advance_type default {info[2]}"
        require_column(conn, "suppliers", "advance_value", "numeric", scale=(10, 2))

    def test_advance_type_check(self, conn):
        defs = " ".join(check_constraint_defs(conn, "suppliers"))
        for v in ("none", "percent", "fixed"):
            assert v in defs, f"suppliers advance_type CHECK missing '{v}'"


# ══════════════════════════════════════════════════════════════════════════════
# item_suppliers
# ══════════════════════════════════════════════════════════════════════════════

class TestItemSuppliers:

    def test_columns(self, conn):
        require_column(conn, "item_suppliers", "item_supplier_id", "integer")
        require_column(conn, "item_suppliers", "item_id", "integer")
        require_column(conn, "item_suppliers", "supplier_id", "integer")
        require_column(conn, "item_suppliers", "cogs", "numeric", scale=(10, 4))
        require_column(conn, "item_suppliers", "lead_time_days", "integer")
        require_column(conn, "item_suppliers", "moq", "integer")
        require_column(conn, "item_suppliers", "is_preferred", "boolean")
        require_column(conn, "item_suppliers", "is_active", "boolean")
        require_column(conn, "item_suppliers", "created_at", "timestamp with time zone")

    def test_unique_item_supplier_pair(self, conn):
        keys = table_unique_keys(conn, "item_suppliers")
        assert frozenset({"item_id", "supplier_id"}) in keys

    def test_at_most_one_preferred_per_item(self, conn):
        assert index_is_unique(conn, "item_suppliers_one_preferred_idx") is True
        assert "WHERE" in index_def(conn, "item_suppliers_one_preferred_idx")


# ══════════════════════════════════════════════════════════════════════════════
# goods_receipts / goods_receipt_items
# ══════════════════════════════════════════════════════════════════════════════

class TestGoodsReceipts:

    def test_columns(self, conn):
        require_column(conn, "goods_receipts", "grn_id", "integer")
        require_column(conn, "goods_receipts", "grn_number", "text")
        require_column(conn, "goods_receipts", "po_id", "integer")
        require_column(conn, "goods_receipts", "received_date", "date")
        info = require_column(conn, "goods_receipts", "received_by", "text")
        assert info[2] == "'system'::text", f"received_by default {info[2]}"
        require_column(conn, "goods_receipts", "status", "text")

    def test_po_fk(self, conn):
        targets = fk_targets(conn, "goods_receipts")
        assert ("po_id",) in [c for c, _ in targets], "goods_receipts.po_id FK missing"

    def test_status_check(self, conn):
        defs = " ".join(check_constraint_defs(conn, "goods_receipts"))
        for v in ("DRAFT", "POSTED", "CANCELLED"):
            assert v in defs


class TestGoodsReceiptItems:

    def test_fks(self, conn):
        targets = {cols for cols, _ in fk_targets(conn, "goods_receipt_items")}
        assert ("grn_id",) in targets
        assert ("poi_id",) in targets
        assert ("item_id",) in targets

    def test_columns(self, conn):
        require_column(conn, "goods_receipt_items", "quantity_received", "integer")
        require_column(conn, "goods_receipt_items", "cost_per_unit", "numeric", scale=(10, 4))
        require_column(conn, "goods_receipt_items", "line_total", "numeric", scale=(10, 2))
        require_column(conn, "goods_receipt_items", "reject_qty", "integer")


# ══════════════════════════════════════════════════════════════════════════════
# vendor_invoices / vendor_invoice_items
# ══════════════════════════════════════════════════════════════════════════════

class TestVendorInvoices:

    def test_columns(self, conn):
        require_column(conn, "vendor_invoices", "invoice_id", "integer")
        require_column(conn, "vendor_invoices", "invoice_number", "text")
        require_column(conn, "vendor_invoices", "supplier_id", "integer")
        require_column(conn, "vendor_invoices", "invoice_date", "date")
        require_column(conn, "vendor_invoices", "due_date", "date")
        require_column(conn, "vendor_invoices", "total_value", "numeric", scale=(10, 2))
        require_column(conn, "vendor_invoices", "tax_amount", "numeric", scale=(10, 2))

    def test_invoice_number_unique(self, conn):
        keys = table_unique_keys(conn, "vendor_invoices")
        assert frozenset({"invoice_number"}) in keys

    def test_supplier_fk_and_status(self, conn):
        assert ("supplier_id",) in [c for c, _ in fk_targets(conn, "vendor_invoices")]
        defs = " ".join(check_constraint_defs(conn, "vendor_invoices"))
        for v in ("DRAFT", "POSTED", "PAID", "PARTIALLY_PAID", "CANCELLED"):
            assert v in defs


class TestVendorInvoiceItems:

    def test_fks(self, conn):
        targets = {cols for cols, _ in fk_targets(conn, "vendor_invoice_items")}
        assert ("invoice_id",) in targets
        assert ("item_id",) in targets

    def test_columns(self, conn):
        require_column(conn, "vendor_invoice_items", "quantity", "integer")
        require_column(conn, "vendor_invoice_items", "cost_per_unit", "numeric", scale=(10, 4))
        require_column(conn, "vendor_invoice_items", "line_total", "numeric", scale=(10, 2))
        require_column(conn, "vendor_invoice_items", "gst_pct", "numeric", scale=(5, 2))
        require_column(conn, "vendor_invoice_items", "gst_amt", "numeric", scale=(10, 2))


# ══════════════════════════════════════════════════════════════════════════════
# po_invoice_allocations
# ══════════════════════════════════════════════════════════════════════════════

class TestPoInvoiceAllocations:

    def test_fks(self, conn):
        targets = {cols for cols, _ in fk_targets(conn, "po_invoice_allocations")}
        assert ("po_id",) in targets
        assert ("invoice_id",) in targets

    def test_unique_po_invoice_pair(self, conn):
        keys = table_unique_keys(conn, "po_invoice_allocations")
        assert frozenset({"po_id", "invoice_id"}) in keys


# ══════════════════════════════════════════════════════════════════════════════
# debit_notes / debit_note_items
# ══════════════════════════════════════════════════════════════════════════════

class TestDebitNotes:

    def test_columns(self, conn):
        require_column(conn, "debit_notes", "debit_note_id", "integer")
        require_column(conn, "debit_notes", "debit_note_number", "text")
        require_column(conn, "debit_notes", "supplier_id", "integer")
        require_column(conn, "debit_notes", "po_id", "integer")
        require_column(conn, "debit_notes", "invoice_id", "integer")
        require_column(conn, "debit_notes", "grn_id", "integer")
        require_column(conn, "debit_notes", "debit_date", "date")
        require_column(conn, "debit_notes", "reason", "text")
        require_column(conn, "debit_notes", "status", "text")
        require_column(conn, "debit_notes", "total_value", "numeric", scale=(10, 2))

    def test_fks(self, conn):
        targets = {cols for cols, _ in fk_targets(conn, "debit_notes")}
        assert ("supplier_id",) in targets
        assert ("po_id",) in targets
        assert ("invoice_id",) in targets
        assert ("grn_id",) in targets

    def test_optional_fks_nullable(self, conn):
        for col in ("po_id", "invoice_id", "grn_id"):
            info = column(conn, "debit_notes", col)
            assert info is not None and info[1] == "YES", f"debit_notes.{col} should be nullable"


class TestDebitNoteItems:

    def test_fks_and_columns(self, conn):
        targets = {cols for cols, _ in fk_targets(conn, "debit_note_items")}
        assert ("debit_note_id",) in targets
        assert ("item_id",) in targets
        require_column(conn, "debit_note_items", "quantity", "integer")
        require_column(conn, "debit_note_items", "cost_per_unit", "numeric", scale=(10, 4))
        require_column(conn, "debit_note_items", "line_total", "numeric", scale=(10, 2))


# ══════════════════════════════════════════════════════════════════════════════
# vendor_advances / vendor_advance_allocations
# ══════════════════════════════════════════════════════════════════════════════

class TestVendorAdvances:

    def test_columns(self, conn):
        require_column(conn, "vendor_advances", "advance_id", "integer")
        require_column(conn, "vendor_advances", "supplier_id", "integer")
        require_column(conn, "vendor_advances", "advance_date", "date")
        require_column(conn, "vendor_advances", "amount", "numeric", scale=(10, 2))
        require_column(conn, "vendor_advances", "method", "text")
        require_column(conn, "vendor_advances", "reference", "text")
        require_column(conn, "vendor_advances", "status", "text")

    def test_fk_and_status(self, conn):
        assert ("supplier_id",) in [c for c, _ in fk_targets(conn, "vendor_advances")]
        defs = " ".join(check_constraint_defs(conn, "vendor_advances"))
        for v in ("OPEN", "ALLOCATED", "CLOSED", "CANCELLED"):
            assert v in defs


class TestVendorAdvanceAllocations:

    def test_fks(self, conn):
        targets = {cols for cols, _ in fk_targets(conn, "vendor_advance_allocations")}
        assert ("advance_id",) in targets
        assert ("po_id",) in targets
        assert ("grn_id",) in targets

    def test_columns(self, conn):
        require_column(conn, "vendor_advance_allocations", "amount", "numeric", scale=(10, 2))
        require_column(conn, "vendor_advance_allocations", "allocated_date", "date")


# ══════════════════════════════════════════════════════════════════════════════
# purchase_orders — kept columns + extension + status enum
# ══════════════════════════════════════════════════════════════════════════════

class TestPurchaseOrders:

    def test_advance_paid_balance_due_kept(self, conn):
        """PV 2026-08-01: keep these until the vendor_advances ledger is live."""
        assert column(conn, "purchase_orders", "advance_paid") is not None
        assert column(conn, "purchase_orders", "balance_due") is not None

    def test_extension_columns(self, conn):
        require_column(conn, "purchase_orders", "terminal_date", "date")
        require_column(conn, "purchase_orders", "advance_type", "text")
        require_column(conn, "purchase_orders", "advance_value", "numeric", scale=(10, 2))
        require_column(conn, "purchase_orders", "payment_terms", "text")

    def test_status_check_includes_closed(self, conn):
        defs = " ".join(check_constraint_defs(conn, "purchase_orders"))
        for v in ("DRAFT", "SENT", "CONFIRMED", "PARTIAL", "RECEIVED", "CANCELLED", "CLOSED"):
            assert v in defs, f"purchase_orders status CHECK missing '{v}'"
