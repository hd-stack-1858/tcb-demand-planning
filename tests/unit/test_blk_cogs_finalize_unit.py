"""Unit tests for finalize_blk_cogs() logic — fully mocked, no DB/network.

Covers the #103 fixes in isolation:
  (a) pre-populated lot_id → COGS straight from that lot, consume_sor_sale never called;
  (b) NULL supply_state → consume_sor_sale(supply_state=None) tier-2 pool, never the
      customer `state` proxy;
  (c) order_ids scoping keeps the finalizer from sweeping unrelated orders.

Mocks get_client() with a fluent fake so no Supabase connection is made.
Run: python -m pytest tests/unit/test_blk_cogs_finalize_unit.py -q
"""
from unittest.mock import MagicMock

import pytest

import tcb.inventory as inv

pytestmark = pytest.mark.unit

BLK_ID = 4


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeBuilder:
    """Fluent no-op query builder; select-style execute() returns canned rows,
    update-style execute() records the payload."""

    def __init__(self, rows, on_update):
        self._rows = rows
        self._on_update = on_update
        self._payload = None

    def select(self, *cols):
        return self

    def update(self, payload):
        self._payload = payload
        return self

    def eq(self, *args):
        return self

    def in_(self, *args):
        return self

    def order(self, *args):
        return self

    def limit(self, *args):
        return self

    def single(self):
        return self

    def is_(self, *args):
        return self

    def gt(self, *args):
        return self

    def execute(self):
        if self._payload is not None:
            self._on_update(self._payload)
            self._payload = None
            return FakeResult([])
        return FakeResult(self._rows)


class FakeDB:
    def __init__(self, responses):
        self._responses = responses
        self.updates = []

    def table(self, name):
        return FakeBuilder(self._responses.get(name, []), self.updates.append)


def _finalize(monkeypatch, pending, lot_rows, order_ids=None, consume_result=(50.0, 123)):
    fake = FakeDB({
        "channels": [{"code": "BLK", "channel_id": BLK_ID}],
        "orders": pending,
        "sku_cogs_lots": lot_rows,
    })
    monkeypatch.setattr(inv, "get_client", lambda: fake)
    consume = MagicMock(return_value=consume_result)
    monkeypatch.setattr(inv, "consume_sor_sale", consume)
    result = inv.finalize_blk_cogs(order_ids=order_ids)
    return fake, consume, result


def test_prepopulated_lot_id_takes_cogs_and_skips_consumption(monkeypatch):
    """(a) lot_id on the order → COGS from that lot; consume_sor_sale NOT called."""
    order = {"order_id": "o1", "sku_id": "TCB001", "quantity": 2,
             "supply_state": None, "state": "Karnataka", "lot_id": 77}
    fake, consume, result = _finalize(monkeypatch, [order],
                                      [{"lot_id": 77, "unit_cogs": 250.0}])

    assert fake.updates == [
        {"cogs": 500.0, "lot_id": 77, "lot_cogs_finalized": True},
    ]
    consume.assert_not_called()
    assert result == {"total": 1, "finalized": 1, "fallback_used": 0, "no_cogs": 0}


def test_stale_lot_row_falls_through_to_consumption(monkeypatch):
    """lot_id set but its sku_cogs_lots row is gone → normal FIFO consumption."""
    order = {"order_id": "o1", "sku_id": "TCB001", "quantity": 2,
             "supply_state": "Haryana", "state": "Delhi", "lot_id": 999}
    fake, consume, result = _finalize(monkeypatch, [order], [])

    consume.assert_called_once_with(
        sku_id="TCB001", qty=2, channel_id=BLK_ID, supply_state="Haryana")
    assert fake.updates == [{"cogs": 100.0, "lot_id": 123, "lot_cogs_finalized": True}]
    assert result == {"total": 1, "finalized": 1, "fallback_used": 0, "no_cogs": 0}


def test_null_supply_state_passes_none_not_customer_state(monkeypatch):
    """(b) supply_state=None → tier-2 pool (supply_state=None). Customer state is
    never fed into tier-1 — the K1a cross-state drift."""
    order = {"order_id": "o1", "sku_id": "TCB001", "quantity": 2,
             "supply_state": None, "state": "Karnataka", "lot_id": None}
    fake, consume, result = _finalize(monkeypatch, [order], [])

    consume.assert_called_once_with(
        sku_id="TCB001", qty=2, channel_id=BLK_ID, supply_state=None)
    assert fake.updates == [{"cogs": 100.0, "lot_id": 123, "lot_cogs_finalized": True}]
    assert result["fallback_used"] == 1


def test_order_ids_scopes_sweep(monkeypatch):
    """order_ids limits processing to those orders only."""
    orders = [
        {"order_id": "o1", "sku_id": "TCB001", "quantity": 1,
         "supply_state": None, "state": "Karnataka", "lot_id": 77},
        {"order_id": "o2", "sku_id": "TCB002", "quantity": 1,
         "supply_state": None, "state": "Delhi", "lot_id": None},
    ]
    lot_rows = [{"lot_id": 77, "unit_cogs": 250.0}]
    fake, consume, result = _finalize(monkeypatch, orders, lot_rows, order_ids=["o1"])

    consume.assert_not_called()
    assert fake.updates == [{"cogs": 250.0, "lot_id": 77, "lot_cogs_finalized": True}]
    assert result["total"] == 1
    assert result["finalized"] == 1
