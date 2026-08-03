"""
L1 repository tests — item↔supplier mapping and supplier CRUD (issue #68).

The repository takes an injectable client, so these tests drive it with a
fluent recording double (no Supabase, no network). They pin the postgrest
calls — table, filters, payloads, upsert conflict target — and the
preferred-supplier demotion invariant.

test-cmd: python -m pytest tests/test_procurement_repo.py -q
"""

import pytest

pytestmark = pytest.mark.unit

from tcb.procurement import ProcurementError
from tcb.procurement_repo import ProcurementRepo


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeBuilder:
    """Fluent postgrest double: records every call, returns canned rows.

    Each execute() pops the next row-set from FakeDB.responses[table], so a
    method that issues two queries (e.g. set_preferred) can be fed two
    responses.
    """

    def __init__(self, table, responses, calls):
        self._table = table
        self._responses = responses
        self._calls = calls
        self._filters = []

    def select(self, *cols):
        self._calls.append(("select", self._table, cols))
        return self

    def insert(self, payload):
        self._calls.append(("insert", self._table, payload))
        return self

    def update(self, payload):
        self._calls.append(("update", self._table, payload))
        return self

    def upsert(self, payload, on_conflict=None):
        self._calls.append(("upsert", self._table, payload, on_conflict))
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        self._calls.append(("eq", self._table, col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        self._calls.append(("neq", self._table, col, val))
        return self

    def order(self, *args, **kwargs):
        self._calls.append(("order", self._table, args))
        return self

    def limit(self, n):
        return self

    def single(self):
        return self

    def execute(self):
        self._calls.append(("execute", self._table, list(self._filters)))
        queue = self._responses.get(self._table, [])
        rows = queue.pop(0) if queue else []
        return FakeResult(rows)


class FakeDB:
    def __init__(self, responses):
        self.responses = responses  # dict[table] -> list[list[dict]] per execute
        self.calls = []

    def table(self, name):
        return FakeBuilder(name, self.responses, self.calls)


@pytest.fixture
def repo():
    return ProcurementRepo(client=FakeDB({}))


# ===========================================================================
# suppliers — list / get
# ===========================================================================

class TestListSuppliers:
    def test_active_only_filters_and_orders(self):
        fake = FakeDB({"suppliers": [[
            {"supplier_id": 1, "name": "A", "is_active": True},
        ]]})
        rows = ProcurementRepo(client=fake).list_suppliers(active_only=True)

        assert rows == [{"supplier_id": 1, "name": "A", "is_active": True}]
        filters = [c for c in fake.calls if c[0] == "eq"]
        assert ("eq", "suppliers", "is_active", True) in filters
        assert any(c[0] == "order" and c[1] == "suppliers" for c in fake.calls)

    def test_inactive_included_when_active_only_false(self):
        fake = FakeDB({"suppliers": [[]]})
        ProcurementRepo(client=fake).list_suppliers(active_only=False)

        eq_filters = [c for c in fake.calls if c[0] == "eq"]
        assert eq_filters == [], "no is_active filter should be issued"


class TestGetSupplier:
    def test_returns_row(self):
        fake = FakeDB({"suppliers": [[{"supplier_id": 3, "name": "S", "is_active": True}]]})
        row = ProcurementRepo(client=fake).get_supplier(3)

        assert row == {"supplier_id": 3, "name": "S", "is_active": True}
        eq_filters = [c[2:] for c in fake.calls if c[0] == "eq"]
        assert ("supplier_id", 3) in eq_filters

    def test_returns_none_when_missing(self):
        fake = FakeDB({"suppliers": [[]]})
        assert ProcurementRepo(client=fake).get_supplier(999) is None


# ===========================================================================
# suppliers — create / update / deactivate
# ===========================================================================

class TestCreateSupplier:
    def test_inserts_and_returns_id(self):
        fake = FakeDB({"suppliers": [[{"supplier_id": 7}]]})
        new_id = ProcurementRepo(client=fake).create_supplier({"name": "Vendor"})

        assert new_id == 7
        inserts = [c for c in fake.calls if c[0] == "insert"]
        assert inserts == [("insert", "suppliers", {"name": "Vendor"})]

    def test_validates_advance_terms_before_insert(self):
        fake = FakeDB({"suppliers": [[{"supplier_id": 1}]]})
        with pytest.raises(ProcurementError):
            ProcurementRepo(client=fake).create_supplier(
                {"name": "V", "advance_type": "half"})
        assert not [c for c in fake.calls if c[0] == "insert"], \
            "no insert should be issued for an invalid row"


class TestUpdateSupplier:
    def test_updates_by_id(self):
        fake = FakeDB({"suppliers": [[]]})
        ProcurementRepo(client=fake).update_supplier(4, {"lead_time_days": 10})

        updates = [c for c in fake.calls if c[0] == "update"]
        assert updates == [("update", "suppliers", {"lead_time_days": 10})]
        eq_filters = [c[2:] for c in fake.calls if c[0] == "eq"]
        assert ("supplier_id", 4) in eq_filters

    def test_deactivate_flips_is_active(self):
        fake = FakeDB({"suppliers": [[]]})
        ProcurementRepo(client=fake).deactivate_supplier(4)

        updates = [c for c in fake.calls if c[0] == "update"]
        assert updates == [("update", "suppliers", {"is_active": False})]
        eq_filters = [c[2:] for c in fake.calls if c[0] == "eq"]
        assert ("supplier_id", 4) in eq_filters


# ===========================================================================
# item_suppliers — lookup
# ===========================================================================

class TestListItemSuppliers:
    def test_lookup_by_item(self):
        fake = FakeDB({"item_suppliers": [[]]})
        ProcurementRepo(client=fake).list_item_suppliers(item_id=5)

        eq_filters = [c[2:] for c in fake.calls if c[0] == "eq"]
        assert ("item_id", 5) in eq_filters
        assert ("is_active", True) in eq_filters, "active_only defaults on"

    def test_lookup_by_supplier(self):
        fake = FakeDB({"item_suppliers": [[]]})
        ProcurementRepo(client=fake).list_item_suppliers(supplier_id=9)

        eq_filters = [c[2:] for c in fake.calls if c[0] == "eq"]
        assert ("supplier_id", 9) in eq_filters

    def test_lookup_by_item_and_supplier(self):
        fake = FakeDB({"item_suppliers": [[]]})
        ProcurementRepo(client=fake).list_item_suppliers(item_id=5, supplier_id=9)

        eq_filters = [c[2:] for c in fake.calls if c[0] == "eq"]
        assert ("item_id", 5) in eq_filters
        assert ("supplier_id", 9) in eq_filters

    def test_active_only_off_omits_filter(self):
        fake = FakeDB({"item_suppliers": [[]]})
        ProcurementRepo(client=fake).list_item_suppliers(item_id=5, active_only=False)

        eq_filters = [c[2:] for c in fake.calls if c[0] == "eq"]
        assert ("is_active", True) not in eq_filters

    def test_returns_rows(self):
        rows = [{"item_id": 1, "supplier_id": 2, "is_preferred": True, "is_active": True}]
        fake = FakeDB({"item_suppliers": [rows]})
        assert ProcurementRepo(client=fake).list_item_suppliers(item_id=1) == rows


class TestGetItemSupplier:
    def test_returns_pair_row(self):
        row = {"item_id": 1, "supplier_id": 2, "is_active": True}
        fake = FakeDB({"item_suppliers": [[row]]})
        got = ProcurementRepo(client=fake).get_item_supplier(1, 2)

        assert got == row
        eq_filters = [c[2:] for c in fake.calls if c[0] == "eq"]
        assert ("item_id", 1) in eq_filters
        assert ("supplier_id", 2) in eq_filters

    def test_returns_none_when_missing(self):
        fake = FakeDB({"item_suppliers": [[]]})
        assert ProcurementRepo(client=fake).get_item_supplier(1, 2) is None


# ===========================================================================
# item_suppliers — upsert / preferred / deactivate
# ===========================================================================

class TestUpsertItemSupplier:
    def test_upsert_uses_pair_conflict_target(self):
        row = {"item_id": 1, "supplier_id": 2, "cogs": 50.0}
        fake = FakeDB({"item_suppliers": [[{"item_supplier_id": 10}]]})
        upserted_id = ProcurementRepo(client=fake).upsert_item_supplier(row)

        assert upserted_id == 10
        upserts = [c for c in fake.calls if c[0] == "upsert"]
        assert len(upserts) == 1
        _, table, payload, on_conflict = upserts[0]
        assert table == "item_suppliers"
        assert payload == row
        assert on_conflict == "item_id,supplier_id"

    def test_preferred_upsert_demotes_other_pairs_first(self):
        row = {"item_id": 1, "supplier_id": 2, "is_preferred": True}
        fake = FakeDB({"item_suppliers": [[], [{"item_supplier_id": 10}]]})
        ProcurementRepo(client=fake).upsert_item_supplier(row)

        demotes = [c for c in fake.calls
                   if c[0] == "update" and c[1] == "item_suppliers"
                   and c[2] == {"is_preferred": False}]
        assert len(demotes) == 1, "preferred insert must demote existing preferred rows"
        # demote scoped to this item + preferred rows, excluding the pair itself
        demote_filters = [c for c in fake.calls
                          if c[0] == "eq" or c[0] == "neq"]
        assert ("eq", "item_suppliers", "item_id", 1) in demote_filters
        assert ("eq", "item_suppliers", "is_preferred", True) in demote_filters
        assert ("neq", "item_suppliers", "supplier_id", 2) in demote_filters

    def test_non_preferred_upsert_skips_demotion(self):
        row = {"item_id": 1, "supplier_id": 2, "is_preferred": False}
        fake = FakeDB({"item_suppliers": [[{"item_supplier_id": 10}]]})
        ProcurementRepo(client=fake).upsert_item_supplier(row)

        updates = [c for c in fake.calls if c[0] == "update"]
        assert updates == [], "no demotion should run for a non-preferred upsert"

    def test_validates_row_before_writing(self):
        fake = FakeDB({"item_suppliers": [[{"item_supplier_id": 1}]]})
        with pytest.raises(ProcurementError):
            ProcurementRepo(client=fake).upsert_item_supplier(
                {"item_id": 1, "supplier_id": 2, "moq": 0})
        assert not fake.calls, "no DB call should be issued for an invalid row"


class TestSetPreferred:
    def test_demotes_all_preferred_rows_for_item_then_promotes(self):
        fake = FakeDB({"item_suppliers": [[], []]})
        ProcurementRepo(client=fake).set_preferred(1, 2)

        demote = [c for c in fake.calls
                  if c[0] == "update" and c[1] == "item_suppliers"
                  and c[2] == {"is_preferred": False}]
        assert len(demote) == 1
        # demotion must hit ALL preferred rows for the item — never a single supplier
        demote_exec = [c for c in fake.calls
                       if c[0] == "execute" and c[1] == "item_suppliers"
                       and ("eq", "is_preferred", True) in c[2]]
        assert demote_exec, "demotion must filter is_preferred=True"
        assert not any(kind == "neq" for kind, *_ in fake.calls), \
            "set_preferred demotion must not exclude any supplier row"

        promote = [c for c in fake.calls
                   if c[0] == "update" and c[1] == "item_suppliers"
                   and c[2] == {"is_preferred": True}]
        assert len(promote) == 1
        promote_filters = [c[2:] for c in fake.calls
                           if (c[0] == "eq" and c[1] == "item_suppliers")]
        assert ("item_id", 1) in promote_filters
        assert ("supplier_id", 2) in promote_filters


class TestDeactivateItemSupplier:
    def test_flips_is_active_for_pair(self):
        fake = FakeDB({"item_suppliers": [[]]})
        ProcurementRepo(client=fake).deactivate_item_supplier(1, 2)

        updates = [c for c in fake.calls if c[0] == "update"]
        assert updates == [("update", "item_suppliers", {"is_active": False})]
        eq_filters = [c[2:] for c in fake.calls if c[0] == "eq"]
        assert ("item_id", 1) in eq_filters
        assert ("supplier_id", 2) in eq_filters
