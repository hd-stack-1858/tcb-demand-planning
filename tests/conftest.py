"""
Shared pytest fixtures for TCB demand planning tests.
Always runs against dev DB — never prod.
"""
import os
import pytest

# Force dev DB before any tcb imports
os.environ["TCB_ENV"] = "dev"

from tcb.db import get_client
from tcb.inventory import return_sku
from tcb.catalog import CATALOG_COGS


@pytest.fixture(scope="session")
def db():
    return get_client()


@pytest.fixture(scope="session")
def own_wh_id(db):
    return db.table("channels").select("channel_id").eq("code", "OWN_WH").single().execute().data["channel_id"]


@pytest.fixture(scope="session", autouse=True)
def seed_dev_cogs(db, own_wh_id):
    """
    Ensure every active SKU has:
      1. At least one ASSEMBLY txn so fallback COGS lookups work.
      2. At least one open sku_cogs_lots row so _consume_lots_fifo() never
         hits zero on dev (where item_batches is empty).
    Skips any SKU that already has ASSEMBLY history or an open lot.
    Non-PYTEST_ reference keeps clean_test_orders from wiping it mid-session.
    """
    # ── ASSEMBLY txns ────────────────────────────────────────────────────────
    existing_asm = {
        r["sku_id"]
        for r in db.table("sku_inventory_transactions")
                   .select("sku_id").eq("type", "ASSEMBLY").execute().data
    }
    asm_rows = [
        {"type": "ASSEMBLY", "sku_id": sku_id, "to_channel_id": own_wh_id,
         "quantity": 1, "unit_cogs": unit_cogs,
         "reference": "SEED_DEV_COGS_PYTEST", "created_by": "pytest"}
        for sku_id, unit_cogs in CATALOG_COGS.items()
        if sku_id not in existing_asm
    ]
    if asm_rows:
        db.table("sku_inventory_transactions").insert(asm_rows).execute()

    # ── sku_cogs_lots ────────────────────────────────────────────────────────
    existing_lots = {
        r["sku_id"]
        for r in db.table("sku_cogs_lots")
                   .select("sku_id")
                   .eq("channel_id", own_wh_id)
                   .gt("qty_remaining", 0)
                   .execute().data
    }
    seeded_lot_ids = []
    for sku_id, unit_cogs in CATALOG_COGS.items():
        if sku_id in existing_lots:
            continue
        result = db.table("sku_cogs_lots").insert({
            "sku_id":       sku_id,
            "channel_id":   own_wh_id,
            "assembled_at": "2025-12-01",
            "unit_cogs":    unit_cogs,
            "qty_assembled": 50,
            "qty_remaining": 50,
        }).execute()
        if result.data:
            seeded_lot_ids.append(result.data[0]["lot_id"])

    yield

    # ── Teardown ─────────────────────────────────────────────────────────────
    if asm_rows:
        db.table("sku_inventory_transactions").delete() \
          .eq("reference", "SEED_DEV_COGS_PYTEST").execute()
    for lot_id in seeded_lot_ids:
        db.table("sku_cogs_lots").delete().eq("lot_id", lot_id).execute()


@pytest.fixture
def restore_sku(db):
    """
    Tracks dispatched SKU units and returns them to OWN_WH after each test.
    Usage: restore_sku(sku_id, qty, from_channel_id)
    """
    dispatches = []

    def _track(sku_id, qty, from_channel_id):
        dispatches.append((sku_id, qty, from_channel_id))

    yield _track

    for sku_id, qty, from_channel_id in dispatches:
        try:
            return_sku(sku_id, qty, from_channel_id, notes="pytest-teardown")
        except Exception as e:
            print(f"\n[teardown warning] Could not restore {qty}x {sku_id}: {e}")


@pytest.fixture
def clean_test_orders(db):
    """Deletes all orders rows with platform_order_id starting with PYTEST_ after test."""
    yield
    rows = (db.table("orders")
              .select("order_id")
              .like("platform_order_id", "PYTEST_%")
              .execute().data)
    for r in rows:
        db.table("orders").delete().eq("order_id", r["order_id"]).execute()
    db.table("sku_inventory_transactions").delete().like("reference", "PYTEST_%").execute()
