# Portal session storage (`tcb/session_store.py`)

Cloud-hosted scrapers have no persistent local disk between invocations, so
Blinkit and FirstCry Playwright session state (cookies + storage, captured
by `automation/blinkit_auth.py` / `automation/fc_auth.py`) is stored in
Supabase instead of `.blinkit_session/state.json` / `.fc_session/state.json`.

Part of [#33](https://github.com/hd-stack-1858/tcb-demand-planning/issues/33)
under the parent migration
[#32](https://github.com/hd-stack-1858/tcb-demand-planning/issues/32).

## Schema

`setup/migrations/027_add_portal_sessions.sql`:

```sql
CREATE TABLE portal_sessions (
  portal      TEXT PRIMARY KEY,
  state_json  JSONB NOT NULL,
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);
```

Plain JSON — **no encryption yet**. This is a deliberate interim choice:
Supabase access is already tightly restricted (service_role key only, never
exposed to a browser or committed to the repo). Encrypting the blob is
tracked separately in
[#39](https://github.com/hd-stack-1858/tcb-demand-planning/issues/39).

FnP is out of scope — it has no persistent session (plain username/password
login every run, no CAPTCHA), so there's nothing to store for it here.

No `CHECK` constraint on `portal` — deliberately, so adding a future portal
(FnP, Zepto, etc.) is a one-line Python change, not a migration. See "API"
below for where the validation actually lives.

## API

```python
from tcb.session_store import load_session, save_session

state = load_session("blinkit")   # dict (Playwright storage_state shape) or None
save_session("blinkit", state)    # upsert
```

`portal` must be one of `tcb/session_store.py`'s `_VALID_PORTALS` (currently
`"blinkit"`, `"fc"`) — anything else raises `ValueError` before any DB call.
This is the only validation; the DB column has no constraint.

## How the scrapers use this

- **`blinkit_auth.py` / `fc_auth.py`**: after a successful interactive login,
  call `save_session(portal, ctx.storage_state())` instead of writing to
  disk. `ctx.storage_state()` (no `path=` arg) returns the state as a dict.
- **`blinkit_scraper.py`, `blinkit_soh_scraper.py`,
  `blinkit_performance_scraper.py`, `fc_scraper.py`**: call
  `load_session(portal)` and pass the dict straight to
  `browser.new_context(storage_state=...)` — Playwright accepts either a
  file path or the state dict directly, so no temp file is needed.
- **Blinkit's self-refresh**: all three Blinkit scrapers call
  `save_session("blinkit", ctx.storage_state())` again at the end of every
  successful run. This is what has kept the Blinkit session alive for weeks
  at a time without re-running OTP — that write-back now lands in Supabase
  instead of the local file, and must be preserved by any future change to
  these scrapers.
- **FirstCry does not self-refresh** — `fc_scraper.py` only reads the
  session, matching its pre-existing behavior (it never wrote the session
  back to disk either). FC re-auth stays a periodic manual step regardless
  of this migration.

## Applying the migration

Follow the standard [DB change workflow](../CLAUDE.md#db-change-workflow--mandatory):
run `setup/migrations/027_add_portal_sessions.sql` against dev first, verify
end-to-end, then hand it to Himanshu to apply to prod.

## Migrating an existing local session (no re-auth needed)

If a valid `.blinkit_session/state.json` or `.fc_session/state.json` already
exists locally — e.g. shared by Himanshu/Meet, or left over from before this
migration — there's no need to burn an OTP/reCAPTCHA cycle re-running
`blinkit_auth.py`/`fc_auth.py`. Push the existing file straight into the store:

```bash
TCB_ENV=dev python automation/sync_local_sessions_to_store.py            # both portals
TCB_ENV=dev python automation/sync_local_sessions_to_store.py --portal fc # one portal
```

It reads the local JSON, calls `save_session`, then reads it back via
`load_session` to confirm the round-trip matched. Silently skips any portal
whose local file doesn't exist — safe to run even if only one session is
present.
