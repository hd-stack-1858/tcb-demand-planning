"""
Daily automation runner — runs at 12:01 PM IST via Windows Task Scheduler.

Sequence:
  12:01  → G1: Amazon SP-API (orders + finances)
  12:01  → G2: Blinkit scraper (MTD sales)
  ~12:15 → G3: WhatsApp briefing (after G1 + G2 complete)
  ~12:15 → G4: Blinkit SOH scraper + ingest (immediate download, ~30 sec)
  ~12:16 → G5: Blinkit performance scraper + loader (7-8 min download)
  ~12:25 → G6: Dev DB ping (keep Supabase free-tier active — prevent 7-day auto-pause)

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


def _run_soh() -> dict:
    """G4: Blinkit SOH scraper + ingest. Immediate download (~30 sec)."""
    logger.info("Blinkit SOH scraper (G4): starting...")
    proc = subprocess.run(
        [PYTHON, str(PROJECT / "automation" / "blinkit_soh_scraper.py")],
        capture_output=True, text=True, cwd=str(PROJECT),
        env={**os.environ, "TCB_ENV": "prod"},
        timeout=120,  # 2-minute cap — download is immediate
    )

    if proc.returncode == 0:
        logger.info("Blinkit SOH scraper: OK — %s", proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "done")
        return {"status": "ok"}
    elif proc.returncode == 2:
        logger.warning("Blinkit SOH session expired — same session as sales scraper.")
        return {"status": "session_expired"}
    else:
        logger.error("Blinkit SOH scraper failed (exit %d):\n%s", proc.returncode, proc.stderr[-500:])
        return {"status": "error", "exit_code": proc.returncode, "stderr": proc.stderr}


def _run_performance() -> dict:
    """G5: Blinkit performance scraper + loader. Runs last — download takes 7-8 min."""
    logger.info("Blinkit performance scraper (G5): starting...")
    proc = subprocess.run(
        [PYTHON, str(PROJECT / "automation" / "blinkit_performance_scraper.py")],
        capture_output=True, text=True, cwd=str(PROJECT),
        env={**os.environ, "TCB_ENV": "prod"},
        timeout=720,  # 12-minute hard cap (download is 7-8 min + ingest overhead)
    )

    if proc.returncode == 0:
        logger.info("Blinkit performance scraper: OK — %s", proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "done")
        return {"status": "ok"}
    elif proc.returncode == 2:
        logger.warning("Blinkit performance session expired — same session as sales scraper.")
        return {"status": "session_expired"}
    else:
        logger.error("Blinkit performance scraper failed (exit %d):\n%s", proc.returncode, proc.stderr[-500:])
        return {"status": "error", "exit_code": proc.returncode, "stderr": proc.stderr}


def _ping_dev_db() -> None:
    """Open and immediately close a dev DB connection to prevent Supabase free-tier pause."""
    try:
        from dotenv import dotenv_values
        dev = dotenv_values(Path(__file__).parent.parent / ".env.dev")
        url = dev.get("DEV_DB_URL", "")
        if not url:
            logger.warning("Dev DB ping: DEV_DB_URL not set — skipping.")
            return
        s = url[len("postgresql://"):]
        ui, hi   = s.rsplit("@", 1)
        user, pw = ui.split(":", 1)
        hp, db   = hi.rsplit("/", 1)
        host, port = hp.rsplit(":", 1)
        import psycopg2
        psycopg2.connect(
            host=host, port=int(port), dbname=db,
            user=user, password=pw, sslmode="require",
            connect_timeout=15,
        ).close()
        logger.info("Dev DB ping: OK")
    except Exception as exc:
        logger.warning("Dev DB ping failed (non-fatal): %s", exc)


def run(dry_run: bool = False) -> int:
    """Run full pipeline. Returns exit code."""
    logger.info("=" * 60)
    logger.info("Vignesh daily runner started — %s", datetime.now().isoformat())
    logger.info("=" * 60)

    os.environ.setdefault("TCB_ENV", "prod")

    # Run Amazon and Blinkit (sequentially for simplicity; both complete before WhatsApp)
    amazon_result  = _run_amazon()

    # G1b: finalize COGS for AZ orders loaded above (consume AZ channel lots)
    try:
        from tcb.inventory import finalize_az_cogs
        result = finalize_az_cogs()
        logger.info(
            "AZ COGS finalized: %d total | %d lot-traced | %d fallback | %d no-cogs",
            result["total"], result["lot_finalized"],
            result["fallback_cogs"], result["no_cogs"],
        )
        if result["no_cogs"]:
            logger.warning("AZ COGS: %d order(s) could not get COGS — check sku_cogs_lots", result["no_cogs"])
    except Exception as exc:
        logger.error("AZ COGS finalization failed (non-fatal): %s", exc)

    blinkit_result = _run_blinkit()

    # G2b: finalize COGS for Blinkit FULFILLED orders (consume BLK channel lots FIFO)
    try:
        from tcb.inventory import finalize_blk_cogs
        blk_result = finalize_blk_cogs()
        logger.info(
            "BLK COGS finalized: %d total | %d finalized | %d no-cogs",
            blk_result["total"], blk_result["finalized"], blk_result["no_cogs"],
        )
        if blk_result["no_cogs"]:
            logger.warning("BLK COGS: %d order(s) could not get COGS — check sku_cogs_lots", blk_result["no_cogs"])
    except Exception as exc:
        logger.error("BLK COGS finalization failed (non-fatal): %s", exc)

    # Wait a moment to ensure DB writes are committed before querying for summary
    time.sleep(5)

    # Send WhatsApp briefing (G3) — before the longer downloads
    _send_whatsapp(amazon_result, blinkit_result, dry_run=dry_run)

    # G4: Blinkit SOH scraper + ingest (immediate download — ~30 sec)
    soh_result = _run_soh()

    # G5: Blinkit performance scraper + loader (runs last — 7-8 min download)
    perf_result = _run_performance()

    # Determine exit code + send targeted email alerts for any failures
    amazon_ok  = all(v == "ok" for v in amazon_result.values())
    blinkit_ok = blinkit_result.get("status") == "ok"
    soh_ok     = soh_result.get("status") == "ok"
    perf_ok    = perf_result.get("status") == "ok"

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

        soh_status = soh_result.get("status")
        if soh_status == "session_expired":
            logger.warning("SOH scraper: same session expiry as sales scraper.")
        elif soh_status != "ok":
            send_alert(
                subject=f"⚠️ Blinkit SOH Scraper — Failed ({today})",
                body=(
                    f"Blinkit SOH scraper (G4) failed (exit {soh_result.get('exit_code', '?')}).\n\n"
                    f"{soh_result.get('stderr', '')[:500]}\n\n"
                    f"Log: {log}"
                ),
            )

        perf_status = perf_result.get("status")
        if perf_status == "session_expired":
            # Session already alerted above for sales scraper; just log
            logger.warning("Performance scraper: same session expiry as sales scraper.")
        elif perf_status != "ok":
            send_alert(
                subject=f"⚠️ Blinkit Performance Scraper — Failed ({today})",
                body=(
                    f"Blinkit performance scraper (G5) failed (exit {perf_result.get('exit_code', '?')}).\n\n"
                    f"{perf_result.get('stderr', '')[:500]}\n\n"
                    f"Log: {log}"
                ),
            )
    except Exception as exc:
        logger.warning("Could not send failure alert email: %s", exc)

    # Last step — ping dev DB to prevent Supabase free-tier auto-pause (7-day inactivity limit)
    _ping_dev_db()

    if amazon_ok and blinkit_ok and soh_ok and perf_ok:
        logger.info("All done — success.")
        return 0
    elif not amazon_ok and not blinkit_ok and not soh_ok and not perf_ok:
        logger.error("All sources failed.")
        return 2
    else:
        logger.warning("Partial success — one or more sources failed.")
        return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vignesh daily automation runner")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run ingestion but skip WhatsApp send")
    args = parser.parse_args()

    sys.exit(run(dry_run=args.dry_run))
