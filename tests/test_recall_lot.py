"""
tests/test_recall_lot.py — regression tests for #102: Recall reduces lot quantity.

Closes #102: before the fix, calling return_sku() for a SOR/BLK channel with
partner_location_id=None fell through to _consume_lots_fifo(partner_location_id=None),
which searched for lots WHERE partner_location_id IS NULL — a set that is always empty
for real partner channels (all lots created by dispatch_sku() have a non-NULL location).
This caused ValueError → fallback COGS path, so the partner lot was never decremented
and the OWN_WH lot was created at fallback (not original) COGS.

The fix adds a tier-2 channel-wide fallback in return_sku(): when the location-specific
pool (tier-1) is exhausted, try all lots for the channel regardless of location. Only
if both tiers fail does it fall through to the COGS fallback.

These are integration tests — they require a real dev DB (TCB_ENV=dev via conftest.py).
Run: python -m pytest tests/test_recall_lot.py -q
"""
import os
import pytest
from datetime import date

os.environ.setdefault("TCB_ENV", "dev")

from tcb.db import get_client
from tcb.inventory import return_sku

pytestmark = pytest.mark.integration

PYTEST_REF = "PYTEST_RECALL_LOT"


@pytest.fixture
def db():
    return get_client()


@pytest.fixture
def blk_channel(db):
    row = db.table("channels").select("channel_id").eq("code", "BLK").single().execute().data
    return row["channel_id"]


@pytest.fixture
def own_wh_id(db):
    row = db.table("channels").select("channel_id").eq("code", "OWN_WH").single().execute().data
    return row["channel_id"]


@pytest.fixture
def blk_partner_location(db, blk_channel):
    """Return an active BLK WH location for seeding lots."""
    rows = (db.table("partner_locations")
              .select("location_id")
              .eq("channel_id", blk_channel)
              .eq("location_type", "WH")
              .eq("is_active", True)
              .limit(1).execute().data)
    if not rows:
        pytest.skip("No active BLK WH location in dev — seed partner_locations first.")
    return rows[0]["location_id"]


@pytest.fixture
def test_sku(db):
    """Use the first active SKU available."""
    row = db.table("skus").select("sku_id").eq("is_active", True).limit(1).execute().data
    if not row:
        pytest.skip("No active SKU in dev.")
    return row[0]["sku_id"]


@pytest.fixture
def blk_lot(db, test_sku, blk_channel, blk_partner_location):
    """Seed a BLK lot with a non-NULL location_id (the real shape dispatch_sku creates)."""
    original_cogs = 500.00
    result = db.table("sku_cogs_lots").insert({
        "sku_id":              test_sku,
        "channel_id":          blk_channel,
        "partner_location_id": blk_partner_location,
        "assembled_at":        "2026-01-01",
        "unit_cogs":           original_cogs,
        "qty_assembled":       10,
        "qty_remaining":       10,
    }).execute()
    lot = result.data[0]
    yield lot
    # Teardown — delete the lot and any RETURN txn we created
    db.table("sku_cogs_lots").delete().eq("lot_id", lot["lot_id"]).execute()
    db.table("sku_inventory_transactions").delete().eq("reference", PYTEST_REF).execute()


def test_recall_with_location_decrements_partner_lot(db, test_sku, blk_channel, own_wh_id,
                                                      blk_partner_location, blk_lot):
    """Tier-1 path: explicit partner_location_id → lot decremented at original COGS."""
    original_cogs = blk_lot["unit_cogs"]
    return_qty = 3

    return_sku(test_sku, return_qty, blk_channel,
               notes=PYTEST_REF, partner_location_id=blk_partner_location)

    # Partner lot must be decremented
    updated = (db.table("sku_cogs_lots")
                 .select("qty_remaining")
                 .eq("lot_id", blk_lot["lot_id"])
                 .single().execute().data)
    assert updated["qty_remaining"] == 10 - return_qty, (
        f"Partner lot not decremented: expected {10 - return_qty}, "
        f"got {updated['qty_remaining']}"
    )

    # OWN_WH lot must be at the original COGS, not a fallback value
    own_lot = (db.table("sku_cogs_lots")
                 .select("unit_cogs, assembled_at")
                 .eq("sku_id", test_sku)
                 .eq("channel_id", own_wh_id)
                 .is_("partner_location_id", "null")
                 .eq("unit_cogs", original_cogs)
                 .execute().data)
    assert own_lot, (
        f"OWN_WH lot at original COGS ({original_cogs}) not found — "
        "fallback COGS was used instead of FIFO"
    )


def test_recall_without_location_decrements_partner_lot(db, test_sku, blk_channel, own_wh_id,
                                                         blk_lot):
    """Tier-2 path: partner_location_id=None → channel-wide pool → lot still decremented.

    This is the recall bug: the UI doesn't always know which BLK WH the stock
    came back from, so partner_location_id may be None. Before the fix, this
    path silently skipped the partner lot and created a fallback COGS OWN_WH lot.
    After the fix, tier-2 pool finds the lot regardless of location and decrements it.
    """
    original_cogs = blk_lot["unit_cogs"]
    return_qty = 2

    # Called without partner_location_id — this is the Bug A scenario from k1a audit
    return_sku(test_sku, return_qty, blk_channel,
               notes=PYTEST_REF, partner_location_id=None)

    # Partner lot MUST be decremented even though we passed location=None
    updated = (db.table("sku_cogs_lots")
                 .select("qty_remaining")
                 .eq("lot_id", blk_lot["lot_id"])
                 .single().execute().data)
    assert updated["qty_remaining"] == 10 - return_qty, (
        f"Partner lot not decremented (Bug A regression): expected {10 - return_qty}, "
        f"got {updated['qty_remaining']}"
    )

    # OWN_WH lot must carry the original COGS, not the fallback
    own_lot = (db.table("sku_cogs_lots")
                 .select("unit_cogs")
                 .eq("sku_id", test_sku)
                 .eq("channel_id", own_wh_id)
                 .is_("partner_location_id", "null")
                 .eq("unit_cogs", original_cogs)
                 .execute().data)
    assert own_lot, (
        f"OWN_WH lot at original COGS ({original_cogs}) not found — "
        "fallback COGS used (Bug A still present)"
    )

    # RETURN transaction recorded
    txn = (db.table("sku_inventory_transactions")
             .select("quantity, unit_cogs")
             .eq("sku_id", test_sku)
             .eq("type", "RETURN")
             .eq("reference", PYTEST_REF)
             .execute().data)
    assert txn, "RETURN transaction not recorded"
    assert txn[0]["unit_cogs"] == original_cogs, (
        f"RETURN txn unit_cogs={txn[0]['unit_cogs']} — expected {original_cogs}"
    )
