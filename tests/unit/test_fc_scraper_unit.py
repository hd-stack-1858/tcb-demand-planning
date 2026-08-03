"""Unit tests for automation/fc_scraper.py's session-store wiring.

fc_scraper.py never writes the session back (matches its pre-existing
behavior — it never wrote to disk either), so unlike the Blinkit scrapers
there's no write-back to verify. Its run() function is a large, real
order-processing pipeline (accepts pending orders on the live FC portal),
so rather than simulate the whole thing, this captures the new_context
call args and aborts immediately after via a sentinel exception raised by
the very next call (ctx.new_page()) — same technique, far less mocking.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import automation.fc_scraper as fc_scraper

pytestmark = pytest.mark.unit


def test_raises_before_launching_browser_when_no_session_saved(monkeypatch):
    monkeypatch.setattr("tcb.session_store.load_session", lambda portal: None)
    mock_playwright = MagicMock()
    monkeypatch.setattr(fc_scraper, "sync_playwright", mock_playwright)

    with pytest.raises(FileNotFoundError, match="No saved FirstCry session"):
        fc_scraper.run()

    mock_playwright.assert_not_called()


def test_passes_loaded_session_through_to_new_context(monkeypatch):
    session_state = {"cookies": [{"name": "sid", "value": "loaded"}], "origins": []}
    monkeypatch.setattr("tcb.session_store.load_session", lambda portal: session_state)

    p = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = p
    cm.__exit__.return_value = False
    monkeypatch.setattr(fc_scraper, "sync_playwright", MagicMock(return_value=cm))

    ctx = p.chromium.launch.return_value.new_context.return_value
    ctx.new_page.side_effect = RuntimeError("stop-here-sentinel")

    with pytest.raises(RuntimeError, match="stop-here-sentinel"):
        fc_scraper.run()

    _, new_context_kwargs = p.chromium.launch.return_value.new_context.call_args
    assert new_context_kwargs["storage_state"] == session_state
