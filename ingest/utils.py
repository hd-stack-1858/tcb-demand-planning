"""Shared helpers for partner sell-out ingestion scripts."""

from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache

logger = logging.getLogger(__name__)

# TCB009 (2025 mugs) and TCB009_1 (2026 mugs) share the same Blinkit Item ID.
# Orders before this cutoff → TCB009; from this date onwards → TCB009_1.
_TCB009_1_CUTOFF = date(2026, 3, 1)
_AMBIGUOUS_BLK_ITEM_ID = 10274008


@lru_cache(maxsize=1)
def _load_blinkit_sku_map() -> dict[str, str]:
    """Return {platform_pid_additional: sku_id} for all unambiguous Blinkit SKUs."""
    from tcb.db import get_client
    rows = (
        get_client()
        .table("sku_channel_ids")
        .select("sku_id, platform_pid_additional")
        .eq("channel_code", "BLK")
        .execute()
        .data
    )
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


@lru_cache(maxsize=512)
def get_sku_cogs_at_date(sku_id: str, as_of_date: date) -> float | None:
    """Compute SKU COGS at a point in time: BOM × most-recent batch cost per item.

    For each BOM item, uses the batch with the most recent received_date on or before
    as_of_date. Returns None if the BOM is empty or any item has no batch before that date.
    Results are cached — safe to call once per row in a bulk load.
    """
    from tcb.db import get_client
    db = get_client()

    bom = (
        db.table("bom")
        .select("item_id, quantity_per_sku")
        .eq("sku_id", sku_id)
        .execute()
        .data
    )
    if not bom:
        return None

    total = 0.0
    for b in bom:
        batch = (
            db.table("item_batches")
            .select("cost_per_unit")
            .eq("item_id", b["item_id"])
            .lte("received_date", str(as_of_date))
            .order("received_date", desc=True)
            .limit(1)
            .execute()
            .data
        )
        if not batch:
            return None
        total += float(b["quantity_per_sku"]) * float(batch[0]["cost_per_unit"])

    return round(total, 2)
