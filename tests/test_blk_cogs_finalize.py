"""Regression tests for #103 — finalize_blk_cogs() ignores lot_id and state proxy.

Two root causes fixed by this change:

  (a) `finalize_blk_cogs()` never reads an order's pre-existing `lot_id` — it
      FIFO-re-consumes `sku_cogs_lots` for every pending order, even one already
      stamped with a lot_id (from an earlier run that was interrupted, or from a
      loader that pre-resolved the lot). An order with `lot_id` set must take COGS
      straight from that lot with NO further consumption.

  (b) when `supply_state` is NULL the code substitutes `order["state"]` as a proxy
      (tcb/inventory.py:616) and feeds that customer-state into tier-1 state-level
      FIFO — the exact cross-state drift K1a says must not happen. NULL supply_state
      must fall to tier-2 channel-pool FIFO (supply_state=None), never the proxy.

Run: python -m pytest tests/test_blk_cogs_finalize.py -q
"""
import pytest

pytestmark = pytest.mark.integration

PYTEST_PREFIX = "PYTEST_103_"


@pytest.fixture
def blk_channel(db):
    row = db.table("channels").select("channel_id").eq("code", "BLK").single().execute().data
    return row["channel_id"]


@pytest.fixture
def clean_sku(db, blk_channel):
    """An active SKU with no open BLK lots, so this test's own lots are the entire
    BLK channel pool — FIFO order is fully deterministic."""
    open_skus = {
        r["sku_id"]
        for r in db.table("sku_cogs_lots")
                   .select("sku_id")
                   .eq("channel_id", blk_channel)
                   .gt("qty_remaining", 0)
                   .execute().data
    }
    rows = (db.table("skus").select("sku_id").eq("is_discontinued", False).limit(50).execute().data)
    for r in rows:
        if r["sku_id"] not in open_skus:
            return r["sku_id"]
    pytest.skip("No active SKU without open BLK lots in dev")


@pytest.fixture
def seeded_lots(db):
    """Tracks created sku_cogs_lots rows and deletes them in teardown."""
    created = []

    def _add(lot):
        res = db.table("sku_cogs_lots").insert(lot).execute()
        created.append(res.data[0])
        return res.data[0]

    yield _add
    for lot in created:
        db.table("sku_cogs_lots").delete().eq("lot_id", lot["lot_id"]).execute()


@pytest.fixture
def seeded_order(db, blk_channel):
    """Tracks created orders and deletes them in teardown."""
    created = []

    def _add(**overrides):
        row = {
            "platform_order_id": f"{PYTEST_PREFIX}{len(created) + 1}",
            "channel_id": blk_channel,
            "status": "FULFILLED",
            "fulfillment_type": "SOR",
            "quantity": 2,
            "order_date": "2026-01-01",
            "lot_cogs_finalized": False,
            **overrides,
        }
        res = db.table("orders").insert(row).execute()
        created.append(res.data[0])
        return res.data[0]

    yield _add
    for order in created:
        db.table("orders").delete().eq("order_id", order["order_id"]).execute()


@pytest.fixture
def karnataka_location(db, blk_channel):
    """A BLK WH location in Karnataka, created for this test and torn down after.
    Requested BEFORE `seeded_lots` so its teardown runs last (FK: lots must be
    deleted before the location row)."""
    res = db.table("partner_locations").insert({
        "channel_id": blk_channel,
        "name": "PYTEST_103_KARNATAKA_WH",
        "state": "Karnataka",
        "location_type": "WH",
        "is_active": True,
    }).execute()
    loc = res.data[0]
    yield loc["location_id"]
    db.table("partner_locations").delete().eq("location_id", loc["location_id"]).execute()


def _get_order(db, order):
    return db.table("orders").select("*").eq("order_id", order["order_id"]).single().execute().data


def _lot_qty(db, lot):
    return db.table("sku_cogs_lots").select("qty_remaining").eq("lot_id", lot["lot_id"]).single().execute().data["qty_remaining"]


def test_prepopulated_lot_id_takes_cogs_without_reconsume(
        db, blk_channel, clean_sku, seeded_lots, seeded_order):
    """(a) Order already stamped with lot_id → COGS straight from that lot, no
    further lot consumption, even when an older (FIFO-first) lot exists."""
    from tcb.inventory import finalize_blk_cogs

    older_lot = seeded_lots({
        "sku_id": clean_sku, "channel_id": blk_channel,
        "partner_location_id": None,
        "assembled_at": "2025-01-01", "unit_cogs": 999.0,
        "qty_assembled": 10, "qty_remaining": 10,
    })
    stamped_lot = seeded_lots({
        "sku_id": clean_sku, "channel_id": blk_channel,
        "partner_location_id": None,
        "assembled_at": "2025-06-01", "unit_cogs": 250.0,
        "qty_assembled": 10, "qty_remaining": 10,
    })
    order = seeded_order(sku_id=clean_sku, lot_id=stamped_lot["lot_id"],
                              supply_state=None, state="Karnataka")

    finalize_blk_cogs(order_ids=[order["order_id"]])

    updated = _get_order(db, order)
    assert updated["cogs"] == 500.0, (
        f"Expected COGS from stamped lot (250 × 2) = 500.0, got {updated['cogs']}"
    )
    assert updated["lot_id"] == stamped_lot["lot_id"], (
        f"lot_id should stay {stamped_lot['lot_id']} (pre-populated), got {updated['lot_id']}"
    )
    assert updated["lot_cogs_finalized"] is True
    assert _lot_qty(db, stamped_lot) == 10, "Stamped lot must NOT be re-consumed"
    assert _lot_qty(db, older_lot) == 10, "Older lot must not be consumed when lot_id is set"


def test_null_supply_state_never_uses_customer_state_proxy(
        db, blk_channel, clean_sku, karnataka_location, seeded_lots, seeded_order):
    """(b) supply_state=None → tier-2 channel-pool FIFO. The customer `state`
    must NOT be fed into tier-1 state-level consumption (K1a cross-state drift)."""
    from tcb.inventory import finalize_blk_cogs

    pool_lot = seeded_lots({
        "sku_id": clean_sku, "channel_id": blk_channel,
        "partner_location_id": None,
        "assembled_at": "2025-01-01", "unit_cogs": 50.0,
        "qty_assembled": 10, "qty_remaining": 10,
    })
    karnataka_lot = seeded_lots({
        "sku_id": clean_sku, "channel_id": blk_channel,
        "partner_location_id": karnataka_location,
        "assembled_at": "2026-01-01", "unit_cogs": 100.0,
        "qty_assembled": 10, "qty_remaining": 10,
    })
    order = seeded_order(sku_id=clean_sku, supply_state=None, state="Karnataka")

    finalize_blk_cogs(order_ids=[order["order_id"]])

    updated = _get_order(db, order)
    assert updated["cogs"] == 100.0, (
        f"Expected tier-2 channel-pool COGS (50 × 2) = 100.0, got {updated['cogs']} "
        "- customer state must not feed tier-1"
    )
    assert updated["lot_id"] == pool_lot["lot_id"], (
        f"Expected lot from channel pool {pool_lot['lot_id']}, got {updated['lot_id']}"
    )
    assert updated["lot_cogs_finalized"] is True
    assert _lot_qty(db, pool_lot) == 8, "Channel-pool lot should be consumed by 2"
    assert _lot_qty(db, karnataka_lot) == 10, (
        "Karnataka lot must NOT be consumed - state proxy would have taken it"
    )
