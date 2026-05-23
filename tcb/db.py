"""
Supabase DB client wrapper.
All DB access in this project goes through this module.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Set TCB_ENV=dev in your shell to use .env.dev instead of .env
_env_file = ".env.dev" if os.environ.get("TCB_ENV") == "dev" else ".env"
load_dotenv(Path(__file__).parent.parent / _env_file)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        # Use service_role key for backend scripts (bypasses RLS).
        # Never use this key in a browser/frontend.
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise EnvironmentError(
                "SUPABASE_URL and SUPABASE_KEY must be set in .env\n"
                "Use the service_role key (Settings → API in Supabase dashboard), "
                "NOT the anon key."
            )
        _client = create_client(url, key)
    return _client


# ── Convenience query helpers ─────────────────────────────────────────────────

def get_channels(active_only=True):
    db = get_client()
    q = db.table("channels").select("*")
    if active_only:
        q = q.eq("is_active", True)
    return q.order("name").execute().data


def get_skus(active_only=True):
    db = get_client()
    q = db.table("skus").select("*")
    if active_only:
        q = q.eq("is_active", True)
    return q.order("sku_id").execute().data


def get_items(active_only=True):
    db = get_client()
    q = db.table("items").select("*")
    if active_only:
        q = q.eq("is_active", True)
    return q.order("name").execute().data


def get_bom(sku_id: str = None):
    db = get_client()
    q = db.table("bom").select("*, items(name, unit, cost_per_unit)")
    if sku_id:
        q = q.eq("sku_id", sku_id)
    return q.execute().data


def get_inventory(channel_code: str = "OWN_WH"):
    """Return item-level inventory for a given location channel code."""
    db = get_client()
    ch = db.table("channels").select("channel_id").eq("code", channel_code).single().execute().data
    return (
        db.table("inventory")
        .select("*, items(name, unit, reorder_point, lead_time_days)")
        .eq("channel_id", ch["channel_id"])
        .order("items(name)")
        .execute()
        .data
    )


def get_assemblable_skus():
    """Return max assembable units per SKU from Own WH stock (uses DB view)."""
    return get_client().table("v_assemblable_skus").select("*").execute().data


def get_low_stock_alerts():
    """Return items at or below reorder point in Own WH."""
    return (
        get_client()
        .table("v_inventory_available")
        .select("*")
        .eq("location_type", "OWN_WH")
        .eq("below_reorder_point", True)
        .execute()
        .data
    )



def get_orders_raw(start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """Fetch all orders for MIS dashboard, with channel and sku names merged in Python."""
    db = get_client()

    cols = (
        "order_id, channel_id, order_date, sku_id, quantity, mrp, "
        "selling_price, gross_value, discount_pct, fulfillment_type, "
        "city, state, status, return_date, return_reason, "
        "return_responsible, return_customer_verbatim, "
        "platform_order_id, source_file"
    )
    orders: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        q = db.table("orders").select(cols)
        if start_date:
            q = q.gte("order_date", start_date)
        if end_date:
            q = q.lte("order_date", end_date)
        batch = q.order("order_date").range(offset, offset + page_size - 1).execute().data
        orders.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    if not orders:
        return []

    channels = {r["channel_id"]: r for r in db.table("channels").select("channel_id, name, code").execute().data}
    skus     = {r["sku_id"]:     r for r in db.table("skus").select("sku_id, name").execute().data}

    for row in orders:
        ch = channels.get(row["channel_id"], {})
        sk = skus.get(row["sku_id"], {})
        row["channel_name"] = ch.get("name", row["channel_id"])
        row["channel_code"] = ch.get("code", "")
        row["sku_name"]     = sk.get("name", row["sku_id"])
    return orders


def record_transaction(txn: dict):
    """
    Insert a single inventory transaction and update inventory position atomically.
    txn keys: type, item_id, from_channel_id, to_channel_id, quantity, reference, notes
    """
    db = get_client()
    db.table("inventory_transactions").insert(txn).execute()

    qty = txn["quantity"]
    if txn.get("from_channel_id"):
        _adjust_inventory(db, txn["item_id"], txn["from_channel_id"], -qty)
    if txn.get("to_channel_id"):
        _adjust_inventory(db, txn["item_id"], txn["to_channel_id"], +qty)


def _adjust_inventory(db: Client, item_id: int, channel_id: int, delta: int):
    """Increment/decrement quantity_on_hand for item at location."""
    existing = (
        db.table("inventory")
        .select("inv_id, quantity_on_hand")
        .eq("item_id", item_id)
        .eq("channel_id", channel_id)
        .execute()
        .data
    )
    if existing:
        new_qty = max(0, existing[0]["quantity_on_hand"] + delta)
        db.table("inventory").update(
            {"quantity_on_hand": new_qty, "last_updated": "now()"}
        ).eq("inv_id", existing[0]["inv_id"]).execute()
    else:
        db.table("inventory").insert(
            {"item_id": item_id, "channel_id": channel_id,
             "quantity_on_hand": max(0, delta), "quantity_reserved": 0,
             "quantity_intransit": 0}
        ).execute()
