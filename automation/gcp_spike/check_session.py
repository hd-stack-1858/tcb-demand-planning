"""
Geo-spike connectivity/session check — run inside the Cloud Run Job.

Tests whether a portal accepts traffic from this container's IP (GCP
asia-south1), using the exact same session-replay / login heuristics as
the production scrapers, but doing nothing else (no downloads, no DB
writes). This is a standalone script, not wired into the real ingestion
pipeline.

Usage (inside the container):
    python check_session.py blinkit   # reads /sessions/blinkit/state.json
    python check_session.py fc        # reads /sessions/fc/state.json
    python check_session.py fnp       # reads FNP_USERNAME / FNP_PASSWORD env vars
    python check_session.py db        # reads SUPABASE_URL / SUPABASE_KEY env vars

Exit codes:
    0  — session valid / login succeeded / DB reachable
    2  — session expired / login rejected
    1  — unexpected error (network, portal changed, missing creds, etc.)
"""

from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

SESSION_ROOT = "/sessions"


def check_db() -> int:
    """
    Mirrors exactly how tcb/db.py connects in production: SUPABASE_URL/KEY
    read straight from the environment, no .env file (there won't be one in
    the real Cloud Run container — Secret Manager injects these as env vars
    directly). Runs one trivial read to prove the REST endpoint + service_role
    key actually work from this container's network path.
    """
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_KEY not set.")
        return 1

    from supabase import create_client
    client = create_client(url, key)

    print(f"Connecting to {url} ...")
    result = client.table("channels").select("channel_id").limit(1).execute()
    print(f"RESULT: query succeeded — {len(result.data)} row(s) returned.")
    return 0


def check_blinkit() -> int:
    session_file = f"{SESSION_ROOT}/blinkit/state.json"
    if not os.path.exists(session_file):
        print(f"NO SESSION FILE at {session_file} — upload it first.")
        return 1

    with sync_playwright() as p:
        # Mirrors automation/blinkit_scraper.py: Blinkit's Cloudflare bot
        # detection blocks Playwright's bundled Chromium in headless mode,
        # so real Chrome + stealth args are required.
        try:
            browser = p.chromium.launch(
                channel="chrome",
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
        ctx = browser.new_context(
            storage_state=session_file,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = ctx.new_page()
        print("Loading https://seller.blinkit.com ...")
        page.goto("https://seller.blinkit.com", wait_until="domcontentloaded", timeout=60_000)
        try:
            page.wait_for_selector(
                "nav, [class*='sidebar'], [class*='nav'], button:has-text('Sell on Blinkit')",
                timeout=30_000,
            )
        except PWTimeout:
            pass

        is_login = False
        try:
            btn = page.get_by_role("button", name="Sell on Blinkit")
            is_login = bool(btn.count() and btn.first.is_visible())
        except Exception:
            pass

        browser.close()
        if is_login:
            print("RESULT: session rejected — landed on login page.")
            return 2
        print("RESULT: session accepted — landed on dashboard.")
        return 0


def check_fc() -> int:
    session_file = f"{SESSION_ROOT}/fc/state.json"
    if not os.path.exists(session_file):
        print(f"NO SESSION FILE at {session_file} — upload it first.")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            storage_state=session_file,
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        print("Loading FC pending orders...")
        try:
            page.goto(
                "https://in-vcom.brainbees.com/#/ordermanagement/pendingorders",
                wait_until="domcontentloaded", timeout=30_000,
            )
        except Exception:
            pass
        time.sleep(3)

        logged_in = page.locator("text=Pending Orders").count() > 0
        browser.close()
        if not logged_in:
            print("RESULT: session rejected — not on pending orders page.")
            return 2
        print("RESULT: session accepted — pending orders loaded.")
        return 0


def check_fnp() -> int:
    username = os.environ.get("FNP_USERNAME", "").strip()
    password = os.environ.get("FNP_PASSWORD", "").strip()
    if not username or not password:
        print("FNP_USERNAME / FNP_PASSWORD not set.")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        print("Loading FnP login page...")
        page.goto(
            "https://partner.fnp.com/vendorapp/templates/index.html#/login/",
            wait_until="commit", timeout=60_000,
        )
        time.sleep(2)

        if "#/login" not in page.url:
            print("RESULT: already authenticated (unexpected — no session should exist).")
            browser.close()
            return 0

        try:
            email_input = page.locator("input[type='email']").first
            if not email_input.count() or not email_input.is_visible():
                email_input = page.locator("input[type='text']:visible").first
            email_input.fill(username)
            page.locator("input[type='password']").first.fill(password)
            page.get_by_role("button", name="Login").click()
            page.wait_for_url(lambda url: "#/login" not in url, timeout=30_000)
            page.wait_for_selector("text=TODAY", timeout=30_000)
        except Exception as exc:
            browser.close()
            print(f"RESULT: login failed or blocked — {exc}")
            return 2

        browser.close()
        print("RESULT: login succeeded — dashboard loaded.")
        return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("blinkit", "fc", "fnp", "db"):
        print("Usage: python check_session.py <blinkit|fc|fnp|db>")
        return 1

    portal = sys.argv[1]
    try:
        if portal == "blinkit":
            return check_blinkit()
        elif portal == "fc":
            return check_fc()
        elif portal == "fnp":
            return check_fnp()
        else:
            return check_db()
    except Exception as exc:
        print(f"UNEXPECTED ERROR: {exc!r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
