"""
One-off migration helper: pushes existing local Playwright session files
into Supabase's portal_sessions table, without re-running blinkit_auth.py /
fc_auth.py (no OTP/reCAPTCHA needed if a valid local session already exists).

Useful right after the session_store migration lands, or any time someone
already has a fresh .blinkit_session/state.json or .fc_session/state.json
sitting locally (e.g. shared by Himanshu/Meet) that should be synced to the
DB instead of triggering a fresh interactive login.

Usage:
    TCB_ENV=dev python automation/sync_local_sessions_to_store.py
    TCB_ENV=dev python automation/sync_local_sessions_to_store.py --portal blinkit
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tcb.session_store import save_session, load_session

ROOT = Path(__file__).parent.parent

_LOCAL_SESSION_FILES = {
    "blinkit": ROOT / ".blinkit_session" / "state.json",
    "fc": ROOT / ".fc_session" / "state.json",
}


def sync_portal(portal: str) -> bool:
    path = _LOCAL_SESSION_FILES[portal]
    if not path.exists():
        print(f"{portal}: no local session file at {path} — skipping.")
        return False

    state = json.loads(path.read_text())
    save_session(portal, state)
    verified = load_session(portal) == state
    print(
        f"{portal}: synced from {path} "
        f"({len(state.get('cookies', []))} cookies) — "
        f"round-trip {'OK' if verified else 'MISMATCH'}"
    )
    return verified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--portal", choices=sorted(_LOCAL_SESSION_FILES), default=None,
        help="Sync only this portal (default: sync all with a local file present)",
    )
    args = parser.parse_args()

    portals = [args.portal] if args.portal else sorted(_LOCAL_SESSION_FILES)
    results = [sync_portal(p) for p in portals]

    if not any(results):
        print("Nothing synced.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
