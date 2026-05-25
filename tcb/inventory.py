"""
Inventory business logic — assembly, dispatch, receive.
All operations update both the position tables and the audit log.
"""
import logging
from datetime import date, datetime, timezone, timedelta
from collections import defaultdict

IST = timezone(timedelta(hours=5, minutes=30))
from tcb.db import get_client
from tcb.geo import city_to_state

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _own_wh_id():
    return (get_client().table("channels").select("channel_id")
            .eq("code", "OWN_WH").single().execute().data["channel_id"])

def _now():
    return datetime.now(IST).isoformat()

def _date_str(d):
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)


def _upsert_lot(db, sku_id, channel_id, partner_location_id, assembled_at, unit_cogs, add_qty):
    """
    Add add_qty to an existing COGS lot, or create it if none exists.
    Lot identity: (sku_id, channel_id, partner_location_id, assembled_at, unit_cogs).
    """
    q = (db.table("sku_cogs_lots")
           .select("lot_id, qty_assembled, qty_remaining")
           .eq("sku_id", sku_id)
           .eq("channel_id", channel_id)
           .eq("assembled_at", str(assembled_at))
           .eq("unit_cogs", unit_cogs))
    if partner_location_id is None:
        q = q.is_("partner_location_id", "null")
    else:
        q = q.eq("partner_location_id", partner_location_id)

    existing = q.execute().data
    if existing:
        row = existing[0]
        db.table("sku_cogs_lots").update({
            "qty_assembled": row["qty_assembled"] + add_qty,
            "qty_remaining": row["qty_remaining"] + add_qty,
        }).eq("lot_id", row["lot_id"]).execute()
    else:
        data = {
            "sku_id":       sku_id,
            "channel_id":   channel_id,
            "assembled_at": str(assembled_at),
            "unit_cogs":    unit_cogs,
            "qty_assembled": add_qty,
            "qty_remaining": add_qty,
        }
        if partner_location_id is not None:
            data["partner_location_id"] = partner_location_id
        db.table("sku_cogs_lots").insert(data).execute()


def _consume_lots_fifo(db, sku_id, channel_id, qty, partner_location_id=None):
    """
    FIFO-consume qty units from lots at (sku_id, channel_id[, partner_location_id]).
    Decrements qty_remaining on consumed lots immediately.
    Returns (plan, weighted_avg_cogs).
      plan = [{"lot_id", "assembled_at", "unit_cogs", "qty"}, ...]
    Raises ValueError if available lot qty < qty requested.
    """
    q = (db.table("sku_cogs_lots")
           .select("lot_id, assembled_at, unit_cogs, qty_remaining")
           .eq("sku_id", sku_id)
           .eq("channel_id", channel_id)
           .gt("qty_remaining", 0)
           .order("assembled_at"))
    if partner_location_id is None:
        q = q.is_("partner_location_id", "null")
    else:
        q = q.eq("partner_location_id", partner_location_id)

    lots = q.execute().data
    available = sum(l["qty_remaining"] for l in lots)
    if available < qty:
        loc_hint = f" location_id={partner_location_id}" if partner_location_id else ""
        raise ValueError(
            f"Insufficient COGS lots for {sku_id}: need {qty}, have {available} "
            f"(channel_id={channel_id}{loc_hint}). "
            "Run setup/seed_sku_cogs_lots.py or check assembly history."
        )

    lot_qty = {l["lot_id"]: int(l["qty_remaining"]) for l in lots}
    plan = []
    remaining = qty
    for lot in lots:
        if remaining <= 0:
            break
        consume = min(lot_qty[lot["lot_id"]], remaining)
        plan.append({
            "lot_id":       lot["lot_id"],
            "assembled_at": lot["assembled_at"],
            "unit_cogs":    float(lot["unit_cogs"]),
            "qty":          consume,
        })
        remaining -= consume

    for p in plan:
        new_qty = lot_qty[p["lot_id"]] - p["qty"]
        db.table("sku_cogs_lots").update({"qty_remaining": new_qty})\
          .eq("lot_id", p["lot_id"]).execute()
        lot_qty[p["lot_id"]] = new_qty

    total_cost = sum(p["unit_cogs"] * p["qty"] for p in plan)
    return plan, round(total_cost / qty, 4) if qty else 0.0


def _get_sku_cogs_fallback(sku_id, db):
    """
    Fallback COGS when no lots exist (e.g. pre-migration returns).
    Uses latest ASSEMBLY txn unit_cogs, then BOM × item_batches.
    """
    last_asm = (db.table("sku_inventory_transactions")
                  .select("unit_cogs")
                  .eq("sku_id", sku_id)
                  .eq("type", "ASSEMBLY")
                  .gt("unit_cogs", 0)
                  .order("created_at", desc=True)
                  .limit(1).execute().data)
    if last_asm:
        return float(last_asm[0]["unit_cogs"])

    bom_rows = (db.table("bom").select("item_id, quantity_per_sku")
                  .eq("sku_id", sku_id).execute().data)
    if not bom_rows:
        return 0.0

    item_ids   = [b["item_id"] for b in bom_rows]
    all_batches = (db.table("item_batches")
                     .select("item_id, cost_per_unit")
                     .in_("item_id", item_ids)
                     .gt("cost_per_unit", 0)
                     .order("received_date", desc=True)
                     .execute().data)
    latest_cost = {}
    for row in all_batches:
        if row["item_id"] not in latest_cost:
            latest_cost[row["item_id"]] = float(row["cost_per_unit"])

    total = 0.0
    for b in bom_rows:
        total += b["quantity_per_sku"] * latest_cost.get(b["item_id"], 0.0)
    return round(total, 4)


def _lookup_mrp(db, sku_id, order_date_str):
    """Latest MRP from sku_pricing on or before order_date. Returns None if missing."""
    row = (db.table("sku_pricing")
             .select("mrp")
             .eq("sku_id", sku_id)
             .lte("effective_date", order_date_str)
             .order("effective_date", desc=True)
             .limit(1).execute().data)
    return float(row[0]["mrp"]) if row and row[0].get("mrp") else None


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
    return dict(agg)


def get_reorder_alerts():
    """
    All items where stock < reorder_point, including items with zero stock.
    """
    db = get_client()
    own_wh_id = _own_wh_id()

    all_items = (db.table("items")
                   .select("item_id, item_code, name, unit, reorder_point, moq, lead_time_days, suppliers(name)")
                   .gt("reorder_point", 0)
                   .eq("is_active", True)
                   .execute().data)

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
    logs ASSEMBLY transactions, and creates/grows a COGS lot at OWN_WH.
    Raises ValueError if stock is insufficient.
    """
    db = get_client()
    own_wh_id = _own_wh_id()
    qty_to_pack = int(qty_to_pack)

    bom = (db.table("bom").select("item_id, quantity_per_sku")
             .eq("sku_id", sku_id).execute().data)

    consumption_plan = {}
    total_cogs = 0.0

    for b in bom:
        item_id = b["item_id"]
        needed  = int(b["quantity_per_sku"]) * qty_to_pack

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

    for item_id, (plan, _) in consumption_plan.items():
        for p in plan:
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

    _upsert_lot(db, sku_id, own_wh_id, None, date.today(), unit_cogs, qty_to_pack)

    # Verify lot sync: total lot qty must match sku_inventory after assembly.
    # Catches silent insert failures before they cause dispatch errors later.
    lot_total = sum(
        r["qty_remaining"]
        for r in (
            db.table("sku_cogs_lots")
            .select("qty_remaining")
            .eq("sku_id", sku_id)
            .eq("channel_id", own_wh_id)
            .is_("partner_location_id", "null")
            .gt("qty_remaining", 0)
            .execute().data or []
        )
    )
    inv_row = (
        db.table("sku_inventory")
        .select("qty_on_hand")
        .eq("sku_id", sku_id)
        .eq("channel_id", own_wh_id)
        .execute().data
    )
    inv_qty = int(inv_row[0]["qty_on_hand"]) if inv_row else 0
    if lot_total != inv_qty:
        raise RuntimeError(
            f"COGS lot sync failed after assembly of {sku_id}: "
            f"lots total {lot_total} != inventory {inv_qty}. "
            f"Assembly is recorded but COGS tracking is inconsistent — "
            f"manually reconcile sku_cogs_lots before dispatching."
        )

    return unit_cogs


def dispatch_sku(sku_id, qty, channel_id, reference="", notes="", created_by="app",
                 txn_type=None, partner_location_id=None):
    """
    Dispatch assembled SKUs from OWN_WH. Consumes COGS lots FIFO.
    - DROP_SHIP / DIRECT channels → type = DISPATCH
    - FBA / SOR / OUTRIGHT channels → type = TRANSFER_OUT; mirrors lots to partner channel
    Returns (txn_type, unit_cogs).
    Raises ValueError if SKU stock or COGS lots are insufficient.
    """
    db = get_client()
    own_wh_id = _own_wh_id()
    qty = int(qty)

    if txn_type is None:
        ch = (db.table("channels").select("code, business_model")
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

    plan, unit_cogs = _consume_lots_fifo(db, sku_id, own_wh_id, qty)

    db.table("sku_inventory").update({"qty_on_hand": available - qty, "last_updated": _now()})\
      .eq("sku_inv_id", inv[0]["sku_inv_id"]).execute()

    base_txn = {
        "type":            txn_type,
        "sku_id":          sku_id,
        "from_channel_id": own_wh_id,
        "to_channel_id":   channel_id,
        "reference":       reference,
        "notes":           notes,
        "created_by":      created_by,
    }
    if partner_location_id is not None:
        base_txn["partner_location_id"] = partner_location_id
    txn_rows = [
        {**base_txn, "quantity": p["qty"], "unit_cogs": p["unit_cogs"], "lot_id": p["lot_id"]}
        for p in plan
    ]
    db.table("sku_inventory_transactions").insert(txn_rows).execute()

    if txn_type == "TRANSFER_OUT":
        for p in plan:
            _upsert_lot(db, sku_id, channel_id, partner_location_id,
                        p["assembled_at"], p["unit_cogs"], p["qty"])

    return txn_type, unit_cogs


def finalize_az_cogs(dry_run: bool = False) -> dict:
    """
    Stamp COGS on AZ/AZ_FBM FULFILLED orders that have lot_cogs_finalized=False.

    Called daily after Amazon orders are loaded. For each order:
      FBA (AZ channel)    — consumes from AZ channel sku_cogs_lots (mirrored at TRANSFER_OUT)
      FBM (AZ_FBM channel) — consumes from OWN_WH sku_cogs_lots

    Inserts sku_inventory_transactions DISPATCH rows (one per lot, with lot_id).
    Falls back to _get_sku_cogs_fallback() when lots are exhausted or missing.
    Does NOT touch sku_inventory.qty_on_hand (AZ FBA stock not tracked there).

    Returns dict: {total, lot_finalized, fallback_cogs, no_cogs}.
    """
    db        = get_client()
    own_wh_id = _own_wh_id()

    ch_rows   = db.table("channels").select("code, channel_id").execute().data
    ch        = {r["code"]: r["channel_id"] for r in ch_rows}
    az_id     = ch["AZ"]
    az_fbm_id = ch.get("AZ_FBM")
    az_ids    = [az_id] + ([az_fbm_id] if az_fbm_id else [])

    pending = (db.table("orders")
                 .select("order_id, platform_order_id, sku_id, channel_id, order_date, quantity")
                 .is_("cogs", "null")
                 .eq("lot_cogs_finalized", False)
                 .in_("status", ["FULFILLED", "REPLACEMENT"])
                 .in_("channel_id", az_ids)
                 .order("order_date")   # oldest first — FIFO alignment
                 .execute().data)

    # Pre-load AZ lot partner_location_ids per SKU.
    # AZ FBA lots are tagged with the Amazon FC's partner_location_id (e.g. BLR8 = 22)
    # because TRANSFER_OUT to Amazon specifies the destination WH.
    # _consume_lots_fifo needs the correct partner_location_id to find these lots.
    az_sku_locs: dict[str, list[int | None]] = {}
    az_lot_rows = (db.table("sku_cogs_lots")
                     .select("sku_id, partner_location_id")
                     .eq("channel_id", az_id)
                     .gt("qty_remaining", 0)
                     .execute().data)
    for r in az_lot_rows:
        az_sku_locs.setdefault(r["sku_id"], set()).add(r["partner_location_id"])

    lot_finalized = fallback_cogs = no_cogs = 0

    for order in pending:
        sku_id     = order["sku_id"]
        qty        = int(order["quantity"])
        channel_id = order["channel_id"]
        lot_ch     = own_wh_id if channel_id == az_fbm_id else az_id

        # For AZ FBA: pick the partner_location_id from available lots (if any).
        # FBM ships from OWN_WH which has no partner_location_id (None = IS NULL filter).
        if channel_id == az_fbm_id or lot_ch == own_wh_id:
            partner_loc_id = None
        else:
            locs = az_sku_locs.get(sku_id, set())
            partner_loc_id = next(iter(locs), None)  # first available FC; None → fallback

        plan      = None
        unit_cogs = None
        try:
            plan, unit_cogs = _consume_lots_fifo(
                db, sku_id, lot_ch, qty,
                partner_location_id=partner_loc_id,
            )
            # Update cached remaining count to reflect consumption
            if plan and partner_loc_id is not None:
                consumed = sum(p["qty"] for p in plan)
                # Refresh loc cache if this lot is now exhausted
                updated_remaining = (db.table("sku_cogs_lots")
                                       .select("partner_location_id")
                                       .eq("channel_id", az_id)
                                       .eq("sku_id", sku_id)
                                       .gt("qty_remaining", 0)
                                       .execute().data)
                az_sku_locs[sku_id] = set(r["partner_location_id"] for r in updated_remaining)
        except ValueError:
            unit_cogs = _get_sku_cogs_fallback(sku_id, db)

        if dry_run:
            src = f"lots={[p['lot_id'] for p in plan]}" if plan else "fallback"
            print(f"  {order['platform_order_id']}  {sku_id}  qty={qty}"
                  f"  date={order['order_date']}  cogs={unit_cogs}  src={src}")
            if plan:          lot_finalized += 1
            elif unit_cogs:   fallback_cogs += 1
            else:             no_cogs       += 1
            continue

        if plan:
            txn_rows = [{
                "type":            "DISPATCH",
                "sku_id":          sku_id,
                "from_channel_id": lot_ch,
                "to_channel_id":   None,
                "quantity":        p["qty"],
                "unit_cogs":       p["unit_cogs"],
                "lot_id":          p["lot_id"],
                "reference":       order["platform_order_id"],
                "notes":           "AZ lot COGS finalization",
                "created_by":      "az_cogs_finalize",
            } for p in plan]
            db.table("sku_inventory_transactions").insert(txn_rows).execute()
            lot_finalized += 1
        elif unit_cogs:
            fallback_cogs += 1
        else:
            no_cogs += 1

        db.table("orders").update({
            "cogs":               unit_cogs,
            "lot_cogs_finalized": True,
        }).eq("order_id", order["order_id"]).execute()

    return {
        "total":         len(pending),
        "lot_finalized": lot_finalized,
        "fallback_cogs": fallback_cogs,
        "no_cogs":       no_cogs,
    }


def finalize_blk_cogs(dry_run: bool = False) -> dict:
    """
    Stamp lot-based COGS on BLK FULFILLED orders that have lot_cogs_finalized=False.

    Called daily after Blinkit scraper (G2b). Consumes BLK channel sku_cogs_lots FIFO
    using supply_state (tier-1) or full channel pool (tier-2 fallback).

    Does NOT insert sku_inventory_transactions rows — TRANSFER_OUT at bulk ship time
    already recorded the stock movement.

    Returns dict: {total, finalized, fallback_used, no_cogs}.
    """
    db         = get_client()
    ch_rows    = db.table("channels").select("code, channel_id").execute().data
    blk_id     = next(r["channel_id"] for r in ch_rows if r["code"] == "BLK")

    pending = (db.table("orders")
                 .select("order_id, sku_id, quantity, supply_state, state")
                 .eq("lot_cogs_finalized", False)
                 .eq("status", "FULFILLED")
                 .eq("channel_id", blk_id)
                 .order("order_date")
                 .execute().data)

    finalized = fallback_used = no_cogs = 0

    for order in pending:
        # Use supply_state if captured; fall back to customer state as proxy
        s_state = order["supply_state"] or order["state"]
        result  = consume_sor_sale(
            sku_id=order["sku_id"],
            qty=order["quantity"],
            channel_id=blk_id,
            supply_state=s_state,
        )

        if result is None:
            no_cogs += 1
            update = {"lot_cogs_finalized": True}
        else:
            unit_cogs, lot_id = result
            cogs = round(unit_cogs * int(order["quantity"]), 2)
            update = {"cogs": cogs, "lot_cogs_finalized": True}
            if lot_id is not None:
                update["lot_id"] = lot_id
            finalized += 1
            if not order["supply_state"]:
                fallback_used += 1

        if not dry_run:
            db.table("orders").update(update).eq("order_id", order["order_id"]).execute()

    return {
        "total":        len(pending),
        "finalized":    finalized,
        "fallback_used": fallback_used,
        "no_cogs":      no_cogs,
    }


def record_dropship_sale(sku_id, qty, channel_id, selling_price,
                         order_date=None, platform_order_id=None,
                         city=None, state=None, notes="", created_by="app"):
    """
    Record a drop-ship / direct sale: dispatches inventory AND writes to orders.
    COGS from OWN_WH lots (FIFO). MRP auto-fetched from sku_pricing.
    Pass state explicitly (from pincode lookup) or it falls back to city_to_state().
    """
    db  = get_client()
    qty = int(qty)
    selling_price = float(selling_price)

    if order_date is None:
        order_date = date.today()
    order_date_str = _date_str(order_date)

    _, unit_cogs = dispatch_sku(sku_id, qty, channel_id,
                                reference=platform_order_id or "",
                                notes=notes, created_by=created_by,
                                txn_type="DISPATCH")

    mrp = _lookup_mrp(db, sku_id, order_date_str)
    discount_pct = (
        round((mrp - selling_price) / mrp * 100, 2)
        if mrp and mrp > 0 else None
    )
    state = state or city_to_state(city)

    db.table("orders").insert({
        "channel_id":        channel_id,
        "order_date":        order_date_str,
        "sku_id":            sku_id,
        "quantity":          qty,
        "mrp":               mrp,
        "selling_price":     selling_price,
        "gross_value":       round(qty * selling_price, 2),
        "discount_pct":      discount_pct,
        "cogs":              round(qty * unit_cogs, 2),
        "fulfillment_type":  "DROP_SHIP",
        "city":              city or None,
        "state":             state,
        "platform_order_id": platform_order_id or None,
        "status":            "FULFILLED",
        "source_file":       "warehouse_app",
    }).execute()


def record_outright_transfer(sku_id, qty, channel_id, reference="",
                             order_date=None, notes="", created_by="app"):
    """
    Record a bulk transfer to an OUTRIGHT channel (Peeko, Kiddo).
    Dispatches inventory AND writes to orders at catalog SP.
    SP + MRP auto-looked up from sku_pricing — blocks if SP missing.
    TP looked up from sku_channel_tp and stored as transfer_price for P&L.
    COGS from OWN_WH lots (FIFO), locked in at dispatch (lot_cogs_finalized=TRUE).
    """
    db  = get_client()
    qty = int(qty)

    if order_date is None:
        order_date = date.today()
    order_date_str = _date_str(order_date)

    pricing = (db.table("sku_pricing")
                 .select("sp, mrp")
                 .eq("sku_id", sku_id)
                 .lte("effective_date", order_date_str)
                 .order("effective_date", desc=True)
                 .limit(1).execute().data)
    if not pricing or pricing[0].get("sp") is None:
        raise ValueError(
            f"No selling price found for {sku_id} in sku_pricing — "
            "add pricing before shipping to an OUTRIGHT channel"
        )
    selling_price = float(pricing[0]["sp"])
    mrp = float(pricing[0]["mrp"]) if pricing[0].get("mrp") else None
    discount_pct = (
        round((mrp - selling_price) / mrp * 100, 2)
        if mrp and mrp > 0 else None
    )

    ch_code = (db.table("channels").select("code")
                 .eq("channel_id", channel_id).single().execute().data["code"])
    tp_row = (db.table("sku_channel_tp")
                .select("transfer_price")
                .eq("sku_id", sku_id)
                .eq("channel_code", ch_code)
                .lte("effective_date", order_date_str)
                .order("effective_date", desc=True)
                .limit(1).execute().data)
    transfer_price = float(tp_row[0]["transfer_price"]) if tp_row else None

    _, unit_cogs = dispatch_sku(sku_id, qty, channel_id,
                                reference=reference,
                                notes=notes, created_by=created_by,
                                txn_type="TRANSFER_OUT")

    db.table("orders").insert({
        "channel_id":        channel_id,
        "order_date":        order_date_str,
        "sku_id":            sku_id,
        "quantity":          qty,
        "mrp":               mrp,
        "selling_price":     selling_price,
        "gross_value":       round(qty * selling_price, 2),
        "discount_pct":      discount_pct,
        "cogs":              round(qty * unit_cogs, 2),
        "transfer_price":    transfer_price,
        "fulfillment_type":  "OUTRIGHT",
        "platform_order_id": reference or None,
        "status":            "FULFILLED",
        "source_file":       "warehouse_app",
        "lot_cogs_finalized": True,
    }).execute()


def return_sku(sku_id, qty, from_channel_id, partner_location_id=None,
               notes="", created_by="app"):
    """
    Return assembled SKU from a partner back into OWN_WH stock.
    For TRANSFER_OUT channels (SOR/FBA/OUTRIGHT): consumes partner lots and
    restores to OWN_WH lots at original COGS.
    For DISPATCH channels (end-customer RTOs): creates OWN_WH lot at fallback COGS.
    """
    db = get_client()
    own_wh_id = _own_wh_id()
    qty = int(qty)

    ch = (db.table("channels").select("business_model")
            .eq("channel_id", from_channel_id).single().execute().data)
    is_transfer_channel = ch["business_model"] in ("FBA", "SOR", "OUTRIGHT")

    if is_transfer_channel:
        try:
            plan, unit_cogs = _consume_lots_fifo(
                db, sku_id, from_channel_id, qty,
                partner_location_id=partner_location_id
            )
            for p in plan:
                _upsert_lot(db, sku_id, own_wh_id, None,
                            p["assembled_at"], p["unit_cogs"], p["qty"])
        except ValueError:
            unit_cogs = _get_sku_cogs_fallback(sku_id, db)
            _upsert_lot(db, sku_id, own_wh_id, None, date.today(), unit_cogs, qty)
    else:
        unit_cogs = _get_sku_cogs_fallback(sku_id, db)
        _upsert_lot(db, sku_id, own_wh_id, None, date.today(), unit_cogs, qty)

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

    txn = {
        "type":            "RETURN",
        "sku_id":          sku_id,
        "from_channel_id": from_channel_id,
        "to_channel_id":   own_wh_id,
        "quantity":        qty,
        "unit_cogs":       unit_cogs,
        "notes":           notes,
        "created_by":      created_by,
    }
    if partner_location_id is not None:
        txn["partner_location_id"] = partner_location_id
    db.table("sku_inventory_transactions").insert(txn).execute()

    lot_total = sum(
        r["qty_remaining"]
        for r in (
            db.table("sku_cogs_lots")
            .select("qty_remaining")
            .eq("sku_id", sku_id)
            .eq("channel_id", own_wh_id)
            .is_("partner_location_id", "null")
            .gt("qty_remaining", 0)
            .execute().data or []
        )
    )
    sku_inv_qty = (
        db.table("sku_inventory")
        .select("qty_on_hand")
        .eq("sku_id", sku_id)
        .eq("channel_id", own_wh_id)
        .execute().data or [{}]
    )[0].get("qty_on_hand", 0)
    if lot_total != sku_inv_qty:
        raise RuntimeError(
            f"COGS lot sync failed after return of {sku_id}: "
            f"lots={lot_total} but sku_inventory={sku_inv_qty}. "
            f"Return was recorded but lot update may have failed — check sku_cogs_lots."
        )


def return_item(item_id, qty, from_channel_id=None, notes="", created_by="app"):
    """
    Return individual item/packaging component to OWN_WH.
    Added to today's batch. Carries last known purchase cost.
    """
    db = get_client()
    own_wh_id = _own_wh_id()
    qty = int(qty)
    today      = date.today()
    batch_code = today.strftime("%Y%m%d")

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
        "type":            "SALE_RETURN",
        "item_id":         item_id,
        "batch_id":        batch_id,
        "from_channel_id": from_channel_id,
        "to_channel_id":   own_wh_id,
        "quantity":        qty,
        "notes":           notes,
        "created_by":      created_by,
    }).execute()


def writeoff_sku(sku_id, qty, reason, notes="", created_by="app"):
    """Write off assembled SKU qty from OWN_WH (Lost / Damaged / QC Reject).
    Consumes COGS lots FIFO."""
    db = get_client()
    own_wh_id = _own_wh_id()
    qty = int(qty)

    inv = (db.table("sku_inventory").select("sku_inv_id, qty_on_hand")
             .eq("sku_id", sku_id).eq("channel_id", own_wh_id).execute().data)
    available = inv[0]["qty_on_hand"] if inv else 0
    if available < qty:
        raise ValueError(f"Insufficient SKU stock: need {qty}, have {available}")

    _, unit_cogs = _consume_lots_fifo(db, sku_id, own_wh_id, qty)

    db.table("sku_inventory").update(
        {"qty_on_hand": available - qty, "last_updated": _now()}
    ).eq("sku_inv_id", inv[0]["sku_inv_id"]).execute()

    db.table("sku_inventory_transactions").insert({
        "type":            "ADJUSTMENT",
        "sku_id":          sku_id,
        "from_channel_id": own_wh_id,
        "quantity":        qty,
        "unit_cogs":       unit_cogs,
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
    Batch auto-created from receipt_date (YYYYMMDD). Same-date batches are merged.
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


# ── SOR sell-out lot consumption ──────────────────────────────────────────────

def _consume_from_lots(db, lots: list, qty: int) -> tuple[float, int | None]:
    """FIFO-consume qty units from an ordered lot list.
    Returns (weighted_avg_unit_cogs, lot_id) where lot_id is set only when
    the entire qty came from a single lot (unambiguous traceability); None otherwise.
    """
    remaining = qty
    total_cost = 0.0
    lots_used: list[int] = []
    for lot in lots:
        if remaining <= 0:
            break
        take = min(int(lot["qty_remaining"]), remaining)
        db.table("sku_cogs_lots").update(
            {"qty_remaining": int(lot["qty_remaining"]) - take}
        ).eq("lot_id", lot["lot_id"]).execute()
        total_cost += take * float(lot["unit_cogs"])
        remaining -= take
        lots_used.append(lot["lot_id"])
    primary_lot_id = lots_used[0] if len(lots_used) == 1 else None
    return round(total_cost / qty, 4), primary_lot_id


def consume_sor_sale(sku_id: str, qty: int, channel_id: int,
                     supply_state: str | None = None) -> tuple[float, int | None] | None:
    """
    FIFO-consume sku_cogs_lots for a confirmed SOR sell-out (Blinkit).

    Tier-1 (preferred): if supply_state given, pool all lots for partner locations
    in that state and consume FIFO. This gives state-level FIFO accuracy without
    needing the specific dark store — Blinkit WHs serve all dark stores in their state.

    Tier-2 (fallback): if tier-1 has insufficient qty, or no supply_state given,
    pool ALL lots for the channel and consume FIFO. Logs a warning when falling back.

    Returns (unit_cogs, lot_id) where lot_id is None when multiple lots were consumed.
    Returns None if even tier-2 is insufficient (logs warning, does not raise).
    """
    db = get_client()
    qty = int(qty)

    def _fetch_lots(location_ids: list | None) -> list:
        q = (db.table("sku_cogs_lots")
               .select("lot_id, assembled_at, unit_cogs, qty_remaining")
               .eq("sku_id", sku_id)
               .eq("channel_id", channel_id)
               .gt("qty_remaining", 0)
               .order("assembled_at")
               .order("lot_id"))
        if location_ids is not None:
            q = q.in_("partner_location_id", location_ids)
        return q.execute().data

    # Tier-1: state-level
    if supply_state:
        loc_rows = (db.table("partner_locations")
                      .select("location_id")
                      .eq("channel_id", channel_id)
                      .eq("state", supply_state)
                      .execute().data)
        loc_ids = [r["location_id"] for r in loc_rows]
        if loc_ids:
            lots_t1 = _fetch_lots(loc_ids)
            if sum(l["qty_remaining"] for l in lots_t1) >= qty:
                return _consume_from_lots(db, lots_t1, qty)
            logger.warning(
                "consume_sor_sale: tier-1 insufficient for %s state=%s "
                "(need %s have %s) — falling back to channel pool",
                sku_id, supply_state, qty,
                sum(l["qty_remaining"] for l in lots_t1),
            )

    # Tier-2: full channel pool
    lots_t2 = _fetch_lots(None)
    available = sum(l["qty_remaining"] for l in lots_t2)
    if available < qty:
        logger.warning(
            "consume_sor_sale: insufficient lots for %s channel_id=%s "
            "(need %s have %s) — COGS not updated for this order",
            sku_id, channel_id, qty, available,
        )
        return None
    return _consume_from_lots(db, lots_t2, qty)
