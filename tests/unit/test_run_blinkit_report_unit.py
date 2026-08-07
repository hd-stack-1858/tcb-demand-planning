"""Unit tests for automation/run_blinkit_report.py — mocks scrape() and
send_with_attachments() entirely, no browser, no network, no Slack."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import automation.run_blinkit_report as run_mod
from automation.blinkit_scraper import BlinkitSessionExpired

pytestmark = pytest.mark.unit


def test_posts_report_to_slack_on_success(monkeypatch, tmp_path):
    xlsx_path = tmp_path / "sales_summary.xlsx"
    xlsx_path.write_bytes(b"fake")
    monkeypatch.setattr(run_mod, "scrape", lambda dry_run, headed: xlsx_path)
    mock_send = MagicMock()
    monkeypatch.setattr(run_mod, "send_with_attachments", mock_send)
    monkeypatch.setattr(sys, "argv", ["run_blinkit_report.py", "--dry-run"])

    assert run_mod.main() == 0

    mock_send.assert_called_once()
    comment, attachments = mock_send.call_args[0]
    assert "Blinkit MTD sales report" in comment
    assert attachments == [xlsx_path]


def test_posts_alert_and_returns_2_on_session_expired(monkeypatch):
    def raise_expired(dry_run, headed):
        raise BlinkitSessionExpired("session dead")

    monkeypatch.setattr(run_mod, "scrape", raise_expired)
    mock_send = MagicMock()
    monkeypatch.setattr(run_mod, "send_with_attachments", mock_send)
    monkeypatch.setattr(sys, "argv", ["run_blinkit_report.py"])

    assert run_mod.main() == 2

    mock_send.assert_called_once_with(
        "*Blinkit report failed — session expired*\nsession dead", attachments=[],
    )


def test_posts_alert_and_returns_1_on_unexpected_error(monkeypatch):
    def raise_error(dry_run, headed):
        raise RuntimeError("portal changed layout")

    monkeypatch.setattr(run_mod, "scrape", raise_error)
    mock_send = MagicMock()
    monkeypatch.setattr(run_mod, "send_with_attachments", mock_send)
    monkeypatch.setattr(sys, "argv", ["run_blinkit_report.py"])

    assert run_mod.main() == 1

    mock_send.assert_called_once_with(
        "*Blinkit report failed*\nportal changed layout", attachments=[],
    )
