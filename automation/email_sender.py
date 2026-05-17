"""
SMTP email sender with PDF attachments.
Shared by FnP and First Cry automation.

Required .env vars:
  SMTP_SENDER      sending Gmail address (e.g. hd@thecradlebox.com)
  SMTP_PASSWORD    Gmail App Password for SMTP_SENDER
                   Generate at: https://myaccount.google.com/apppasswords
"""

from __future__ import annotations

import logging
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587


def send_with_attachments(
    subject: str,
    body: str,
    to_addrs: list[str],
    attachments: list[Path],
    dry_run: bool = False,
) -> None:
    """Send an email with one or more PDF attachments via Gmail SMTP."""
    sender   = os.environ.get("SMTP_SENDER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()

    if not sender or not password:
        raise EnvironmentError(
            "SMTP_SENDER and SMTP_PASSWORD must be set in .env\n"
            "Use a Gmail App Password: https://myaccount.google.com/apppasswords"
        )

    if dry_run:
        logger.info(
            "[dry-run] Would send '%s' to %s — %d attachment(s): %s",
            subject, to_addrs, len(attachments), [a.name for a in attachments],
        )
        return

    msg            = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    for path in attachments:
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
        msg.attach(part)

    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, to_addrs, msg.as_string())

    logger.info(
        "Email sent — to=%s | subject='%s' | attachments=%s",
        to_addrs, subject, [a.name for a in attachments],
    )


def send_alert(subject: str, body: str) -> None:
    """Send a plain-text failure alert to Himanshu (no attachments).

    Sends to EMAIL_HIMANSHU; also CC EMAIL_HIMANSHU_ALT if set (use personal Gmail
    as backup so alerts don't silently land in work-inbox spam).
    """
    himanshu = os.environ.get("EMAIL_HIMANSHU", "").strip()
    if not himanshu:
        logger.warning("EMAIL_HIMANSHU not set — cannot send alert email.")
        return
    alt = os.environ.get("EMAIL_HIMANSHU_ALT", "").strip()
    to_addrs = [himanshu] + ([alt] if alt and alt != himanshu else [])
    send_with_attachments(subject, body, to_addrs, attachments=[])
