"""Unit tests for automation/blinkit_performance_scraper.py's session-store
wiring. Mirrors test_blinkit_scraper_unit.py's depth — full read-session ->
scrape -> write-back-session flow, fully mocked."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import automation.blinkit_performance_scraper as perf_scraper

pytestmark = pytest.mark.unit


def test_raises_before_launching_browser_when_no_session_saved(monkeypatch):
    monkeypatch.setattr("tcb.session_store.load_session", lambda portal: None)
    mock_playwright = MagicMock()
    monkeypatch.setattr(perf_scraper, "sync_playwright", mock_playwright)

    with pytest.raises(FileNotFoundError, match="No saved Blinkit session"):
        perf_scraper.scrape()

    mock_playwright.assert_not_called()


def test_passes_loaded_session_through_and_refreshes_on_success(monkeypatch, tmp_path):
    session_state = {"cookies": [{"name": "sid", "value": "loaded"}], "origins": []}
    refreshed_state = {"cookies": [{"name": "sid", "value": "refreshed"}], "origins": []}

    monkeypatch.setattr("tcb.session_store.load_session", lambda portal: session_state)
    mock_save_session = MagicMock()
    monkeypatch.setattr("tcb.session_store.save_session", mock_save_session)

    monkeypatch.setattr(perf_scraper, "DOWNLOAD_DIR", tmp_path)
    monkeypatch.setattr(perf_scraper, "_is_login_page", lambda page: False)
    monkeypatch.setattr(perf_scraper.time, "sleep", lambda *a, **k: None)

    p = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = p
    cm.__exit__.return_value = False
    monkeypatch.setattr(perf_scraper, "sync_playwright", MagicMock(return_value=cm))

    ctx = p.chromium.launch.return_value.new_context.return_value
    ctx.storage_state.return_value = refreshed_state
    page = ctx.new_page.return_value
    page.locator.return_value.first.wait_for.return_value = None
    page.get_by_text.return_value.first.wait_for.return_value = None

    download_mock = MagicMock()
    download_mock.failure.return_value = None
    download_mock.suggested_filename = "performance-detail-test.csv"
    page.expect_download.return_value.__enter__.return_value.value = download_mock

    dest = perf_scraper.scrape()

    _, new_context_kwargs = p.chromium.launch.return_value.new_context.call_args
    assert new_context_kwargs["storage_state"] == session_state

    mock_save_session.assert_called_once_with("blinkit", refreshed_state)

    assert dest.parent == tmp_path
