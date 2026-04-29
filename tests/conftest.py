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


@pytest.fixture(scope="session")
def db():
    return get_client()


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
