"""
Stage 2 of the Slack-delivery spike: post a file to Slack from Docker.

Uses Slack's current upload flow (files.upload was deprecated):
  1. files.getUploadURLExternal — reserve an upload slot, get a URL + file_id
  2. POST the file bytes to that URL
  3. files.completeUploadExternal — finalizes and shares the file to a channel

Required env vars:
  SLACK_BOT_TOKEN     xoxb-... token, scopes: chat:write, files:write
  SLACK_CHANNEL_ID    channel to post to (bot must be invited to it)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

SLACK_API = "https://slack.com/api"


def upload_file(path: Path, token: str, channel_id: str, comment: str = "") -> None:
    headers = {"Authorization": f"Bearer {token}"}

    # Step 1: reserve an upload slot
    resp = requests.post(
        f"{SLACK_API}/files.getUploadURLExternal",
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
        f"{SLACK_API}/files.completeUploadExternal",
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

    print(f"Posted {path.name} to Slack channel {channel_id}")


def main() -> int:
    token = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    channel_id = os.environ.get("SLACK_CHANNEL_ID", "").strip()
    if not token or not channel_id:
        print("SLACK_BOT_TOKEN / SLACK_CHANNEL_ID not set.")
        return 1

    if len(sys.argv) != 2:
        print("Usage: python post_to_slack.py <path-to-file>")
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    upload_file(path, token, channel_id, comment="Stage 2 spike: local docker -> Slack")
    return 0


if __name__ == "__main__":
    sys.exit(main())
