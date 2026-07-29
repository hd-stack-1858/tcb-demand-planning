"""
tests/integration_mocked/ — cross-module integration tests where only the
true external boundary (the Supabase network client) is faked. Unlike
tests/unit/, these do NOT mock tcb.session_store's own functions — they
exercise the real save_session()/load_session() code, and the real
automation/*.py callers, against an in-memory fake standing in for
Supabase's REST client. This catches integration bugs a pure unit test
(which mocks session_store directly) would miss, e.g. a caller passing the
wrong shape of data through session_store into "Supabase".

Same as tests/unit/: overrides the root conftest.py's autouse
`seed_dev_cogs` fixture, which otherwise forces a real dev DB connection.
This subtree must also run with zero credentials.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def seed_dev_cogs():
    yield


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Stands in for postgrest-py's chainable query builder, backed by an
    in-memory dict keyed by `portal` — enough of the real chain
    (select/eq/upsert/execute) for tcb/session_store.py's actual usage."""

    def __init__(self, rows: dict):
        self._rows = rows
        self._method = None
        self._eq_filters: dict = {}
        self._payload = None

    def select(self, *_cols):
        self._method = "select"
        return self

    def eq(self, col, val):
        self._eq_filters[col] = val
        return self

    def upsert(self, row: dict):
        self._method = "upsert"
        self._payload = dict(row)
        return self

    def delete(self):
        self._method = "delete"
        return self

    def execute(self):
        if self._method == "select":
            matches = [
                r for r in self._rows.values()
                if all(r.get(k) == v for k, v in self._eq_filters.items())
            ]
            return _FakeResult(matches)
        if self._method == "upsert":
            pk = self._payload.get("portal")
            self._rows[pk] = self._payload
            return _FakeResult([self._payload])
        if self._method == "delete":
            for pk in [k for k, r in self._rows.items()
                       if all(r.get(c) == v for c, v in self._eq_filters.items())]:
                del self._rows[pk]
            return _FakeResult([])
        raise RuntimeError("FakeQuery.execute() called before select/upsert/delete")


class FakeSupabaseClient:
    """Persists state across .table() calls within one instance — so a
    save_session() followed by a load_session() through the SAME fake
    client genuinely round-trips, the way real Supabase would."""

    def __init__(self):
        self._tables: dict[str, dict] = {}

    def table(self, name: str) -> _FakeQuery:
        self._tables.setdefault(name, {})
        return _FakeQuery(self._tables[name])


@pytest.fixture
def fake_supabase(monkeypatch):
    """Patches tcb.session_store.get_client so real session_store code
    (and anything that calls into it) talks to an in-memory fake instead
    of real Supabase."""
    client = FakeSupabaseClient()
    monkeypatch.setattr("tcb.session_store.get_client", lambda: client)
    return client
