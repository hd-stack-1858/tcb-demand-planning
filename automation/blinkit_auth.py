"""
Blinkit one-time authentication — saves browser session for daily scraper.

Run this once (and again whenever the session expires):
    python automation/blinkit_auth.py

What it does:
  1. Opens a real Chrome browser window
  2. Clicks "Sell on Blinkit" on the landing page
  3. Enters your phone number in the login modal
  4. Clicks "Send OTP" — waits for you to enter the OTP in the browser
  5. Detects successful login
  6. Saves the full browser session (cookies + storage) to .blinkit_session/state.json

After this, blinkit_scraper.py loads that saved session every day — no OTP needed
until the session expires (typically several weeks).

Required env var:
  BLINKIT_USERNAME   Your Blinkit seller portal phone number (10 digits, no country code)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv(Path(__file__).parent.parent / ".env")

PORTAL_URL   = "https://seller.blinkit.com"
SESSION_DIR  = Path(__file__).parent.parent / ".blinkit_session"
SESSION_FILE = SESSION_DIR / "state.json"

OTP_TIMEOUT_MS = 5 * 60 * 1000  # 5 minutes to enter OTP


def run() -> None:
    phone = os.environ.get("BLINKIT_USERNAME", "").strip()
    if not phone:
        print("ERROR: BLINKIT_USERNAME not set in .env")
        sys.exit(1)

    SESSION_DIR.mkdir(exist_ok=True)

    print(f"\n{'='*55}")
    print("  Blinkit One-Time Authentication")
    print(f"{'='*55}")
    print(f"  Phone: {phone}")
    print(f"  Session will be saved to: {SESSION_FILE}")
    print(f"{'='*55}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=200)
        ctx     = browser.new_context(viewport={"width": 1280, "height": 800})
        page    = ctx.new_page()

        # ── Step 1: Open portal ───────────────────────────────────────────────
        print("Opening Blinkit seller portal...")
        page.goto(PORTAL_URL, wait_until="networkidle", timeout=30_000)
        time.sleep(1)

        # ── Step 2: Click "Sell on Blinkit" button ────────────────────────────
        print('Clicking "Sell on Blinkit"...')
        try:
            btn = page.get_by_role("button", name="Sell on Blinkit")
            if not btn.count():
                btn = page.get_by_text("Sell on Blinkit").first
            btn.first.wait_for(timeout=10_000)
            btn.first.click()
            time.sleep(1)
        except (PWTimeout, Exception):
            # May already be on the login form, or session still valid
            print('  "Sell on Blinkit" not found — may already be at login form or logged in.')

        # ── Step 3: Fill phone number ─────────────────────────────────────────
        # The portal shows "+91-" prefix and expects just the 10-digit number
        print(f"Entering phone number: {phone}")
        time.sleep(2)  # wait for modal/page to fully render

        filled = False
        # Try progressively broader selectors
        selectors = [
            "input[placeholder*='phone' i]",
            "input[placeholder*='mobile' i]",
            "input[placeholder*='email' i]",
            "input[type='tel']",
            "input[type='text']",
            "input",   # last resort — grab the first visible input on the page
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.count() and el.is_visible():
                    el.click()
                    el.fill(phone)
                    print(f"  Filled via selector: {sel}")
                    filled = True
                    time.sleep(0.5)
                    break
            except Exception:
                continue

        if not filled:
            print("\nCould not find phone input automatically.")
            print("The browser is open — please enter your phone number manually,")
            print("then press ENTER here to continue.")
            input("Press ENTER once you've entered your phone number > ")

        # ── Step 4: Click "Send OTP" ──────────────────────────────────────────
        print('Clicking "Send OTP"...')
        try:
            otp_btn = page.get_by_role("button", name="Send OTP")
            if not otp_btn.count():
                otp_btn = page.get_by_text("Send OTP").first
            otp_btn.first.wait_for(timeout=10_000)
            otp_btn.first.click()
            print("  OTP request sent.")
        except (PWTimeout, Exception):
            print('  Could not click "Send OTP" automatically.')
            print("  Please click it in the browser window.")
            input("Press ENTER after clicking Send OTP > ")

        # ── Step 5: Wait for OTP entry ────────────────────────────────────────
        print(f"\n{'='*55}")
        print(f"  OTP sent to {phone}")
        print(f"  Enter the OTP in the browser window.")
        print(f"  Waiting up to 5 minutes for login...")
        print(f"{'='*55}\n")

        # Wait for URL to move past the landing/login page
        try:
            page.wait_for_function(
                """() => {
                    const url = window.location.href;
                    return !url.includes('login') &&
                           !url.includes('signin') &&
                           url !== 'https://seller.blinkit.com/' &&
                           url !== 'https://seller.blinkit.com';
                }""",
                timeout=OTP_TIMEOUT_MS,
            )
            print(f"Login detected. Current URL: {page.url}")
        except PWTimeout:
            # URL may not have changed — check for a post-login DOM element
            print("URL unchanged — checking for logged-in page elements...")
            try:
                page.wait_for_selector(
                    "nav, [class*='sidebar'], [class*='dashboard'], "
                    "[aria-label='Performance'], [title='Performance']",
                    timeout=10_000,
                )
                print("  Logged-in page elements detected.")
            except PWTimeout:
                print("\nCould not auto-detect login completion.")
                print("If you have successfully logged in, press ENTER to save the session.")
                input("Press ENTER to save session (or Ctrl+C to abort) > ")

        # ── Step 6: Save session ──────────────────────────────────────────────
        print("\nSaving session...")
        ctx.storage_state(path=str(SESSION_FILE))
        print(f"\n  Session saved to {SESSION_FILE}")
        print("  The daily scraper will use this until the session expires.")
        print("  When it expires, just run this script again.\n")

        browser.close()


if __name__ == "__main__":
    run()
