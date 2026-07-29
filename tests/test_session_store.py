"""tcb/session_store.py — Supabase-backed portal session storage.

Requires setup/migrations/027_add_portal_sessions.sql applied to dev DB.
All tests hit dev DB only (TCB_ENV=dev set by conftest.py). Any existing
row for a portal is snapshotted and restored after each test so this
doesn't clobber a real saved session.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tcb.session_store import load_session, save_session

pytestmark = pytest.mark.integration


@pytest.fixture
def preserve_portal_session(db):
    """Snapshots a portal's existing row before a test touches it, restores after."""
    snapshots = {}

    def _track(portal):
        rows = db.table("portal_sessions").select("*").eq("portal", portal).execute().data
        snapshots[portal] = rows[0] if rows else None

    yield _track

    for portal, original in snapshots.items():
        if original is None:
            db.table("portal_sessions").delete().eq("portal", portal).execute()
        else:
            db.table("portal_sessions").upsert(original).execute()


class TestSessionStore:
    def test_save_then_load_round_trips(self, db, preserve_portal_session):
        preserve_portal_session("blinkit")
        state = {"cookies": [{"name": "sid", "value": "abc123"}], "origins": []}

        save_session("blinkit", state)
        loaded = load_session("blinkit")

        assert loaded == state

    def test_save_overwrites_previous_session(self, db, preserve_portal_session):
        preserve_portal_session("fc")

        save_session("fc", {"cookies": [{"name": "old", "value": "1"}], "origins": []})
        save_session("fc", {"cookies": [{"name": "new", "value": "2"}], "origins": []})

        loaded = load_session("fc")
        assert loaded["cookies"] == [{"name": "new", "value": "2"}]

    def test_load_returns_none_when_no_session_saved(self, db, preserve_portal_session):
        preserve_portal_session("fc")
        db.table("portal_sessions").delete().eq("portal", "fc").execute()
        assert load_session("fc") is None

    def test_load_rejects_unknown_portal(self):
        with pytest.raises(ValueError):
            load_session("amazon")

    def test_save_rejects_unknown_portal(self):
        with pytest.raises(ValueError):
            save_session("amazon", {"cookies": [], "origins": []})
