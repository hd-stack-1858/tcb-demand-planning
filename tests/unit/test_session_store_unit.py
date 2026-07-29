"""Pure-logic unit tests for tcb/session_store.py — no DB, no network.

Mocks tcb.session_store.get_client entirely, so these run anywhere
(local, CI, sandbox) with no credentials at all.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import tcb.session_store as session_store

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_db(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(session_store, "get_client", lambda: db)
    return db


class TestLoadSession:
    def test_returns_state_json_when_row_exists(self, mock_db):
        expected_state = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"state_json": expected_state}
        ]

        result = session_store.load_session("blinkit")

        assert result == expected_state
        mock_db.table.assert_called_with("portal_sessions")

    def test_returns_none_when_no_row(self, mock_db):
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []

        assert session_store.load_session("fc") is None

    def test_rejects_unknown_portal_before_touching_db(self, mock_db):
        with pytest.raises(ValueError):
            session_store.load_session("amazon")
        mock_db.table.assert_not_called()


class TestSaveSession:
    def test_upserts_with_portal_and_state(self, mock_db):
        state = {"cookies": [{"name": "sid", "value": "xyz"}], "origins": []}

        session_store.save_session("blinkit", state)

        mock_db.table.assert_called_with("portal_sessions")
        upsert_call = mock_db.table.return_value.upsert
        upsert_call.assert_called_once()
        payload = upsert_call.call_args[0][0]
        assert payload["portal"] == "blinkit"
        assert payload["state_json"] == state
        assert "updated_at" in payload

    def test_rejects_unknown_portal_before_touching_db(self, mock_db):
        with pytest.raises(ValueError):
            session_store.save_session("amazon", {"cookies": [], "origins": []})
        mock_db.table.assert_not_called()
