"""
Supabase-backed storage for Playwright session state (Blinkit, FirstCry).

Replaces local .blinkit_session/state.json and .fc_session/state.json so
scrapers can run on a cloud host with no persistent disk between invocations.
Plain JSON — no encryption yet (see docs/session_store.md).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from tcb.db import get_client

# The DB has no CHECK constraint on `portal` — this tuple is the only
# validation. Adding a new portal (FnP, Zepto, etc.) is a one-line change
# here, no migration needed.
_VALID_PORTALS = ("blinkit", "fc")


def load_session(portal: str) -> Optional[dict]:
    """Returns the saved storage_state dict for `portal`, or None if no session is saved."""
    if portal not in _VALID_PORTALS:
        raise ValueError(f"Unknown portal '{portal}' — expected one of {_VALID_PORTALS}")

    db = get_client()
    rows = db.table("portal_sessions").select("state_json").eq("portal", portal).execute().data
    return rows[0]["state_json"] if rows else None


def save_session(portal: str, state: dict) -> None:
    """Upserts the storage_state dict for `portal`."""
    if portal not in _VALID_PORTALS:
        raise ValueError(f"Unknown portal '{portal}' — expected one of {_VALID_PORTALS}")

    db = get_client()
    db.table("portal_sessions").upsert({
        "portal": portal,
        "state_json": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
