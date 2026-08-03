"""Unit tests for automation/sync_local_sessions_to_store.py.

Fully mocks tcb.session_store — no DB, no network, no real files under the
actual .blinkit_session/.fc_session paths. Local session files are faked via
tmp_path and monkeypatching the module's _LOCAL_SESSION_FILES dict.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import automation.sync_local_sessions_to_store as sync_mod

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_store(monkeypatch):
    save_session = MagicMock()
    monkeypatch.setattr(sync_mod, "save_session", save_session)
    return save_session


def test_sync_portal_skips_when_file_missing(tmp_path, monkeypatch, mock_store):
    monkeypatch.setitem(sync_mod._LOCAL_SESSION_FILES, "blinkit", tmp_path / "missing.json")

    result = sync_mod.sync_portal("blinkit")

    assert result is False
    mock_store.assert_not_called()


def test_sync_portal_saves_and_verifies_when_file_present(tmp_path, monkeypatch, mock_store):
    state = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}
    session_file = tmp_path / "state.json"
    session_file.write_text(json.dumps(state))
    monkeypatch.setitem(sync_mod._LOCAL_SESSION_FILES, "blinkit", session_file)
    monkeypatch.setattr(sync_mod, "load_session", lambda portal: state)

    result = sync_mod.sync_portal("blinkit")

    assert result is True
    mock_store.assert_called_once_with("blinkit", state)


def test_sync_portal_reports_mismatch_if_roundtrip_differs(tmp_path, monkeypatch, mock_store):
    state = {"cookies": [{"name": "sid", "value": "abc"}], "origins": []}
    session_file = tmp_path / "state.json"
    session_file.write_text(json.dumps(state))
    monkeypatch.setitem(sync_mod._LOCAL_SESSION_FILES, "blinkit", session_file)
    # Simulate a store that returns something different from what was saved
    monkeypatch.setattr(sync_mod, "load_session", lambda portal: {"cookies": [], "origins": []})

    result = sync_mod.sync_portal("blinkit")

    assert result is False
    mock_store.assert_called_once_with("blinkit", state)


def test_main_returns_1_when_nothing_synced(tmp_path, monkeypatch, mock_store):
    monkeypatch.setitem(sync_mod._LOCAL_SESSION_FILES, "blinkit", tmp_path / "missing1.json")
    monkeypatch.setitem(sync_mod._LOCAL_SESSION_FILES, "fc", tmp_path / "missing2.json")
    monkeypatch.setattr(sys, "argv", ["sync_local_sessions_to_store.py"])

    assert sync_mod.main() == 1


def test_main_returns_0_when_at_least_one_synced(tmp_path, monkeypatch, mock_store):
    state = {"cookies": [], "origins": []}
    session_file = tmp_path / "state.json"
    session_file.write_text(json.dumps(state))
    monkeypatch.setitem(sync_mod._LOCAL_SESSION_FILES, "blinkit", session_file)
    monkeypatch.setitem(sync_mod._LOCAL_SESSION_FILES, "fc", tmp_path / "missing.json")
    monkeypatch.setattr(sync_mod, "load_session", lambda portal: state)
    monkeypatch.setattr(sys, "argv", ["sync_local_sessions_to_store.py"])

    assert sync_mod.main() == 0


def test_main_respects_portal_flag(tmp_path, monkeypatch, mock_store):
    state = {"cookies": [], "origins": []}
    blinkit_file = tmp_path / "blinkit_state.json"
    blinkit_file.write_text(json.dumps(state))
    fc_file = tmp_path / "fc_state.json"
    fc_file.write_text(json.dumps(state))
    monkeypatch.setitem(sync_mod._LOCAL_SESSION_FILES, "blinkit", blinkit_file)
    monkeypatch.setitem(sync_mod._LOCAL_SESSION_FILES, "fc", fc_file)
    monkeypatch.setattr(sync_mod, "load_session", lambda portal: state)
    monkeypatch.setattr(sys, "argv", ["sync_local_sessions_to_store.py", "--portal", "fc"])

    assert sync_mod.main() == 0
    mock_store.assert_called_once_with("fc", state)
