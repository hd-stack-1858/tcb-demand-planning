"""
Slack file/message sender via the Slack Web API. Mirrors email_sender.py's
shape (send_with_attachments / send_alert) so callers can treat Slack as a
second, parallel delivery channel alongside email.

Uses Slack's current upload flow (the old files.upload endpoint is
deprecated): files.getUploadURLExternal -> upload bytes -> files.completeUploadExternal.
No SMTP involved — this is a separate mechanism from email_sender.py.

Required .env vars:
  SLACK_BOT_TOKEN     xoxb-... bot token, scopes: chat:write, files:write
  SLACK_CHANNEL_ID    channel to post to (bot must be invited to it)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

_SLACK_API = "https://slack.com/api"


def _get_credentials() -> tuple[str, str]:
    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    channel_id = os.environ.get("SLACK_CHANNEL_ID", "").strip()
    if not token or not channel_id:
        raise EnvironmentError(
            "SLACK_BOT_TOKEN and SLACK_CHANNEL_ID must be set in .env\n"
            "Create a Slack app at api.slack.com/apps with chat:write + "
            "files:write scopes, install it, and invite the bot to the channel."
        )
    return token, channel_id


def send_with_attachments(
    comment: str,
    attachments: list[Path],
    dry_run: bool = False,
) -> None:
    """Post a comment with one or more file attachments to the configured channel.

    Note: Slack's upload API has no batch-complete endpoint, so each file in
    `attachments` is posted as its own separate message carrying the same
    `comment` text — not one message with N files attached. Only single-file
    callers exist today (run_blinkit_report.py); multi-file callers should be
    aware the channel will show N messages, not one.
    """
    token, channel_id = _get_credentials()

    if dry_run:
        logger.info(
            "[dry-run] Would post to Slack channel %s — comment=%r, attachments=%s",
            channel_id, comment, [a.name for a in attachments],
        )
        return

    headers = {"Authorization": f"Bearer {token}"}

    if not attachments:
        resp = requests.post(
            f"{_SLACK_API}/chat.postMessage",
            headers=headers,
            json={"channel": channel_id, "text": comment},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise RuntimeError(f"chat.postMessage failed: {result}")
        logger.info("Slack message sent — channel=%s", channel_id)
        return

    for path in attachments:
        _upload_file(path, token, channel_id, comment)

    logger.info(
        "Slack post sent — channel=%s | attachments=%s",
        channel_id, [a.name for a in attachments],
    )


def _upload_file(path: Path, token: str, channel_id: str, comment: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}

    # Step 1: reserve an upload slot
    resp = requests.post(
        f"{_SLACK_API}/files.getUploadURLExternal",
        headers=headers,
        data={"filename": path.name, "length": path.stat().st_size},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"getUploadURLExternal failed: {data}")
    upload_url = data["upload_url"]
    file_id = data["file_id"]

    # Step 2: upload the raw bytes
    with open(path, "rb") as f:
        upload_resp = requests.post(upload_url, files={"file": f}, timeout=60)
    upload_resp.raise_for_status()

    # Step 3: complete the upload and share to the channel
    complete_resp = requests.post(
        f"{_SLACK_API}/files.completeUploadExternal",
        headers={**headers, "Content-Type": "application/json; charset=utf-8"},
        json={
            "files": [{"id": file_id, "title": path.name}],
            "channel_id": channel_id,
            "initial_comment": comment,
        },
        timeout=30,
    )
    complete_resp.raise_for_status()
    result = complete_resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"completeUploadExternal failed: {result}")


def send_alert(subject: str, body: str) -> None:
    """Post a plain-text failure alert to the configured channel (no attachments)."""
    try:
        send_with_attachments(f"*{subject}*\n{body}", attachments=[])
    except EnvironmentError:
        logger.warning("SLACK_BOT_TOKEN/SLACK_CHANNEL_ID not set — cannot send Slack alert.")
