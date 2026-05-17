"""
First Cry one-time authentication — saves browser session for daily scraper.

Run this once (and again whenever the session expires):
    python automation/fc_auth.py

What it does:
  1. Opens a Chrome browser window
  2. Fills email + password
  3. Waits for you to click the reCAPTCHA checkbox in the browser
  4. Clicks Login
  5. Saves the full browser session to .fc_session/state.json

After this, fc_scraper.py loads that session every day — no reCAPTCHA needed
until the session expires (typically several weeks).

Required env vars:
  FC_USERNAME    First Cry vendor portal email
  FC_PASSWORD    First Cry vendor portal password
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv(Path(__file__).parent.parent / ".env")

PORTAL_URL   = "https://in-vcom.brainbees.com/#/"
SESSION_DIR  = Path(__file__).parent.parent / ".fc_session"
SESSION_FILE = SESSION_DIR / "state.json"


def run() -> None:
    username = os.environ.get("FC_USERNAME", "").strip()
    password = os.environ.get("FC_PASSWORD", "").strip()
    if not username or not password:
        print("ERROR: FC_USERNAME and FC_PASSWORD must be set in .env")
        sys.exit(1)

    SESSION_DIR.mkdir(exist_ok=True)

    print(f"\n{'='*55}")
    print("  First Cry One-Time Authentication")
    print(f"{'='*55}")
    print(f"  Email: {username}")
    print(f"  Session will be saved to: {SESSION_FILE}")
    print(f"{'='*55}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        ctx  = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()

        # ── Step 1: Open portal ───────────────────────────────────────────────
        print("Opening First Cry Vcom portal...")
        page.goto(PORTAL_URL, wait_until="networkidle", timeout=30_000)
        time.sleep(2)

        # ── Step 2: Fill credentials ──────────────────────────────────────────
        print("Filling credentials...")
        page.locator("input[type='email'], input[type='text']").first.fill(username)
        page.locator("input[type='password']").first.fill(password)
        time.sleep(1)

        # ── Step 3: reCAPTCHA ─────────────────────────────────────────────────
        print(f"\n{'='*55}")
        print("  ACTION REQUIRED:")
        print("  Click the 'I am not a robot' checkbox in the browser window.")
        print("  If an image puzzle appears, solve it.")
        print("  Once the checkbox shows a green tick, press ENTER here.")
        print(f"{'='*55}\n")
        input("Press ENTER after completing the reCAPTCHA > ")

        # ── Step 4: Click Login ───────────────────────────────────────────────
        print("Clicking Login...")
        login_btn = page.get_by_role("button", name="Login")
        if not login_btn.count():
            login_btn = page.locator("button:has-text('Login'), input[type='submit']").first
        login_btn.click()

        # ── Step 5: Wait for dashboard, then navigate to pending orders ─────
        # We save the session from the pending orders page so the saved
        # cookies are associated with that route — avoids reCAPTCHA on reuse.
        print("Waiting for dashboard to load...")
        try:
            page.wait_for_selector("text=Welcome To Vcom, text=Dashboard, nav", timeout=30_000)
            print(f"  Dashboard loaded. URL: {page.url}")
            print("  Navigating to Pending Orders to enrich session state...")
            try:
                page.goto("https://in-vcom.brainbees.com/#/ordermanagement/pendingorders",
                          wait_until="domcontentloaded", timeout=15_000)
            except Exception:
                pass
            time.sleep(3)
            print(f"  URL: {page.url}")
        except PWTimeout:
            print("  Dashboard selector timed out — checking login state...")
            if page.locator("input[type='password']").count():
                print("\nStill on login page. Login may have failed.")
                print("Check the browser window and try again.")
                browser.close()
                sys.exit(1)
            print("  Logged in. Navigating to Pending Orders before saving...")
            try:
                page.goto("https://in-vcom.brainbees.com/#/ordermanagement/pendingorders",
                          wait_until="domcontentloaded", timeout=15_000)
            except Exception:
                pass  # page may have loaded even if networkidle/timeout fires
            time.sleep(3)
            print(f"  URL: {page.url}")

        # ── Step 6: Save session ──────────────────────────────────────────────
        print("\nSaving session...")
        ctx.storage_state(path=str(SESSION_FILE))
        print(f"\n  Session saved to {SESSION_FILE}")
        print("  The daily scraper will use this until the session expires.\n")

        browser.close()


if __name__ == "__main__":
    run()
