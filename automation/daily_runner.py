"""
Daily automation runner — runs at 12:00 noon IST via Windows Task Scheduler.

Sequence:
  12:00  → G1: Amazon SP-API (orders + finances)
  12:00  → G2: Blinkit scraper (parallel with Amazon)
  12:15  → G3: WhatsApp briefing (after both complete)

Exit codes:
  0  — success
  1  — partial failure (one source failed, briefing sent with partial data)
  2  — both sources failed (briefing still sent with failure notice)

WINDOWS TASK SCHEDULER SETUP:
  1. Open Task Scheduler → Create Basic Task
  2. Name: "Vignesh Daily Runner"
  3. Trigger: Daily at 12:00 PM (noon IST — adjust if your machine is in a different timezone)
  4. Action: Start a program
     Program: C:\\path\\to\\python.exe
     Arguments: C:\\01Claude\\projects\\DemandPlanning\\automation\\daily_runner.py
     Start in: C:\\01Claude\\projects\\DemandPlanning
  5. Conditions: uncheck "Start only if computer is on AC power" (if on laptop)
  6. Settings: check "Run task as soon as possible after a scheduled start is missed"

Logs are written to: automation/logs/daily_runner_YYYYMMDD.log
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"daily_runner_{date.today().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(str(log_file), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

PYTHON = sys.executable
PROJECT = Path(__file__).parent.parent


def _run_amazon() -> dict:
    """Run Amazon SP-API orders pull (MTD status refresh). Returns result dict."""
    logger.info("Amazon SP-API: pulling orders...")
    proc = subprocess.run(
        [PYTHON, str(PROJECT / "automation" / "amazon_sp_api.py"), "orders",
         "--env", "prod"],
        capture_output=True, text=True, cwd=str(PROJECT),
    )
    if proc.returncode == 0:
        logger.info("Amazon orders: OK")
        return {"orders": "ok"}
    else:
        logger.error("Amazon orders failed (exit %d):\n%s", proc.returncode, proc.stderr)
        return {"orders": f"error (exit {proc.returncode})"}


def _run_blinkit() -> dict:
    """Run Blinkit scraper. Returns result dict."""
    from automation.blinkit_scraper import BlinkitSessionExpired

    logger.info("Blinkit scraper: starting...")
    proc = subprocess.run(
        [PYTHON, str(PROJECT / "automation" / "blinkit_scraper.py")],
        capture_output=True, text=True, cwd=str(PROJECT),
        env={**os.environ, "TCB_ENV": "prod"},
    )

    if proc.returncode == 0:
        logger.info("Blinkit scraper: OK — %s", proc.stdout.strip())
        return {"status": "ok", "output": proc.stdout.strip()}
    elif proc.returncode == 2:
        # Session expired
        logger.warning("Blinkit session expired — WhatsApp alert will be sent.")
        return {"status": "session_expired"}
    else:
        logger.error("Blinkit scraper failed (exit %d):\n%s", proc.returncode, proc.stderr)
        return {"status": "error", "exit_code": proc.returncode, "stderr": proc.stderr}


def _send_whatsapp(amazon_result: dict, blinkit_result: dict, dry_run: bool) -> None:
    """Send daily WhatsApp briefing. Includes failure notices if sources failed."""
    from automation.daily_summary import build_summary, send_summary
    from automation.whatsapp import send_daily_brief

    failures = []

    amazon_ok = all(v == "ok" for v in amazon_result.values())
    if not amazon_ok:
        failures.append(f"Amazon pull failed: {amazon_result}")

    blinkit_status = blinkit_result.get("status")
    if blinkit_status == "session_expired":
        failures.append("Blinkit session expired — run: python automation/blinkit_auth.py")
    elif blinkit_status != "ok":
        failures.append(f"Blinkit scraper failed: {blinkit_result.get('stderr', '')[:200]}")

    # Build the sales summary message
    try:
        message = build_summary()
    except Exception as exc:
        logger.error("Could not build sales summary: %s", exc)
        message = ""

    # Append failure notices if any
    if failures:
        notice = "\n\nDATA ISSUES:\n" + "\n".join(f"• {f}" for f in failures)
        if message:
            message += notice
        else:
            today = date.today()
            message = f"{today.strftime('%d-%b %a')} — no sales data (ingestion failed){notice}"

    if not message:
        logger.info("Nothing to send.")
        return

    try:
        send_daily_brief(message, dry_run=dry_run)
        logger.info("WhatsApp sent%s.", " (dry-run)" if dry_run else "")
    except EnvironmentError as exc:
        # requests.HTTPError inherits IOError→OSError→EnvironmentError in Python 3;
        # check isinstance so API errors aren't silently logged as "not configured".
        import requests as _req
        if isinstance(exc, _req.exceptions.HTTPError):
            logger.error("WhatsApp API error (already logged above): %s", exc)
        else:
            logger.warning("WhatsApp not configured — skipping send.\n%s", exc)
    except Exception as exc:
        logger.error("WhatsApp send failed: %s", exc)


def run(dry_run: bool = False) -> int:
    """Run full pipeline. Returns exit code."""
    logger.info("=" * 60)
    logger.info("Vignesh daily runner started — %s", datetime.now().isoformat())
    logger.info("=" * 60)

    os.environ.setdefault("TCB_ENV", "prod")

    # Run Amazon and Blinkit (sequentially for simplicity; both complete before WhatsApp)
    amazon_result  = _run_amazon()
    blinkit_result = _run_blinkit()

    # Wait a moment to ensure DB writes are committed before querying for summary
    time.sleep(5)

    # Send WhatsApp briefing
    _send_whatsapp(amazon_result, blinkit_result, dry_run=dry_run)

    # Determine exit code + send targeted email alerts for any failures
    amazon_ok  = all(v == "ok" for v in amazon_result.values())
    blinkit_ok = blinkit_result.get("status") == "ok"

    try:
        from automation.email_sender import send_alert
        today = date.today().strftime("%d-%b")
        log   = f"automation/logs/daily_runner_{date.today().strftime('%Y%m%d')}.log"

        if not amazon_ok:
            send_alert(
                subject=f"⚠️ Amazon SP-API — Failed ({today})",
                body=(
                    f"Amazon SP-API pull failed.\n\n"
                    f"Detail: {amazon_result}\n\n"
                    f"Log: {log}"
                ),
            )

        blinkit_status = blinkit_result.get("status")
        if blinkit_status == "session_expired":
            send_alert(
                subject=f"⚠️ Blinkit Scraper — Session Expired ({today})",
                body=(
                    f"The Blinkit portal session has expired.\n\n"
                    f"Action required:\n"
                    f"  python automation/blinkit_auth.py\n\n"
                    f"Log: {log}"
                ),
            )
        elif blinkit_status != "ok":
            send_alert(
                subject=f"⚠️ Blinkit Scraper — Failed ({today})",
                body=(
                    f"Blinkit scraper failed (exit {blinkit_result.get('exit_code', '?')}).\n\n"
                    f"{blinkit_result.get('stderr', '')[:500]}\n\n"
                    f"Log: {log}"
                ),
            )
    except Exception as exc:
        logger.warning("Could not send failure alert email: %s", exc)

    if amazon_ok and blinkit_ok:
        logger.info("All done — success.")
        return 0
    elif amazon_ok or blinkit_ok:
        logger.warning("Partial success — one source failed.")
        return 1
    else:
        logger.error("Both sources failed.")
        return 2


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vignesh daily automation runner")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run ingestion but skip WhatsApp send")
    args = parser.parse_args()

    sys.exit(run(dry_run=args.dry_run))
