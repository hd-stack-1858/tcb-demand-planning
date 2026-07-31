-- Cloud-hosted scrapers have no persistent local disk between runs, so
-- Playwright session state (cookies + storage) moves from
-- .blinkit_session/state.json and .fc_session/state.json into Supabase.
--
-- Plain JSON for now, no encryption — Supabase access is already tightly
-- restricted (service_role key only, never exposed to a browser). Encryption
-- is tracked separately (see docs/session_store.md).
--
-- No CHECK constraint on `portal` — validation lives in tcb/session_store.py's
-- _VALID_PORTALS instead, so adding a new portal (FnP, Zepto, etc.) later is a
-- one-line Python change, not a migration.

CREATE TABLE IF NOT EXISTS portal_sessions (
  portal      TEXT PRIMARY KEY,
  state_json  JSONB NOT NULL,
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);
