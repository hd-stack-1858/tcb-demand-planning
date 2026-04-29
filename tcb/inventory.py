"""
Inventory business logic — assembly, dispatch, receive.
All operations update both the position tables and the audit log.
"""
import sys
from datetime import date, datetime, timezone, timedelta
from collections import defaultdict

IST = timezone(timedelta(hours=5, minutes=30))
from tcb.db import get_client

# ── Helpers ───────────────────────────────────────────────────────────────────

def _own_wh_id():
    return (get_client().table("channels").select("channel_id")
            .eq("code", "OWN_WH").single().execute().data["channel_id"])

def _now():
    return datetime.now(IST).isoformat()


# ── Read helpers ──────────────────────────────────────────────────────────────

def get_item_stock():
    """Aggregated item stock at OWN_WH across all batches."""
    db = get_client()
    own_wh_id = _own_wh_id()
    rows = (db.table("inventory")
              .select("item_id, quantity_on_hand, items(item_code, name, unit, reorder_point, moq, lead_time_days, supplier_id, suppliers(name))")
              .eq("channel_id", own_wh_id)
              .execute().data)
    agg = defaultdict(lambda: {
        "item_code": "", "name": "", "unit": "", "qty": 0,
        "reorder_point": 0, "moq": 1, "lead_time_days": 7, "supplier": "",
    })
    for r in rows:
        it = r["items"]
        agg[r["item_id"]]["item_code"]      = it["item_code"]
        agg[r["item_id"]]["name"]           = it["name"]
        agg[r["item_id"]]["unit"]           = it["unit"]
        agg[r["item_id"]]["reorder_point"]  = it["reorder_point"] or 0
        agg[r["item_id"]]["moq"]            = it["moq"] or 1
        agg[r["item_id"]]["lead_time_days"] = it["lead_time_days"] or 7
        agg[r["item_id"]]["supplier"]       = (it.get("suppliers") or {}).get("name", "")
        agg[r["item_id"]]["qty"]           += r["quantity_on_hand"]
    return dict(agg)  # item_id → {...}


def get_reorder_alerts():
    """
    All items where stock < reorder_point, including items with zero stock
    (no inventory row yet). Queries items table directly then overlays stock.
    """
    db = get_client()
    own_wh_id = _own_wh_id()

    # All items with a meaningful ROP
    all_items = (db.table("items")
                   .select("item_id, item_code, name, unit, reorder_point, moq, lead_time_days, suppliers(name)")
                   .gt("reorder_point", 0)
                   .eq("is_active", True)
                   .execute().data)

    # Current stock summed per item at OWN_WH
    inv_rows = (db.table("inventory")
                  .select("item_id, quantity_on_hand")
                  .eq("channel_id", own_wh_id)
                  .execute().data)
    stock_map = {}
    for r in inv_rows:
        stock_map[r["item_id"]] = stock_map.get(r["item_id"], 0) + r["quantity_on_hand"]

    alerts = []
    for it in all_items:
        qty = stock_map.get(it["item_id"], 0)
        rop = it["reorder_point"] or 0
        if qty < rop:
            alerts.append({
                "item_code":      it["item_code"],
                "name":           it["name"],
                "unit":           it["unit"],
                "qty":            qty,
                "reorder_point":  rop,
                "moq":            it["moq"] or 1,
                "lead_time_days": it["lead_time_days"] or 7,
                "supplier":       (it.get("suppliers") or {}).get("name", ""),
            })
    return alerts


def get_sku_stock():
    """Assembled SKU stock at OWN_WH."""
    db = get_client()
    own_wh_id = _own_wh_id()
    return (db.table("sku_inventory")
              .select("sku_id, qty_on_hand, qty_reserved, skus(name)")
              .eq("channel_id", own_wh_id)
              .execute().data)


def get_assemblable():
    """Max assemblable units per SKU from current loose item stock."""
    db = get_client()
    item_stock = get_item_stock()
    bom_rows   = db.table("bom").select("sku_id, item_id, quantity_per_sku").execute().data
    skus       = (db.table("skus").select("sku_id, name")
                    .eq("is_discontinued", False).order("sku_id").execute().data)

    bom_by_sku = defaultdict(list)
    for b in bom_rows:
        bom_by_sku[b["sku_id"]].append(b)

    result = []
    for sku in skus:
        sid = sku["sku_id"]
        if sid not in bom_by_sku:
            continue
        max_units = None
        for b in bom_by_sku[sid]:
            avail    = item_stock.get(b["item_id"], {}).get("qty", 0)
            possible = avail // b["quantity_per_sku"]
            if max_units is None or possible < max_units:
                max_units = possible
        result.append({"sku_id": sid, "name": sku["name"], "assemblable": max_units or 0})
    return result


def check_assembly_feasibility(sku_id, qty_to_pack):
    """
    Returns (feasible: bool, detail: list of dicts per BOM line).
    detail = [{"item_id", "name", "unit", "needed", "available", "ok"}]
    """
    db = get_client()
    item_stock = get_item_stock()
    bom = (db.table("bom")
             .select("item_id, quantity_per_sku, items(name, unit)")
             .eq("sku_id", sku_id).execute().data)

    detail = []
    feasible = True
    for b in bom:
        needed    = b["quantity_per_sku"] * qty_to_pack
        available = item_stock.get(b["item_id"], {}).get("qty", 0)
        ok        = available >= needed
        if not ok:
            feasible = False
        detail.append({
            "item_id":   b["item_id"],
            "name":      b["items"]["name"],
            "unit":      b["items"]["unit"],
            "needed":    needed,
            "available": available,
            "ok":        ok,
        })
    return feasible, detail


# ── Write operations ──────────────────────────────────────────────────────────

def assemble_sku(sku_id, qty_to_pack, notes="", created_by="app"):
    """
    Pack qty_to_pack units of sku_id.
    Consumes items FIFO (oldest batch first), updates inventory + sku_inventory,
    logs ASSEMBLY transactions.
    Raises ValueError if stock is insufficient.
    """
    db = get_client()
    own_wh_id = _own_wh_id()
    qty_to_pack = int(qty_to_pack)

    bom = (db.table("bom").select("item_id, quantity_per_sku")
             .eq("sku_id", sku_id).execute().data)

    # ── Plan FIFO consumption ─────────────────────────────────
    consumption_plan = {}  # item_id → [(inv_id, batch_id, consume_qty, cost_per_unit)]
    total_cogs = 0.0

    for b in bom:
        item_id  = b["item_id"]
        needed   = int(b["quantity_per_sku"]) * qty_to_pack

        inv_rows = (db.table("inventory")
                      .select("inv_id, batch_id, quantity_on_hand, "
                              "item_batches(received_date, cost_per_unit)")
                      .eq("item_id", item_id)
                      .eq("channel_id", own_wh_id)
                      .gt("quantity_on_hand", 0)
                      .execute().data)

        inv_rows.sort(key=lambda r: r["item_batches"]["received_date"])

        available = sum(r["quantity_on_hand"] for r in inv_rows)
        if available < needed:
            item_name = (db.table("items").select("name").eq("item_id", item_id)
                           .single().execute().data["name"])
            raise ValueError(
                f"Insufficient stock for '{item_name}': need {needed}, have {available}"
            )

        plan = []
        remaining = needed
        for row in inv_rows:
            if remaining <= 0:
                break
            consume = min(row["quantity_on_hand"], remaining)
            cost    = row["item_batches"].get("cost_per_unit") or 0
            plan.append({
                "inv_id":        row["inv_id"],
                "batch_id":      row["batch_id"],
                "consume":       consume,
                "cost_per_unit": cost,
            })
            total_cogs += consume * cost
            remaining  -= consume

        consumption_plan[item_id] = (plan, b["quantity_per_sku"])

    unit_cogs = round(total_cogs / qty_to_pack, 4) if qty_to_pack else 0

    # ── Execute ───────────────────────────────────────────────
    for item_id, (plan, _) in consumption_plan.items():
        for p in plan:
            # Fetch current qty (re-fetch to be safe)
            cur = (db.table("inventory").select("quantity_on_hand")
                     .eq("inv_id", p["inv_id"]).single().execute().data)
            new_qty = int(cur["quantity_on_hand"]) - int(p["consume"])
            db.table("inventory").update({"quantity_on_hand": new_qty})\
              .eq("inv_id", p["inv_id"]).execute()
            db.table("item_batches").update({"is_current": new_qty > 0})\
              .eq("batch_id", p["batch_id"]).execute()

            db.table("inventory_transactions").insert({
                "type":            "ASSEMBLY",
                "item_id":         item_id,
                "sku_id":          sku_id,
                "batch_id":        p["batch_id"],
                "from_channel_id": own_wh_id,
                "quantity":        int(p["consume"]),
                "reference":       f"ASSEMBLE_{sku_id}",
                "notes":           notes,
                "created_by":      created_by,
            }).execute()

    # Update sku_inventory
    existing = (db.table("sku_inventory").select("sku_inv_id, qty_on_hand")
                  .eq("sku_id", sku_id).eq("channel_id", own_wh_id).execute().data)
    if existing:
        db.table("sku_inventory").update(
            {"qty_on_hand": int(existing[0]["qty_on_hand"]) + int(qty_to_pack),
             "last_updated": _now()}
        ).eq("sku_inv_id", existing[0]["sku_inv_id"]).execute()
    else:
        db.table("sku_inventory").insert({
            "sku_id": sku_id, "channel_id": own_wh_id,
            "qty_on_hand": int(qty_to_pack), "qty_reserved": 0,
        }).execute()

    db.table("sku_inventory_transactions").insert({
        "type":          "ASSEMBLY",
        "sku_id":        sku_id,
        "to_channel_id": own_wh_id,
        "quantity":      int(qty_to_pack),
        "unit_cogs":     unit_cogs,
        "notes":         notes,
        "created_by":    created_by,
    }).execute()

    return unit_cogs


def record_dropship_sale(sku_id, qty, channel_id, selling_price,
                         order_date=None, platform_order_id=None,
                         city=None, notes="", created_by="app"):
    """
    Record a drop-ship / direct sale: dispatches inventory AND writes to orders table.
    Use this for DROP_SHIP / DIRECT channel shipments instead of dispatch_sku().
    COGS = qty × unit_cogs from the most recent ASSEMBLY transaction (valid because
    assembly itself uses FIFO item costs, so latest assembly COGS = current FIFO cost).
    """
    db  = get_client()
    qty = int(qty)
    selling_price = float(selling_price)

    if order_date is None:
        order_date = date.today()

    last_asm = (db.table("sku_inventory_transactions")
                  .select("unit_cogs")
                  .eq("sku_id", sku_id)
                  .eq("type", "ASSEMBLY")
                  .order("created_at", desc=True)
                  .limit(1).execute().data)
    unit_cogs = float(last_asm[0]["unit_cogs"] or 0) if last_asm else 0.0

    # Inventory movement first — raises ValueError on insufficient stock
    dispatch_sku(sku_id, qty, channel_id,
                 reference=platform_order_id or "",
                 notes=notes, created_by=created_by)

    db.table("orders").insert({
        "channel_id":        channel_id,
        "order_date":        order_date.strftime("%Y-%m-%d") if hasattr(order_date, "strftime") else str(order_date),
        "sku_id":            sku_id,
        "quantity":          qty,
        "selling_price":     selling_price,
        "gross_value":       round(qty * selling_price, 2),
        "cogs":              round(qty * unit_cogs, 2),
        "fulfillment_type":  "DROP_SHIP",
        "city":              city or None,
        "platform_order_id": platform_order_id or None,
        "status":            "FULFILLED",
        "source_file":       "warehouse_app",
    }).execute()


def dispatch_sku(sku_id, qty, channel_id, reference="", notes="", created_by="app"):
    """
    Dispatch assembled SKUs from OWN_WH.
    - DROP_SHIP / DIRECT channels → type = DISPATCH
    - FBA / SOR / OUTRIGHT channels → type = TRANSFER_OUT
    Raises ValueError if SKU stock is insufficient.
    """
    db = get_client()
    own_wh_id = _own_wh_id()
    qty = int(qty)

    ch = (db.table("channels").select("code, business_model, name")
            .eq("channel_id", channel_id).single().execute().data)
    txn_type = (
        "TRANSFER_OUT"
        if ch["business_model"] in ("FBA", "SOR", "OUTRIGHT")
        else "DISPATCH"
    )

    inv = (db.table("sku_inventory").select("sku_inv_id, qty_on_hand")
             .eq("sku_id", sku_id).eq("channel_id", own_wh_id).execute().data)
    available = inv[0]["qty_on_hand"] if inv else 0
    if available < qty:
        raise ValueError(f"Insufficient SKU stock: need {qty}, have {available}")

    db.table("sku_inventory").update({"qty_on_hand": available - qty, "last_updated": _now()})\
      .eq("sku_inv_id", inv[0]["sku_inv_id"]).execute()

    db.table("sku_inventory_transactions").insert({
        "type":            txn_type,
        "sku_id":          sku_id,
        "from_channel_id": own_wh_id,
        "to_channel_id":   channel_id if txn_type == "TRANSFER_OUT" else None,
        "quantity":        qty,
        "reference":       reference,
        "notes":           notes,
        "created_by":      created_by,
    }).execute()

    return txn_type


def return_sku(sku_id, qty, from_channel_id, notes="", created_by="app"):
    """Return assembled SKU from a partner back into OWN_WH stock."""
    db = get_client()
    own_wh_id = _own_wh_id()
    qty = int(qty)

    existing = (db.table("sku_inventory").select("sku_inv_id, qty_on_hand")
                  .eq("sku_id", sku_id).eq("channel_id", own_wh_id).execute().data)
    if existing:
        db.table("sku_inventory").update(
            {"qty_on_hand": existing[0]["qty_on_hand"] + qty, "last_updated": _now()}
        ).eq("sku_inv_id", existing[0]["sku_inv_id"]).execute()
    else:
        db.table("sku_inventory").insert({
            "sku_id": sku_id, "channel_id": own_wh_id,
            "qty_on_hand": qty, "qty_reserved": 0,
        }).execute()

    db.table("sku_inventory_transactions").insert({
        "type":            "RETURN",
        "sku_id":          sku_id,
        "from_channel_id": from_channel_id,
        "to_channel_id":   own_wh_id,
        "quantity":        qty,
        "notes":           notes,
        "created_by":      created_by,
    }).execute()


def return_item(item_id, qty, notes="", created_by="app"):
    """
    Return individual item/packaging component to OWN_WH.
    Added to today's batch. Carries last known purchase cost so re-assembled
    hampers reflect correct COGS.
    """
    db = get_client()
    own_wh_id = _own_wh_id()
    qty = int(qty)
    today      = date.today()
    batch_code = today.strftime("%Y%m%d")

    # Use last real purchase cost so re-assembled COGS is correct
    last = (db.table("item_batches")
              .select("cost_per_unit")
              .eq("item_id", item_id)
              .gt("cost_per_unit", 0)
              .order("received_date", desc=True)
              .limit(1).execute().data)
    cost = float(last[0]["cost_per_unit"]) if last else 0.0

    existing_batch = (db.table("item_batches")
                        .select("batch_id, qty_received, qty_remaining")
                        .eq("item_id", item_id)
                        .eq("batch_code", batch_code)
                        .execute().data)

    if existing_batch:
        batch_id = existing_batch[0]["batch_id"]
        db.table("item_batches").update({
            "qty_received":  existing_batch[0]["qty_received"]  + qty,
            "qty_remaining": existing_batch[0]["qty_remaining"] + qty,
            "is_current":    True,
        }).eq("batch_id", batch_id).execute()
    else:
        result = db.table("item_batches").insert({
            "item_id":       item_id,
            "batch_code":    batch_code,
            "received_date": today.strftime("%Y-%m-%d"),
            "cost_per_unit": cost,
            "qty_received":  qty,
            "qty_remaining": qty,
            "is_current":    True,
        }).execute()
        batch_id = result.data[0]["batch_id"]

    existing_inv = (db.table("inventory")
                      .select("inv_id, quantity_on_hand")
                      .eq("item_id", item_id)
                      .eq("batch_id", batch_id)
                      .eq("channel_id", own_wh_id)
                      .execute().data)
    if existing_inv:
        db.table("inventory").update({
            "quantity_on_hand": existing_inv[0]["quantity_on_hand"] + qty
        }).eq("inv_id", existing_inv[0]["inv_id"]).execute()
    else:
        db.table("inventory").insert({
            "item_id":            item_id,
            "batch_id":           batch_id,
            "channel_id":         own_wh_id,
            "quantity_on_hand":   qty,
            "quantity_reserved":  0,
            "quantity_intransit": 0,
        }).execute()

    db.table("inventory_transactions").insert({
        "type":          "SALE_RETURN",
        "item_id":       item_id,
        "batch_id":      batch_id,
        "to_channel_id": own_wh_id,
        "quantity":      qty,
        "notes":         notes,
        "created_by":    created_by,
    }).execute()


def writeoff_sku(sku_id, qty, reason, notes="", created_by="app"):
    """Write off assembled SKU qty from OWN_WH (Lost / Damaged / QC Reject)."""
    db = get_client()
    own_wh_id = _own_wh_id()
    qty = int(qty)

    inv = (db.table("sku_inventory").select("sku_inv_id, qty_on_hand")
             .eq("sku_id", sku_id).eq("channel_id", own_wh_id).execute().data)
    available = inv[0]["qty_on_hand"] if inv else 0
    if available < qty:
        raise ValueError(f"Insufficient SKU stock: need {qty}, have {available}")

    db.table("sku_inventory").update(
        {"qty_on_hand": available - qty, "last_updated": _now()}
    ).eq("sku_inv_id", inv[0]["sku_inv_id"]).execute()

    db.table("sku_inventory_transactions").insert({
        "type":            "ADJUSTMENT",
        "sku_id":          sku_id,
        "from_channel_id": own_wh_id,
        "quantity":        qty,
        "notes":           f"[WRITE-OFF: {reason}] {notes}".strip(),
        "created_by":      created_by,
    }).execute()


def writeoff_item(item_id, qty, reason, notes="", created_by="app"):
    """Write off loose item qty from OWN_WH FIFO (Lost / Damaged / QC Reject)."""
    db = get_client()
    own_wh_id = _own_wh_id()
    qty = int(qty)

    inv_rows = (db.table("inventory")
                  .select("inv_id, batch_id, quantity_on_hand, item_batches(received_date)")
                  .eq("item_id", item_id)
                  .eq("channel_id", own_wh_id)
                  .gt("quantity_on_hand", 0)
                  .execute().data)
    inv_rows.sort(key=lambda r: r["item_batches"]["received_date"])

    available = sum(r["quantity_on_hand"] for r in inv_rows)
    if available < qty:
        raise ValueError(f"Insufficient stock: need {qty}, have {available}")

    remaining = qty
    for row in inv_rows:
        if remaining <= 0:
            break
        consume  = min(row["quantity_on_hand"], remaining)
        new_qty  = row["quantity_on_hand"] - consume
        db.table("inventory").update({"quantity_on_hand": new_qty})\
          .eq("inv_id", row["inv_id"]).execute()
        db.table("item_batches").update({"is_current": new_qty > 0})\
          .eq("batch_id", row["batch_id"]).execute()
        remaining -= consume

    db.table("inventory_transactions").insert({
        "type":            "DAMAGE_WRITE_OFF",
        "item_id":         item_id,
        "from_channel_id": own_wh_id,
        "quantity":        qty,
        "notes":           f"[{reason}] {notes}".strip(),
        "created_by":      created_by,
    }).execute()


def receive_item(item_id, qty, cost_per_unit, supplier_id=None,
                 receipt_date=None, notes="", created_by="app"):
    """
    Record an inward stock receipt at OWN_WH.
    Batch auto-created from receipt_date (YYYYMMDD). If same-date batch exists,
    quantities are merged and cost updated.
    """
    db = get_client()
    own_wh_id = _own_wh_id()
    qty = int(qty)

    if receipt_date is None:
        receipt_date = date.today()
    batch_code = receipt_date.strftime("%Y%m%d")

    existing_batch = (db.table("item_batches")
                        .select("batch_id, qty_received, qty_remaining")
                        .eq("item_id", item_id)
                        .eq("batch_code", batch_code)
                        .execute().data)

    if existing_batch:
        batch_id = existing_batch[0]["batch_id"]
        db.table("item_batches").update({
            "qty_received":  existing_batch[0]["qty_received"]  + qty,
            "qty_remaining": existing_batch[0]["qty_remaining"] + qty,
            "cost_per_unit": cost_per_unit,
            "is_current":    True,
            "supplier_id":   supplier_id,
        }).eq("batch_id", batch_id).execute()
    else:
        result = db.table("item_batches").insert({
            "item_id":       item_id,
            "batch_code":    batch_code,
            "received_date": receipt_date.strftime("%Y-%m-%d"),
            "supplier_id":   supplier_id,
            "cost_per_unit": cost_per_unit,
            "qty_received":  qty,
            "qty_remaining": qty,
            "is_current":    True,
        }).execute()
        batch_id = result.data[0]["batch_id"]

    existing_inv = (db.table("inventory")
                      .select("inv_id, quantity_on_hand")
                      .eq("item_id", item_id)
                      .eq("batch_id", batch_id)
                      .eq("channel_id", own_wh_id)
                      .execute().data)

    if existing_inv:
        db.table("inventory").update({
            "quantity_on_hand": existing_inv[0]["quantity_on_hand"] + qty
        }).eq("inv_id", existing_inv[0]["inv_id"]).execute()
    else:
        db.table("inventory").insert({
            "item_id":            item_id,
            "batch_id":           batch_id,
            "channel_id":         own_wh_id,
            "quantity_on_hand":   qty,
            "quantity_reserved":  0,
            "quantity_intransit": 0,
        }).execute()

    db.table("inventory_transactions").insert({
        "type":          "RECEIPT",
        "item_id":       item_id,
        "batch_id":      batch_id,
        "to_channel_id": own_wh_id,
        "quantity":      qty,
        "reference":     f"INWARD_{batch_code}",
        "notes":         notes,
        "created_by":    created_by,
    }).execute()

    return batch_id
