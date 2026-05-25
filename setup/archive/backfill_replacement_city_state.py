"""
One-off: backfill city/state for 6 REPLACEMENT Amazon orders using SP-API Orders API.

These orders have city=NULL because Amazon omits ship-city/ship-state for replacement
orders in the flat file report. The Orders API returns ShippingAddress directly.

Falls back to pincode_to_city_state() if City/StateOrRegion are absent in API response.

Usage:
    python setup/archive/backfill_replacement_city_state.py --dry-run
    python setup/archive/backfill_replacement_city_state.py
"""

from __future__ import annotations

import os
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import requests

SP_API_ENDPOINT = os.environ.get("SP_API_ENDPOINT", "https://sellingpartnerapi-eu.amazon.com")
LWA_TOKEN_URL   = "https://api.amazon.com/auth/o2/token"

_token_cache: dict = {}


def _get_access_token() -> str:
    now = time.time()
    if _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["access_token"]
    resp = requests.post(
        LWA_TOKEN_URL,
        data={
            "grant_type":    "refresh_token",
            "refresh_token": os.environ["SP_API_REFRESH_TOKEN"],
            "client_id":     os.environ["SP_API_CLIENT_ID"],
            "client_secret": os.environ["SP_API_CLIENT_SECRET"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    _token_cache["access_token"] = payload["access_token"]
    _token_cache["expires_at"]   = now + payload.get("expires_in", 3600)
    return _token_cache["access_token"]


def _headers() -> dict:
    from datetime import datetime, timezone
    return {
        "x-amz-access-token": _get_access_token(),
        "x-amz-date":         datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "Content-Type":       "application/json",
    }


def fetch_order(amazon_order_id: str) -> dict:
    """Call GET /orders/v0/orders/{orderId} and return payload dict."""
    url  = f"{SP_API_ENDPOINT}/orders/v0/orders/{amazon_order_id}"
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("payload", {})


def run(dry_run: bool) -> None:
    from tcb.db import get_client
    from ingest.utils import normalise_city, normalise_state
    from tcb.geo import pincode_to_city_state

    db = get_client()

    # Fetch the 6 REPLACEMENT orders missing city
    rows = (db.table("orders")
              .select("order_id, platform_order_id, sku_id")
              .is_("city", "null")
              .in_("channel_id", [2, 3])
              .eq("status", "REPLACEMENT")
              .execute().data)

    print(f"{'DRY RUN -- ' if dry_run else ''}Backfilling city/state for {len(rows)} REPLACEMENT order(s)")
    print("=" * 65)

    for r in rows:
        oid = r["platform_order_id"]
        try:
            payload = fetch_order(oid)
        except requests.HTTPError as e:
            print(f"  {oid}  ERROR fetching: {e}")
            continue

        addr = payload.get("ShippingAddress", {})
        city  = normalise_city(addr.get("City") or addr.get("City"))
        state = normalise_state(addr.get("StateOrRegion"))

        # Fallback: pincode lookup if city/state not in response
        if not city or not state:
            pincode = (addr.get("PostalCode") or "").strip()
            if pincode:
                pin_city, pin_state = pincode_to_city_state(pincode)
                city  = city  or normalise_city(pin_city)
                state = state or pin_state

        print(f"  {oid}  ({r['sku_id']})")
        print(f"    ShippingAddress: City={addr.get('City')!r}  StateOrRegion={addr.get('StateOrRegion')!r}  PostalCode={addr.get('PostalCode')!r}")
        print(f"    -> city={city!r}  state={state!r}")

        if not dry_run:
            if city or state:
                db.table("orders").update({
                    "city":  city,
                    "state": state,
                }).eq("order_id", r["order_id"]).execute()
                print(f"    Updated.")
            else:
                print(f"    WARNING: no city/state resolved -- skipped.")

    if dry_run:
        print("\nDry run complete -- no changes written.")
    else:
        # Verify
        remaining = (db.table("orders")
                       .select("order_id", count="exact")
                       .is_("city", "null")
                       .in_("channel_id", [2, 3])
                       .eq("status", "REPLACEMENT")
                       .execute().count)
        print(f"\nREPLACEMENT orders still missing city: {remaining}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
