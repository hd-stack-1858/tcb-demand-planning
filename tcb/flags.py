"""
Feature Flags Module.
Handles environment-aware, multi-stage feature rollouts with failsafe fallbacks.
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# Cache maps flag_key -> (row_data_dict_or_None, expiry_timestamp)
_FLAG_CACHE: dict[str, tuple[dict | None, float]] = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECS = 60


def is_enabled(flag_key: str, user_email: str | None = None) -> bool:
    """
    Check if a feature flag is enabled for the current environment and user context.

    Lifecycle stages:
      - 'off': Disabled everywhere.
      - 'dev_only': Active only when TCB_ENV == 'dev'.
      - 'testing': Active when TCB_ENV is 'dev' or 'staging'.
      - 'prod_test': Active unconditionally in 'dev'/'staging'; in 'prod', only active
                     for whitelisted emails in the allowed_users list.
      - 'on': Enabled everywhere.

    Failsafe: Returns False on any query or connection failure.
    """
    now = time.time()

    # 1. Check cache
    with _CACHE_LOCK:
        if flag_key in _FLAG_CACHE:
            row, expiry = _FLAG_CACHE[flag_key]
            if now < expiry:
                return _resolve_flag(row, user_email)

    # 2. Query Supabase
    try:
        from tcb.db import get_client
        db = get_client()
        res = db.table("feature_flags").select("status, allowed_users").eq("flag_key", flag_key).single().execute()
        row = res.data
        
        with _CACHE_LOCK:
            if not row:
                logger.warning("Feature flag '%s' not found in database. Defaulting to False.", flag_key)
                # Cache negative result for a shorter period (10s) to avoid database spamming
                _FLAG_CACHE[flag_key] = (None, now + 10.0)
                return False

            # Cache successful query
            _FLAG_CACHE[flag_key] = (row, now + CACHE_TTL_SECS)
            
        return _resolve_flag(row, user_email)

    except Exception as exc:
        logger.warning("Failed to query feature flag '%s' from DB. Defaulting to False. Error: %s", flag_key, exc)
        # Cache connection failure briefly (5s) to prevent tight loop DB spamming while offline
        with _CACHE_LOCK:
            _FLAG_CACHE[flag_key] = (None, now + 5.0)
        return False


def _resolve_flag(row: dict | None, user_email: str | None) -> bool:
    if not row:
        return False

    status = row.get("status", "off").lower()
    allowed_users = row.get("allowed_users") or []

    env = os.environ.get("TCB_ENV", "prod").lower()

    if status == "off":
        return False
    elif status == "on":
        return True
    elif status == "dev_only":
        return env == "dev"
    elif status == "testing":
        return env in ("dev", "staging")
    elif status == "prod_test":
        if env in ("dev", "staging"):
            return True
        if env == "prod" and user_email:
            email_normalized = user_email.strip().lower()
            return any(email_normalized == u.strip().lower() for u in allowed_users)
        return False

    return False
