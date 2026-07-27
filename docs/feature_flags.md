# Feature Flags System

This document outlines the architecture, usage, and management of the feature flags system at The Cradle Box.

---

## Why Feature Flags?
We use feature flags to perform **phased, environment-by-environment rollouts** of features (e.g. Supabase Auth wrapper, cloud scrapers) safely:
* Deploy code to `main` and production without immediately activating it.
* Test new features directly in `dev` and `staging` while keeping them off in `prod`.
* Enable features for specific whitelisted users in `prod` for beta testing.
* Flip features on or off instantly in production without requiring code redeploys.

---

## Database Schema
Feature flags are stored in the `feature_flags` table of each environment's database (`dev` and `prod` databases are completely separate):

```sql
CREATE TABLE feature_flags (
    flag_key TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('off', 'dev_only', 'testing', 'prod_test', 'on')),
    allowed_users TEXT[] NOT NULL DEFAULT '{}',
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Flag Status Lifecycle Stages

| Status | Dev (`TCB_ENV=dev`) | Staging (`TCB_ENV=staging`) | Prod (`TCB_ENV=prod`) | Use Case |
|---|---|---|---|---|
| **`off`** | `False` | `False` | `False` | Disabled everywhere (kill-switch). |
| **`dev_only`** | `True` | `False` | `False` | Active only for local developers. |
| **`testing`** | `True` | `True` | `False` | Open for internal QA/testing. |
| **`prod_test`** | `True` | `True` | `True` if user whitelisted | Whitelisted production testing (BETA). |
| **`on`** | `True` | `True` | `True` | Fully released to everyone. |

---

## Checking Flags in Code

Import the `is_enabled` helper from `tcb.flags`. It handles caching and fails safe to `False` on any database error or missing flag.

### Basic Check (Global features / Crons)
```python
from tcb.flags import is_enabled

if is_enabled("cloud_scrapers_enabled"):
    # Run the scraper logic
    pass
else:
    # Exit early or run legacy logic
    pass
```

### Whitelisted User Check (UI / Streamlit apps)
Always pass the logged-in user's email as the second argument when checking flags inside user-facing UIs:
```python
from tcb.flags import is_enabled

# For a Streamlit app with user context
user_email = st.session_state.get("user_email")

if is_enabled("auth_wrapper_enabled", user_email=user_email):
    st.write("Welcome to the new Auth system!")
else:
    st.write("Legacy view")
```

---

## Caching & Failsafe Behaviors

### TTL Cache
To prevent slamming the Supabase DB on every Streamlit rerun or scraper loop, `is_enabled` caches lookups in memory for **60 seconds**.
* A flag state flip in the database will be reflected in-app within a maximum of 60 seconds without restarting the service.

### Failsafes
* If a flag does not exist in the database, `is_enabled` returns `False`.
* If the database is offline, queries time out, or query syntax fails, `is_enabled` catches the exception, logs a warning, and returns `False`.
* Connection failures are cached for **5 seconds** to prevent tight loops from spamming an offline database.

---

## How to Manage Flags

### 1. Adding a New Flag
Create a new migration file under `setup/migrations/NNN_name.sql` to register and seed your flag:

```sql
INSERT INTO feature_flags (flag_key, status, description)
VALUES ('my_new_feature', 'dev_only', 'Testing new checkout flow');
```

### 2. Toggling Flags in Production
Flipping a flag in production is a **data write**, not a schema change, so it does not require running migrations.
You can toggle a flag directly in the Supabase Production SQL Editor or table viewer:

```sql
-- Enable production testing for Himanshu and PV
UPDATE feature_flags
SET status = 'prod_test', allowed_users = '{himanshu@example.com, pv@example.com}'
WHERE flag_key = 'my_new_feature';

-- Fully roll out the feature to everyone
UPDATE feature_flags
SET status = 'on'
WHERE flag_key = 'my_new_feature';
```
> [!IMPORTANT]
> Since toggling a flag in **prod** instantly changes live behavior, it should be done deliberately and synchronized with your release notes.
