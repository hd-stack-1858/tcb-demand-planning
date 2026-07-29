"""Unit test for automation/blinkit_auth.py's session-save wiring.

Fully mocks Playwright (no browser launched, no network) and tcb.session_store,
so this runs anywhere with no credentials. Verifies the one thing this module
is responsible for post-migration: the captured storage_state is handed to
save_session("blinkit", ...) instead of written to local disk.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import automation.blinkit_auth as blinkit_auth

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_playwright(monkeypatch):
    """Patches sync_playwright to a context manager yielding a fully-mocked `p`."""
    p = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = p
    cm.__exit__.return_value = False
    monkeypatch.setattr(blinkit_auth, "sync_playwright", MagicMock(return_value=cm))
    monkeypatch.setattr(blinkit_auth.time, "sleep", lambda *a, **k: None)
    return p


def test_saves_captured_storage_state_to_session_store(monkeypatch, mock_playwright):
    monkeypatch.setenv("BLINKIT_USERNAME", "9999999999")
    expected_state = {"cookies": [{"name": "sid", "value": "captured"}], "origins": []}
    mock_playwright.chromium.launch.return_value.new_context.return_value.storage_state.return_value = expected_state

    mock_save_session = MagicMock()
    monkeypatch.setattr(blinkit_auth, "save_session", mock_save_session)

    blinkit_auth.run()

    mock_save_session.assert_called_once_with("blinkit", expected_state)


def test_exits_without_launching_browser_if_username_missing(monkeypatch, mock_playwright):
    monkeypatch.delenv("BLINKIT_USERNAME", raising=False)

    with pytest.raises(SystemExit):
        blinkit_auth.run()

    mock_playwright.chromium.launch.assert_not_called()
