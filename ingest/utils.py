"""Shared helpers for partner sell-out ingestion scripts."""

from __future__ import annotations

import logging
import time
from datetime import date
from functools import lru_cache

logger = logging.getLogger(__name__)


def _execute_with_retry(query, retries: int = 3, backoff: float = 2.0):
    """Execute a postgrest query, retrying on transient network errors."""
    import httpx
    import httpcore
    for attempt in range(retries):
        try:
            return query.execute()
        except (httpx.ReadError, httpx.ConnectError, httpcore.ReadError, httpcore.ConnectError):
            if attempt == retries - 1:
                raise
            wait = backoff * (2 ** attempt)
            logger.warning("Network error on attempt %d — retrying in %.1fs", attempt + 1, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")

# TCB009 (2025 mugs) and TCB009_1 (2026 mugs) share the same Blinkit Item ID.
# Orders before this cutoff → TCB009; from this date onwards → TCB009_1.
_TCB009_1_CUTOFF = date(2026, 3, 1)
_AMBIGUOUS_BLK_ITEM_ID = 10274008


@lru_cache(maxsize=1)
def _load_blinkit_sku_map() -> dict[str, str]:
    """Return {platform_pid_additional: sku_id} for all unambiguous Blinkit SKUs."""
    from tcb.db import get_client
    rows = _execute_with_retry(
        get_client()
        .table("sku_channel_ids")
        .select("sku_id, platform_pid_additional")
        .eq("channel_code", "BLK")
    ).data
    result: dict[str, str] = {}
    for r in rows:
        val = r.get("platform_pid_additional") or ""
        try:
            item_id = int(val)
        except (ValueError, TypeError):
            continue  # 'Not listed', 'NA', etc.
        if item_id != _AMBIGUOUS_BLK_ITEM_ID:
            result[str(item_id)] = r["sku_id"]
    return result


def resolve_blinkit_sku(blinkit_item_id: int, order_date: date) -> str | None:
    """Return our sku_id for a Blinkit Item ID + order date.

    Handles the TCB009/TCB009_1 ambiguity: both versions share item_id 10274008.
    Returns None if the item_id is not mapped.
    """
    if blinkit_item_id == _AMBIGUOUS_BLK_ITEM_ID:
        return "TCB009" if order_date < _TCB009_1_CUTOFF else "TCB009_1"
    sku_id = _load_blinkit_sku_map().get(str(blinkit_item_id))
    if sku_id is None:
        logger.warning("Unknown Blinkit item_id %s — row skipped", blinkit_item_id)
    return sku_id


# ── Amazon helpers ────────────────────────────────────────────────────────────

# Indian state normalisation: handles abbreviations AND all-caps full names.
_STATE_NORM: dict[str, str] = {
    # Abbreviations
    "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam",
    "BR": "Bihar", "CG": "Chhattisgarh", "GA": "Goa", "GJ": "Gujarat",
    "HR": "Haryana", "HP": "Himachal Pradesh", "JK": "Jammu & Kashmir",
    "JH": "Jharkhand", "KA": "Karnataka", "KL": "Kerala",
    "MP": "Madhya Pradesh", "MH": "Maharashtra", "MN": "Manipur",
    "ML": "Meghalaya", "MZ": "Mizoram", "NL": "Nagaland",
    "OD": "Odisha", "OR": "Odisha", "PB": "Punjab", "RJ": "Rajasthan",
    "SK": "Sikkim", "TN": "Tamil Nadu", "TG": "Telangana", "TR": "Tripura",
    "UP": "Uttar Pradesh", "UK": "Uttarakhand", "WB": "West Bengal",
    "DL": "Delhi", "CH": "Chandigarh", "PY": "Puducherry",
    "DN": "Dadra & Nagar Haveli", "DD": "Daman & Diu", "LD": "Lakshadweep",
    "AN": "Andaman & Nicobar Islands",
}


def normalise_state(raw: str | None) -> str | None:
    """Return a consistently-cased state name from Amazon ship-state values."""
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    upper = s.upper()
    # Try abbreviation map first (2–3 char codes)
    if upper in _STATE_NORM:
        return _STATE_NORM[upper]
    # Already a full name (possibly all-caps) — title-case it
    return s.title()


@lru_cache(maxsize=1)
def _load_amazon_asin_map() -> dict[str, str]:
    """Return {asin: sku_id} from sku_channel_ids for channel AZ."""
    from tcb.db import get_client
    rows = _execute_with_retry(
        get_client()
        .table("sku_channel_ids")
        .select("sku_id, platform_pid")
        .eq("channel_code", "AZ")
    ).data
    result: dict[str, str] = {}
    for r in rows:
        pid = (r.get("platform_pid") or "").strip()
        if pid and pid not in ("Not listed", "NA"):
            result[pid] = r["sku_id"]
    return result


def resolve_amazon_sku(asin: str) -> str | None:
    """Return our sku_id for an Amazon ASIN. Returns None if not mapped."""
    sku_id = _load_amazon_asin_map().get(asin.strip())
    if sku_id is None:
        logger.warning("Unknown ASIN %s — row skipped", asin)
    return sku_id


@lru_cache(maxsize=256)
def get_sku_mrp_at_date(sku_id: str, as_of_date: date) -> float | None:
    """Return the MRP effective on as_of_date from sku_pricing."""
    from tcb.db import get_client
    rows = _execute_with_retry(
        get_client()
        .table("sku_pricing")
        .select("mrp")
        .eq("sku_id", sku_id)
        .lte("effective_date", str(as_of_date))
        .order("effective_date", desc=True)
        .limit(1)
    ).data
    return float(rows[0]["mrp"]) if rows else None


# ── First Cry helpers ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_fc_product_map() -> dict[str, str]:
    """Return {platform_pid: sku_id} for all FC SKUs with a mapped Product ID."""
    from tcb.db import get_client
    rows = _execute_with_retry(
        get_client()
        .table("sku_channel_ids")
        .select("sku_id, platform_pid")
        .eq("channel_code", "FC")
    ).data
    result: dict[str, str] = {}
    for r in rows:
        pid = str(r.get("platform_pid") or "").strip()
        if pid and pid not in ("Not listed", "NA", ""):
            result[pid] = r["sku_id"]
    return result


def resolve_fc_sku(product_id: str | int) -> str | None:
    """Return our sku_id for a First Cry Product ID. Returns None if not mapped."""
    sku_id = _load_fc_product_map().get(str(product_id).strip())
    if sku_id is None:
        logger.warning("Unknown FC Product ID %s — row skipped", product_id)
    return sku_id


@lru_cache(maxsize=256)
def get_sku_sp_at_date(sku_id: str, as_of_date: date) -> float | None:
    """Return the selling price (sp) effective on as_of_date from sku_pricing."""
    from tcb.db import get_client
    rows = _execute_with_retry(
        get_client()
        .table("sku_pricing")
        .select("sp")
        .eq("sku_id", sku_id)
        .lte("effective_date", str(as_of_date))
        .order("effective_date", desc=True)
        .limit(1)
    ).data
    return float(rows[0]["sp"]) if rows else None


@lru_cache(maxsize=512)
def get_channel_tp_at_date(sku_id: str, channel_code: str, as_of_date: date) -> float | None:
    """Return the transfer price effective on as_of_date from sku_channel_tp."""
    from tcb.db import get_client
    rows = _execute_with_retry(
        get_client()
        .table("sku_channel_tp")
        .select("transfer_price")
        .eq("sku_id", sku_id)
        .eq("channel_code", channel_code)
        .lte("effective_date", str(as_of_date))
        .order("effective_date", desc=True)
        .limit(1)
    ).data
    return float(rows[0]["transfer_price"]) if rows else None


# ── SKU COGS helper ────────────────────────────────────────────────────────────

@lru_cache(maxsize=512)
def get_sku_cogs_at_date(sku_id: str, as_of_date: date) -> float | None:
    """Compute SKU COGS at a point in time: BOM × most-recent batch cost per item.

    For each BOM item, uses the batch with the most recent received_date on or before
    as_of_date. Returns None if the BOM is empty or any item has no batch before that date.
    Results are cached — safe to call once per row in a bulk load.
    """
    from tcb.db import get_client
    db = get_client()

    bom = _execute_with_retry(
        db.table("bom")
        .select("item_id, quantity_per_sku")
        .eq("sku_id", sku_id)
    ).data
    if not bom:
        return None

    total = 0.0
    for b in bom:
        batch = _execute_with_retry(
            db.table("item_batches")
            .select("cost_per_unit")
            .eq("item_id", b["item_id"])
            .lte("received_date", str(as_of_date))
            .order("received_date", desc=True)
            .limit(1)
        ).data
        if not batch:
            return None
        total += float(b["quantity_per_sku"]) * float(batch[0]["cost_per_unit"])

    return round(total, 2)
