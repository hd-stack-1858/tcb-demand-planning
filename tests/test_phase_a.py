"""
Phase A tests — drop-ship sale capture + COGS lots + MRP/state enrichment.
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
from tcb.geo import city_to_state

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
        assert txn["to_channel_id"] == DS_CHANNEL

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
        """COGS is sourced from sku_cogs_lots (seeded by conftest). Must be > 0."""
        record_dropship_sale(TEST_SKU, 1, DS_CHANNEL, SELL_PRICE,
                             platform_order_id="PYTEST_sale_003")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        row = get_order(db, "PYTEST_sale_003")
        assert row["cogs"] > 0, "COGS must be > 0 — check sku_cogs_lots seed in conftest"

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


# ══════════════════════════════════════════════════════════════════════════════
# COGS lots tests
# ══════════════════════════════════════════════════════════════════════════════

class TestCogsLots:

    def test_open_lot_exists_for_test_sku(self, db, own_wh_id):
        """Conftest must have seeded an open lot for TCB011 at OWN_WH."""
        lots = (db.table("sku_cogs_lots")
                  .select("qty_remaining")
                  .eq("sku_id", TEST_SKU)
                  .eq("channel_id", own_wh_id)
                  .gt("qty_remaining", 0)
                  .execute().data)
        assert lots, f"No open COGS lots for {TEST_SKU} at OWN_WH — check conftest seed"

    def test_dispatch_decrements_lot_total(self, db, own_wh_id, restore_sku):
        """Dispatching 1 unit reduces total lot qty_remaining by exactly 1."""
        def total_remaining():
            rows = (db.table("sku_cogs_lots")
                      .select("qty_remaining")
                      .eq("sku_id", TEST_SKU)
                      .eq("channel_id", own_wh_id)
                      .execute().data)
            return sum(r["qty_remaining"] for r in rows)

        before = total_remaining()
        dispatch_sku(TEST_SKU, 1, DS_CHANNEL, reference="PYTEST_lot_dec")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        assert total_remaining() == before - 1

    def test_dispatch_txn_carries_unit_cogs(self, db, restore_sku):
        """DISPATCH transaction must record unit_cogs from lots."""
        dispatch_sku(TEST_SKU, 1, DS_CHANNEL, reference="PYTEST_lot_cogs")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        rows = (db.table("sku_inventory_transactions")
                  .select("unit_cogs")
                  .eq("reference", "PYTEST_lot_cogs")
                  .execute().data)
        assert rows
        assert rows[0]["unit_cogs"] is not None
        assert float(rows[0]["unit_cogs"]) > 0

    def test_transfer_out_creates_partner_lot(self, db, own_wh_id, restore_sku):
        """TRANSFER_OUT must mirror a lot to the destination channel."""
        dispatch_sku(TEST_SKU, 1, BULK_CHANNEL, reference="PYTEST_lot_transfer")
        restore_sku(TEST_SKU, 1, BULK_CHANNEL)

        partner_lots = (db.table("sku_cogs_lots")
                          .select("qty_remaining, qty_assembled")
                          .eq("sku_id", TEST_SKU)
                          .eq("channel_id", BULK_CHANNEL)
                          .execute().data)
        assert partner_lots, "Partner lots must be created on TRANSFER_OUT"
        assert sum(l["qty_assembled"] for l in partner_lots) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# MRP + state enrichment tests
# ══════════════════════════════════════════════════════════════════════════════

class TestMrpAndState:

    def test_mrp_populated_in_orders(self, db, restore_sku, clean_test_orders):
        """MRP must be fetched from sku_pricing and written to orders."""
        record_dropship_sale(TEST_SKU, 1, DS_CHANNEL, SELL_PRICE,
                             platform_order_id="PYTEST_mrp_001", city="Mumbai")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        row = get_order(db, "PYTEST_mrp_001")
        assert row is not None
        assert row["mrp"] is not None and float(row["mrp"]) > 0, \
            "MRP must be populated from sku_pricing"

    def test_discount_pct_computed_when_mrp_above_sp(self, db, restore_sku, clean_test_orders):
        """discount_pct = (mrp - sp) / mrp × 100 when MRP > SP."""
        record_dropship_sale(TEST_SKU, 1, DS_CHANNEL, SELL_PRICE,
                             platform_order_id="PYTEST_disc_001")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        row = get_order(db, "PYTEST_disc_001")
        if row["mrp"] and float(row["mrp"]) > float(row["selling_price"]):
            assert row["discount_pct"] is not None
            expected = round((float(row["mrp"]) - float(row["selling_price"])) / float(row["mrp"]) * 100, 2)
            assert abs(float(row["discount_pct"]) - expected) < 0.01

    def test_state_resolved_from_known_city(self, db, restore_sku, clean_test_orders):
        """State must be auto-filled for a known city."""
        record_dropship_sale(TEST_SKU, 1, DS_CHANNEL, SELL_PRICE,
                             platform_order_id="PYTEST_state_001", city="Bengaluru")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        row = get_order(db, "PYTEST_state_001")
        assert row["state"] == "Karnataka"

    def test_state_null_for_unknown_city(self, db, restore_sku, clean_test_orders):
        """State must be NULL when city is not in the lookup map."""
        record_dropship_sale(TEST_SKU, 1, DS_CHANNEL, SELL_PRICE,
                             platform_order_id="PYTEST_state_002", city="Atlantis")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        row = get_order(db, "PYTEST_state_002")
        assert row["state"] is None

    def test_state_null_when_no_city(self, db, restore_sku, clean_test_orders):
        """State must be NULL when city is omitted."""
        record_dropship_sale(TEST_SKU, 1, DS_CHANNEL, SELL_PRICE,
                             platform_order_id="PYTEST_state_003")
        restore_sku(TEST_SKU, 1, DS_CHANNEL)

        row = get_order(db, "PYTEST_state_003")
        assert row["state"] is None


# ── Unit tests for geo lookup (no DB needed) ──────────────────────────────────

class TestGeoLookup:
    def test_known_cities(self):
        assert city_to_state("Bengaluru")  == "Karnataka"
        assert city_to_state("bangalore")  == "Karnataka"   # case-insensitive
        assert city_to_state("Hyderabad")  == "Telangana"
        assert city_to_state("Mumbai")     == "Maharashtra"
        assert city_to_state("Gurgaon")    == "Haryana"
        assert city_to_state("Delhi")      == "Delhi"
        assert city_to_state("Noida")      == "Uttar Pradesh"

    def test_unknown_city_returns_none(self):
        assert city_to_state("Atlantis")   is None
        assert city_to_state("")           is None
        assert city_to_state(None)         is None

    def test_strips_whitespace(self):
        assert city_to_state("  Mumbai  ") == "Maharashtra"
