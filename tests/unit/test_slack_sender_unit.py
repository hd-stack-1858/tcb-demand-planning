"""Unit tests for automation/slack_sender.py — fully mocks requests.post,
no real network calls, no Slack credentials needed."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import automation.slack_sender as slack_sender

pytestmark = pytest.mark.unit


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C123456")


def _ok_response(json_data):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = json_data
    return resp


class TestCredentialGuard:
    def test_raises_when_token_missing(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        monkeypatch.setenv("SLACK_CHANNEL_ID", "C123456")
        with pytest.raises(EnvironmentError):
            slack_sender.send_with_attachments("hi", attachments=[])

    def test_raises_when_channel_missing(self, monkeypatch):
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
        monkeypatch.delenv("SLACK_CHANNEL_ID", raising=False)
        with pytest.raises(EnvironmentError):
            slack_sender.send_with_attachments("hi", attachments=[])


class TestDryRun:
    def test_dry_run_does_not_call_requests(self, creds, monkeypatch):
        mock_post = MagicMock()
        monkeypatch.setattr(slack_sender.requests, "post", mock_post)

        slack_sender.send_with_attachments("hi", attachments=[], dry_run=True)

        mock_post.assert_not_called()


class TestPlainMessage:
    def test_posts_chat_message_when_no_attachments(self, creds, monkeypatch):
        mock_post = MagicMock(return_value=_ok_response({"ok": True}))
        monkeypatch.setattr(slack_sender.requests, "post", mock_post)

        slack_sender.send_with_attachments("hello channel", attachments=[])

        mock_post.assert_called_once()
        url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
        assert url.endswith("chat.postMessage")
        assert kwargs["json"] == {"channel": "C123456", "text": "hello channel"}

    def test_raises_if_slack_returns_not_ok(self, creds, monkeypatch):
        mock_post = MagicMock(return_value=_ok_response({"ok": False, "error": "invalid_auth"}))
        monkeypatch.setattr(slack_sender.requests, "post", mock_post)

        with pytest.raises(RuntimeError, match="chat.postMessage failed"):
            slack_sender.send_with_attachments("hello", attachments=[])


class TestFileUpload:
    def test_uploads_via_three_step_flow(self, creds, monkeypatch, tmp_path):
        report = tmp_path / "report.xlsx"
        report.write_bytes(b"fake xlsx content")

        get_url_resp = _ok_response({
            "ok": True, "upload_url": "https://files.slack.com/upload/xyz", "file_id": "F123",
        })
        raw_upload_resp = MagicMock()
        raw_upload_resp.raise_for_status.return_value = None
        complete_resp = _ok_response({"ok": True})

        mock_post = MagicMock(side_effect=[get_url_resp, raw_upload_resp, complete_resp])
        monkeypatch.setattr(slack_sender.requests, "post", mock_post)

        slack_sender.send_with_attachments("here's the report", attachments=[report])

        assert mock_post.call_count == 3
        step1_url = mock_post.call_args_list[0][0][0]
        step2_url = mock_post.call_args_list[1][0][0]
        step3_url = mock_post.call_args_list[2][0][0]
        assert step1_url.endswith("files.getUploadURLExternal")
        assert step2_url == "https://files.slack.com/upload/xyz"
        assert step3_url.endswith("files.completeUploadExternal")

        complete_kwargs = mock_post.call_args_list[2][1]
        assert complete_kwargs["json"]["channel_id"] == "C123456"
        assert complete_kwargs["json"]["files"] == [{"id": "F123", "title": "report.xlsx"}]
        assert complete_kwargs["json"]["initial_comment"] == "here's the report"

    def test_raises_if_upload_url_step_fails(self, creds, monkeypatch, tmp_path):
        report = tmp_path / "report.xlsx"
        report.write_bytes(b"x")
        mock_post = MagicMock(return_value=_ok_response({"ok": False, "error": "boom"}))
        monkeypatch.setattr(slack_sender.requests, "post", mock_post)

        with pytest.raises(RuntimeError, match="getUploadURLExternal failed"):
            slack_sender.send_with_attachments("comment", attachments=[report])


class TestSendAlert:
    def test_formats_subject_and_body_into_message(self, creds, monkeypatch):
        mock_send = MagicMock()
        monkeypatch.setattr(slack_sender, "send_with_attachments", mock_send)

        slack_sender.send_alert("Scraper Failed", "Detail: timeout")

        mock_send.assert_called_once_with(
            "*Scraper Failed*\nDetail: timeout", attachments=[],
        )

    def test_swallows_missing_credentials_instead_of_raising(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        monkeypatch.delenv("SLACK_CHANNEL_ID", raising=False)

        slack_sender.send_alert("subject", "body")  # must not raise
