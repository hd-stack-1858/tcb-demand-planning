"""Unit test for automation/fc_auth.py's session-save wiring.

Fully mocks Playwright and tcb.session_store — no browser, no network, no
credentials required. fc_auth.py always prompts for the reCAPTCHA step via
input(), so that's stubbed too.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import automation.fc_auth as fc_auth

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_playwright(monkeypatch):
    p = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = p
    cm.__exit__.return_value = False
    monkeypatch.setattr(fc_auth, "sync_playwright", MagicMock(return_value=cm))
    monkeypatch.setattr(fc_auth.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")
    return p


def test_saves_captured_storage_state_to_session_store(monkeypatch, mock_playwright):
    monkeypatch.setenv("FC_USERNAME", "vendor@example.com")
    monkeypatch.setenv("FC_PASSWORD", "secret")
    expected_state = {"cookies": [{"name": "sid", "value": "captured"}], "origins": []}
    mock_playwright.chromium.launch.return_value.new_context.return_value.storage_state.return_value = expected_state

    mock_save_session = MagicMock()
    monkeypatch.setattr(fc_auth, "save_session", mock_save_session)

    fc_auth.run()

    mock_save_session.assert_called_once_with("fc", expected_state)


def test_exits_without_launching_browser_if_credentials_missing(monkeypatch, mock_playwright):
    monkeypatch.delenv("FC_USERNAME", raising=False)
    monkeypatch.delenv("FC_PASSWORD", raising=False)

    with pytest.raises(SystemExit):
        fc_auth.run()

    mock_playwright.chromium.launch.assert_not_called()
