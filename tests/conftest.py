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


@pytest.fixture(scope="session", autouse=True)
def seed_dev_cogs(db):
    """
    Ensure every active SKU has at least one ASSEMBLY txn so _get_sku_cogs()
    never hits zero on dev (where item_batches is empty).
    Skips any SKU that already has ASSEMBLY history.
    Non-PYTEST_ reference keeps clean_test_orders from wiping it mid-session.
    """
    existing = {
        r["sku_id"]
        for r in db.table("sku_inventory_transactions")
                   .select("sku_id").eq("type", "ASSEMBLY").execute().data
    }
    rows = [
        {"type": "ASSEMBLY", "sku_id": sku_id, "to_channel_id": 1,
         "quantity": 1, "unit_cogs": unit_cogs,
         "reference": "SEED_DEV_COGS_PYTEST", "created_by": "pytest"}
        for sku_id, unit_cogs in CATALOG_COGS.items()
        if sku_id not in existing
    ]
    if rows:
        db.table("sku_inventory_transactions").insert(rows).execute()
    yield
    # Only remove entries this session created; never touch SEED_DEV_COGS (setup_script)
    if rows:
        db.table("sku_inventory_transactions").delete() \
          .eq("reference", "SEED_DEV_COGS_PYTEST").execute()


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
    # Also clean up any sku_inventory_transactions with pytest references
    db.table("sku_inventory_transactions").delete().like("reference", "PYTEST_%").execute()
