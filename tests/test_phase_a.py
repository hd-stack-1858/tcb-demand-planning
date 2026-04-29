"""
Phase A tests — drop-ship sale capture.
Runs against dev DB (TCB_ENV=dev set in conftest.py).

Dev DB constants (verified 29-Apr-2026):
  TCB011: 18 units in stock  — primary test SKU
  channel 6: First Cry (DROP_SHIP)
  channel 2: Amazon FBA (FBA → TRANSFER_OUT)
"""
import pytest
from tcb.inventory import (
    get_sku_stock, dispatch_sku, record_dropship_sale,
)

TEST_SKU     = "TCB011"
DS_CHANNEL   = 6   # First Cry — DROP_SHIP
BULK_CHANNEL = 2   # Amazon FBA — FBA (→ TRANSFER_OUT)
SELL_PRICE   = 899.0


# ── helpers ───────────────────────────────────────────────────────────────────

def sku_qty(sku_id=TEST_SKU):
    """Current qty_on_hand for sku_id at OWN_WH."""
    return {r["sku_id"]: r["qty_on_hand"] for r in get_sku_stock()}.get(sku_id, 0)


def get_order(db, pid):
    rows = db.table("orders").select("*").eq("platform_order_id", pid).execute().data
    return rows[0] if rows else None


# ══════════════════════════════════════════════════════════════════════════════
# dispatch_sku() tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDispatchSku:

    def test_drop_ship_reduces_stock(self, restore_sku):
        before = sku_qty()
        assert before >= 1, f"Need ≥1 unit of {TEST_SKU} in dev"

        dispatch_sku(TEST_SKU, 1, DS_CHANNEL, reference="PYTEST_ds_stock")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        assert sku_qty() == before - 1

    def test_drop_ship_logs_dispatch_transaction(self, db, restore_sku):
        dispatch_sku(TEST_SKU, 1, DS_CHANNEL, reference="PYTEST_ds_txn")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        rows = (db.table("sku_inventory_transactions")
                  .select("type, sku_id, quantity, to_channel_id, from_channel_id")
                  .eq("reference", "PYTEST_ds_txn").execute().data)
        assert len(rows) == 1
        txn = rows[0]
        assert txn["type"] == "DISPATCH"
        assert txn["sku_id"] == TEST_SKU
        assert txn["quantity"] == 1
        assert txn["to_channel_id"] is None     # drop-ship goes to customer, not a WH

    def test_bulk_logs_transfer_out_with_destination(self, db, restore_sku):
        dispatch_sku(TEST_SKU, 1, BULK_CHANNEL, reference="PYTEST_bulk_txn")
        restore_sku(TEST_SKU, 1, BULK_CHANNEL)

        rows = (db.table("sku_inventory_transactions")
                  .select("type, to_channel_id")
                  .eq("reference", "PYTEST_bulk_txn").execute().data)
        assert len(rows) == 1
        txn = rows[0]
        assert txn["type"] == "TRANSFER_OUT"
        assert txn["to_channel_id"] == BULK_CHANNEL   # destination is set for bulk

    def test_insufficient_stock_raises(self):
        with pytest.raises(Exception, match="(?i)insufficient"):
            dispatch_sku(TEST_SKU, 99999, DS_CHANNEL, reference="PYTEST_ds_overflow")

    def test_insufficient_stock_does_not_change_stock(self):
        before = sku_qty()
        try:
            dispatch_sku(TEST_SKU, 99999, DS_CHANNEL, reference="PYTEST_ds_overflow2")
        except Exception:
            pass
        assert sku_qty() == before


# ══════════════════════════════════════════════════════════════════════════════
# record_dropship_sale() tests
# ══════════════════════════════════════════════════════════════════════════════

class TestRecordDropshipSale:

    def test_stock_reduced(self, restore_sku, clean_test_orders):
        before = sku_qty()
        assert before >= 1

        record_dropship_sale(TEST_SKU, 1, DS_CHANNEL, SELL_PRICE,
                             platform_order_id="PYTEST_sale_001", city="Mumbai")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        assert sku_qty() == before - 1

    def test_orders_row_fields(self, db, restore_sku, clean_test_orders):
        record_dropship_sale(TEST_SKU, 1, DS_CHANNEL, SELL_PRICE,
                             platform_order_id="PYTEST_sale_002", city="Delhi")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        row = get_order(db, "PYTEST_sale_002")
        assert row is not None,                   "orders row must be created"
        assert row["order_id"] is not None,       "order_id (UUID) must be auto-generated"
        assert row["sku_id"]         == TEST_SKU
        assert row["channel_id"]     == DS_CHANNEL
        assert row["selling_price"]  == SELL_PRICE
        assert row["gross_value"]    == SELL_PRICE   # qty=1
        assert row["fulfillment_type"] == "DROP_SHIP"
        assert row["status"]         == "FULFILLED"
        assert row["city"]           == "Delhi"
        assert row["source_file"]    == "warehouse_app"

    def test_cogs_positive_after_assembly(self, db, restore_sku, clean_test_orders):
        """
        COGS is sourced from the most recent ASSEMBLY transaction.
        Dev seed stock was loaded directly (no assembly history), so we
        assemble 1 unit first to create history, then verify COGS > 0.
        """
        from tcb.inventory import assemble_sku
        assemble_sku(TEST_SKU, 1, notes="pytest-cogs-setup")

        record_dropship_sale(TEST_SKU, 1, DS_CHANNEL, SELL_PRICE,
                             platform_order_id="PYTEST_sale_003")
        # restore_sku only for the sale dispatch (assembly is already consumed)
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        row = get_order(db, "PYTEST_sale_003")
        assert row["cogs"] > 0, "COGS should be > 0 after assembly history exists"

    def test_multi_qty_gross_value(self, db, restore_sku, clean_test_orders):
        before = sku_qty()
        assert before >= 2, "Need ≥2 units for multi-qty test"

        record_dropship_sale(TEST_SKU, 2, DS_CHANNEL, SELL_PRICE,
                             platform_order_id="PYTEST_sale_004")
        restore_sku(TEST_SKU, 2, DS_CHANNEL)

        row = get_order(db, "PYTEST_sale_004")
        assert row["quantity"]    == 2
        assert row["gross_value"] == round(2 * SELL_PRICE, 2)
        assert row["cogs"]        >= 0

    def test_platform_order_id_stored(self, db, restore_sku, clean_test_orders):
        pid = "PYTEST_sale_005"
        record_dropship_sale(TEST_SKU, 1, DS_CHANNEL, SELL_PRICE,
                             platform_order_id=pid)
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        row = get_order(db, pid)
        assert row["platform_order_id"] == pid

    def test_no_orders_row_on_insufficient_stock(self, db, clean_test_orders):
        """If dispatch fails, no orphan row must appear in orders."""
        before = len(db.table("orders").select("order_id").execute().data)

        with pytest.raises(Exception):
            record_dropship_sale(TEST_SKU, 99999, DS_CHANNEL, SELL_PRICE,
                                 platform_order_id="PYTEST_sale_fail_001")

        after = len(db.table("orders").select("order_id").execute().data)
        assert after == before, "No orders row should be created when dispatch fails"
