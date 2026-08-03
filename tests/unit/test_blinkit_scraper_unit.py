"""Unit tests for automation/blinkit_scraper.py's session-store wiring.

Fully mocks Playwright, tcb.session_store, and the filesystem download
destination — no browser, no network, no real files written, no credentials.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import automation.blinkit_scraper as blinkit_scraper

pytestmark = pytest.mark.unit


def test_raises_before_launching_browser_when_no_session_saved(monkeypatch):
    monkeypatch.setattr("tcb.session_store.load_session", lambda portal: None)
    mock_playwright = MagicMock()
    monkeypatch.setattr(blinkit_scraper, "sync_playwright", mock_playwright)

    with pytest.raises(FileNotFoundError, match="No saved Blinkit session"):
        blinkit_scraper.scrape()

    mock_playwright.assert_not_called()


def test_passes_loaded_session_through_and_refreshes_on_success(monkeypatch, tmp_path):
    session_state = {"cookies": [{"name": "sid", "value": "loaded"}], "origins": []}
    refreshed_state = {"cookies": [{"name": "sid", "value": "refreshed"}], "origins": []}

    monkeypatch.setattr("tcb.session_store.load_session", lambda portal: session_state)
    mock_save_session = MagicMock()
    monkeypatch.setattr("tcb.session_store.save_session", mock_save_session)

    monkeypatch.setattr(blinkit_scraper, "DOWNLOAD_DIR", tmp_path)
    monkeypatch.setattr(blinkit_scraper, "_is_login_page", lambda page: False)
    monkeypatch.setattr(blinkit_scraper.time, "sleep", lambda *a, **k: None)

    p = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = p
    cm.__exit__.return_value = False
    monkeypatch.setattr(blinkit_scraper, "sync_playwright", MagicMock(return_value=cm))

    ctx = p.chromium.launch.return_value.new_context.return_value
    ctx.storage_state.return_value = refreshed_state
    page = ctx.new_page.return_value

    # Make the sidebar "Performance" click succeed on the first selector strategy.
    page.locator.return_value.first.wait_for.return_value = None

    # First selector-loop strategy (download-trigger check inside expect_download)
    # should find nothing so the code proceeds without extra clicks — .count()
    # truthy on a bare MagicMock would trigger a click, which is harmless here.
    download_mock = MagicMock()
    download_mock.failure.return_value = None
    download_mock.suggested_filename = "sales-report-test.xlsx"
    page.expect_download.return_value.__enter__.return_value.value = download_mock

    dest = blinkit_scraper.scrape()

    # storage_state loaded from the store was handed to new_context, not a local path
    _, new_context_kwargs = p.chromium.launch.return_value.new_context.call_args
    assert new_context_kwargs["storage_state"] == session_state

    # storage_state captured after the run was written back to the store
    mock_save_session.assert_called_once_with("blinkit", refreshed_state)

    assert dest == tmp_path / "sales-report-test.xlsx"
