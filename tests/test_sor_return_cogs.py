"""
tests/test_sor_return_cogs.py — regression tests for #104: Unsold SOR return uses
FIFO COGS, not fallback.

Closes #104: when unsold SOR stock (e.g. Blinkit) is returned physically to OWN_WH
without a matching originating order, return_sku() must:
  1. FIFO-consume the partner channel lot (decrement qty_remaining).
  2. Create an OWN_WH lot at the original FIFO unit_cogs, NOT the fallback COGS.

The failure mode is identical to #102: _consume_lots_fifo filters by
partner_location_id IS NULL, misses all real SOR lots (which have non-NULL location),
raises ValueError, and falls through to _get_sku_cogs_fallback. The tier-2 channel-wide
pool fix in return_sku() addresses both #102 (BLK recall) and #104 (SOR unsold return)
with the same code change.

These are integration tests — they require a real dev DB (TCB_ENV=dev via conftest.py).
Run: python -m pytest tests/test_sor_return_cogs.py -q
"""
import os
import pytest

os.environ.setdefault("TCB_ENV", "dev")

from tcb.db import get_client
from tcb.inventory import return_sku

pytestmark = pytest.mark.integration

PYTEST_REF = "PYTEST_SOR_RETURN_COGS"

# A deliberately unusual COGS value so we can distinguish it from any fallback COGS
_ORIGINAL_COGS = 777.77


@pytest.fixture
def db():
    return get_client()


@pytest.fixture
def sor_channel(db):
    """Use the BLK channel (business_model=SOR) — simplest real SOR channel on dev."""
    row = db.table("channels").select("channel_id").eq("code", "BLK").single().execute().data
    return row["channel_id"]


@pytest.fixture
def own_wh_id(db):
    row = db.table("channels").select("channel_id").eq("code", "OWN_WH").single().execute().data
    return row["channel_id"]


@pytest.fixture
def sor_partner_location(db, sor_channel):
    rows = (db.table("partner_locations")
              .select("location_id")
              .eq("channel_id", sor_channel)
              .eq("location_type", "WH")
              .eq("is_active", True)
              .limit(1).execute().data)
    if not rows:
        pytest.skip("No active SOR WH location in dev.")
    return rows[0]["location_id"]


@pytest.fixture
def test_sku(db):
    row = db.table("skus").select("sku_id").eq("is_active", True).limit(1).execute().data
    if not row:
        pytest.skip("No active SKU in dev.")
    return row[0]["sku_id"]


@pytest.fixture
def sor_lot(db, test_sku, sor_channel, sor_partner_location):
    """Seed a SOR lot with a non-NULL location and a distinctive COGS value."""
    result = db.table("sku_cogs_lots").insert({
        "sku_id":              test_sku,
        "channel_id":          sor_channel,
        "partner_location_id": sor_partner_location,
        "assembled_at":        "2026-02-01",
        "unit_cogs":           _ORIGINAL_COGS,
        "qty_assembled":       8,
        "qty_remaining":       8,
    }).execute()
    lot = result.data[0]
    yield lot
    db.table("sku_cogs_lots").delete().eq("lot_id", lot["lot_id"]).execute()
    db.table("sku_inventory_transactions").delete().eq("reference", PYTEST_REF).execute()


def test_unsold_sor_return_no_location_uses_fifo_cogs(db, test_sku, sor_channel, own_wh_id,
                                                       sor_lot):
    """
    Unsold SOR stock returned without specifying a location (the typical case — Himanshu
    selects 'SOR' channel but the stock came back mixed from multiple WHs or the specific
    WH wasn't captured) must still consume the SOR lot and restore at original COGS.

    Before the fix: partner_location_id=None → FIFO searched IS NULL lots → found none →
    ValueError → fallback COGS (e.g. 724.70) used instead of 777.77.
    After the fix: tier-2 channel-wide pool finds the lot and uses its 777.77 COGS.
    """
    return_qty = 5

    return_sku(test_sku, return_qty, sor_channel,
               notes=PYTEST_REF, partner_location_id=None)

    # SOR lot must be decremented
    updated = (db.table("sku_cogs_lots")
                 .select("qty_remaining")
                 .eq("lot_id", sor_lot["lot_id"])
                 .single().execute().data)
    assert updated["qty_remaining"] == 8 - return_qty, (
        f"SOR lot not decremented (#104 regression): expected {8 - return_qty}, "
        f"got {updated['qty_remaining']}"
    )

    # OWN_WH lot must carry the original distinctive COGS
    own_lot = (db.table("sku_cogs_lots")
                 .select("unit_cogs")
                 .eq("sku_id", test_sku)
                 .eq("channel_id", own_wh_id)
                 .is_("partner_location_id", "null")
                 .eq("unit_cogs", _ORIGINAL_COGS)
                 .execute().data)
    assert own_lot, (
        f"OWN_WH lot at original COGS ({_ORIGINAL_COGS}) not found — "
        "fallback COGS was used (#104 still present)"
    )


def test_unsold_sor_return_with_location_uses_fifo_cogs(db, test_sku, sor_channel, own_wh_id,
                                                         sor_partner_location, sor_lot):
    """Tier-1 (location-specific) path still works — regression guard for existing behavior."""
    return_qty = 3

    return_sku(test_sku, return_qty, sor_channel,
               notes=PYTEST_REF, partner_location_id=sor_partner_location)

    updated = (db.table("sku_cogs_lots")
                 .select("qty_remaining")
                 .eq("lot_id", sor_lot["lot_id"])
                 .single().execute().data)
    assert updated["qty_remaining"] == 8 - return_qty

    own_lot = (db.table("sku_cogs_lots")
                 .select("unit_cogs")
                 .eq("sku_id", test_sku)
                 .eq("channel_id", own_wh_id)
                 .is_("partner_location_id", "null")
                 .eq("unit_cogs", _ORIGINAL_COGS)
                 .execute().data)
    assert own_lot, (
        f"OWN_WH lot at original COGS ({_ORIGINAL_COGS}) not found after location-specific return"
    )
