"""
Vignesh — The Cradle Box Operations Agent
FastMCP server for Claude Desktop.

Gives Claude Desktop live access to inventory, sales, P&L, OOS risk,
and purchase orders via natural language.

Run locally:
    python mcp/server.py

Register in claude_desktop_config.json:
    {
      "mcpServers": {
        "vignesh": {
          "command": "python",
          "args": ["C:\\\\01Claude\\\\projects\\\\DemandPlanning\\\\mcp\\\\server.py"]
        }
      }
    }
"""

# ── Import FastMCP FIRST — before we add project root to sys.path.
# The project root contains an mcp/ directory that would shadow the
# installed `mcp` package if it were on sys.path at import time.
from mcp.server.fastmcp import FastMCP

import sys
from pathlib import Path

# Add project root so tcb.* imports resolve.
sys.path.insert(0, str(Path(__file__).parent.parent))

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from tcb.db import get_client, get_skus
from tcb.inventory import (
    get_assemblable,
    get_item_stock,
    get_reorder_alerts,
    receive_item,
)

mcp = FastMCP("Vignesh — TCB Ops Agent")


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _inr(val) -> str:
    if val is None:
        return "₹—"
    val = float(val)
    if abs(val) >= 1_00_000:
        return f"₹{val/1_00_000:.1f}L"
    if abs(val) >= 1_000:
        return f"₹{val/1_000:.1f}K"
    return f"₹{val:.0f}"


def _pct(num, denom) -> str:
    if not denom:
        return "—"
    return f"{100 * num / denom:.1f}%"


# ── Read-only tools ────────────────────────────────────────────────────────────

@mcp.tool()
def get_inventory_status() -> str:
    """
    Current item-level stock at the Own Warehouse (OWN_WH).
    Shows quantity, unit, reorder point, and supplier for every item.
    Also shows how many units of each SKU can be assembled right now from loose stock.
    """
    stock = get_item_stock()
    assemblable = get_assemblable()

    lines = ["## Item Stock — Own Warehouse\n"]
    lines.append(f"{'Item':<42} {'Qty':>5} {'Unit':<5} {'ROP':>4}  Supplier")
    lines.append("─" * 75)

    for item in sorted(stock.values(), key=lambda x: x["name"]):
        flag = " ⚠️" if item["qty"] < item["reorder_point"] else ""
        lines.append(
            f"{item['name']:<42} {item['qty']:>5} {item['unit']:<5} "
            f"{item['reorder_point']:>4}  {item['supplier']}{flag}"
        )

    lines.append("\n## Assemblable SKUs (from current loose stock)\n")
    lines.append(f"{'SKU':<10} {'Name':<42} {'Units':>6}")
    lines.append("─" * 62)
    for row in assemblable:
        flag = "  ⚠️ ZERO" if row["assemblable"] == 0 else ""
        lines.append(f"{row['sku_id']:<10} {row['name']:<42} {row['assemblable']:>6}{flag}")

    return "\n".join(lines)


@mcp.tool()
def get_low_stock_alerts() -> str:
    """
    Items at or below their reorder point at OWN_WH.
    Includes MOQ, lead time, and supplier — ready to draft a PO.
    """
    alerts = get_reorder_alerts()

    if not alerts:
        return "✅ All items are above their reorder points. No action needed."

    lines = [f"## Low Stock — {len(alerts)} item(s) below reorder point\n"]
    lines.append(f"{'Item':<42} {'Qty':>5} {'ROP':>5} {'Gap':>5} {'MOQ':>5} {'LT':>4}  Supplier")
    lines.append("─" * 85)

    for a in sorted(alerts, key=lambda x: x["qty"] - x["reorder_point"]):
        gap = a["qty"] - a["reorder_point"]
        lines.append(
            f"{a['name']:<42} {a['qty']:>5} {a['reorder_point']:>5} {gap:>5} "
            f"{a['moq']:>5} {a['lead_time_days']:>3}d  {a['supplier']}"
        )

    return "\n".join(lines)


@mcp.tool()
def get_oos_risk(within_days: int = 14) -> str:
    """
    SKUs at risk of going out-of-stock within the next N days (default 14).
    Uses the last 30 days of FULFILLED + PENDING orders to estimate daily velocity.
    Available supply = assemblable units from current loose item stock.

    Args:
        within_days: Alert threshold in days (default 14)
    """
    db = get_client()

    cutoff = (date.today() - timedelta(days=30)).isoformat()
    rows = (
        db.table("orders")
        .select("sku_id, quantity, status")
        .gte("order_date", cutoff)
        .in_("status", ["FULFILLED", "PENDING"])
        .execute()
        .data
    )

    # Daily velocity per SKU (units/day over last 30 days)
    raw_units: dict[str, int] = defaultdict(int)
    for r in rows:
        raw_units[r["sku_id"]] += r["quantity"] or 0
    velocity = {sku: round(units / 30, 3) for sku, units in raw_units.items()}

    assemblable = {r["sku_id"]: r["assemblable"] for r in get_assemblable()}
    skus        = {r["sku_id"]: r["name"] for r in get_skus()}

    risks = []
    for sku_id, vel in velocity.items():
        if vel <= 0:
            continue
        stock      = assemblable.get(sku_id, 0)
        days_cover = round(stock / vel, 1)
        risks.append({
            "sku_id":     sku_id,
            "name":       skus.get(sku_id, sku_id),
            "stock":      stock,
            "daily_vel":  vel,
            "days_cover": days_cover,
        })
    risks.sort(key=lambda x: x["days_cover"])

    critical = [r for r in risks if r["days_cover"] < within_days]

    header = f"{'SKU':<10} {'Name':<36} {'Stock':>6} {'Vel/d':>6} {'Days':>6}"
    rule   = "─" * 68

    lines = []
    if critical:
        lines.append(f"## 🔴 OOS Risk — {len(critical)} SKU(s) within {within_days} days\n")
        lines.append(header)
        lines.append(rule)
        for r in critical:
            icon = "🔴" if r["stock"] == 0 else ("🟡" if r["days_cover"] < 7 else "🟠")
            lines.append(
                f"{r['sku_id']:<10} {r['name']:<36} {r['stock']:>6} "
                f"{r['daily_vel']:>6.2f} {r['days_cover']:>6.1f}  {icon}"
            )
        lines.append("")

    lines.append(f"## All SKUs — days of cover (last 30d velocity)\n")
    lines.append(header)
    lines.append(rule)
    for r in risks:
        lines.append(
            f"{r['sku_id']:<10} {r['name']:<36} {r['stock']:>6} "
            f"{r['daily_vel']:>6.2f} {r['days_cover']:>6.1f}"
        )

    no_vel = [sid for sid in skus if sid not in velocity]
    if no_vel:
        lines.append(f"\nNo orders in last 30 days: {', '.join(sorted(no_vel))}")

    return "\n".join(lines)


@mcp.tool()
def get_sales_summary(
    start_date: str = "",
    end_date: str = "",
    channel: str = "",
    sku_id: str = "",
) -> str:
    """
    Sales summary — revenue and units by channel and SKU for a date range.

    Args:
        start_date: YYYY-MM-DD (default: first day of current month)
        end_date:   YYYY-MM-DD (default: today)
        channel:    Filter by channel name, partial match OK (e.g. "Amazon", "Blinkit")
        sku_id:     Filter to a single SKU (e.g. "TCB005")
    """
    db = get_client()

    sd = start_date or date.today().replace(day=1).isoformat()
    ed = end_date   or date.today().isoformat()

    q = (
        db.table("orders")
        .select("channel_id, sku_id, quantity, gross_value, city, status")
        .gte("order_date", sd)
        .lte("order_date", ed)
        .neq("status", "CANCELLED")
    )
    if sku_id:
        q = q.eq("sku_id", sku_id.upper())
    rows = q.execute().data

    if not rows:
        return f"No orders found between {sd} and {ed}."

    channels = {r["channel_id"]: r["name"] for r in db.table("channels").select("channel_id, name").execute().data}
    skus     = {r["sku_id"]:     r["name"] for r in db.table("skus").select("sku_id, name").execute().data}

    if channel:
        ch_lower  = channel.lower()
        ok_ids    = {cid for cid, cname in channels.items() if ch_lower in cname.lower()}
        rows      = [r for r in rows if r["channel_id"] in ok_ids]
        if not rows:
            return f"No orders for channel matching '{channel}' between {sd} and {ed}."

    RETURN_STATUSES = {"RTO", "SALE_RETURN"}

    by_ch:   dict[str, dict] = defaultdict(lambda: {"units": 0, "revenue": 0.0, "returns": 0})
    by_sku:  dict[str, dict] = defaultdict(lambda: {"units": 0, "revenue": 0.0, "returns": 0})
    by_city: dict[str, dict] = defaultdict(lambda: {"units": 0, "revenue": 0.0})

    for r in rows:
        ch_name = channels.get(r["channel_id"], str(r["channel_id"]))
        sk_key  = r["sku_id"]
        city    = r.get("city") or "Unknown"
        qty     = r["quantity"] or 0
        rev     = float(r["gross_value"] or 0)
        is_ret  = r["status"] in RETURN_STATUSES

        by_ch[ch_name]["units"]   += qty
        by_ch[ch_name]["revenue"] += rev
        if is_ret:
            by_ch[ch_name]["returns"] += qty

        by_sku[sk_key]["units"]   += qty
        by_sku[sk_key]["revenue"] += rev
        if is_ret:
            by_sku[sk_key]["returns"] += qty

        by_city[city]["units"]   += qty
        by_city[city]["revenue"] += rev

    total_units = sum(v["units"]   for v in by_ch.values())
    total_rev   = sum(v["revenue"] for v in by_ch.values())

    lines = [f"## Sales Summary: {sd} → {ed}\n"]
    lines.append(f"**Total:** {total_units} units | Revenue: {_inr(total_rev)}\n")

    lines.append("### By Channel\n")
    lines.append(f"{'Channel':<25} {'Units':>6} {'Revenue':>10} {'Returns':>8}")
    lines.append("─" * 55)
    for ch, v in sorted(by_ch.items(), key=lambda x: -x[1]["revenue"]):
        lines.append(f"{ch:<25} {v['units']:>6} {_inr(v['revenue']):>10} {v['returns']:>8}")

    lines.append("\n### By SKU\n")
    lines.append(f"{'SKU':<10} {'Name':<38} {'Units':>6} {'Revenue':>10} {'Returns':>8}")
    lines.append("─" * 76)
    for sk, v in sorted(by_sku.items(), key=lambda x: -x[1]["revenue"]):
        name = skus.get(sk, sk)
        lines.append(f"{sk:<10} {name:<38} {v['units']:>6} {_inr(v['revenue']):>10} {v['returns']:>8}")

    lines.append("\n### By City (top 20)\n")
    lines.append(f"{'City':<25} {'Units':>6} {'Revenue':>10}")
    lines.append("─" * 45)
    for city, v in sorted(by_city.items(), key=lambda x: -x[1]["units"])[:20]:
        lines.append(f"{city:<25} {v['units']:>6} {_inr(v['revenue']):>10}")

    return "\n".join(lines)


@mcp.tool()
def get_channel_pnl(months: int = 3) -> str:
    """
    P&L by channel for the last N months (default 3).
    Shows units, revenue, COGS, commission, ad spend, and net margin per channel.

    Args:
        months: Number of past months to include (default 3)
    """
    from dateutil.relativedelta import relativedelta

    cutoff = (date.today() - relativedelta(months=months)).strftime("%Y-%m-01")
    rows   = (
        get_client()
        .table("v_monthly_mis")
        .select("*")
        .gte("month", cutoff)
        .execute()
        .data
    )

    if not rows:
        return f"No P&L data for the last {months} months."

    by_ch: dict[str, dict] = defaultdict(lambda: {
        "units": 0, "returns": 0, "revenue": 0.0, "cogs": 0.0,
        "commission": 0.0, "logistics": 0.0, "ad_spend": 0.0, "nm": 0.0,
    })

    for r in rows:
        ch = r["channel"]
        by_ch[ch]["units"]      += int(r.get("units_sold")        or 0)
        by_ch[ch]["returns"]    += int(r.get("units_returned")     or 0)
        by_ch[ch]["revenue"]    += float(r.get("gross_revenue")    or 0)
        by_ch[ch]["cogs"]       += float(r.get("total_cogs")       or 0)
        by_ch[ch]["commission"] += float(r.get("total_commission") or 0)
        by_ch[ch]["logistics"]  += float(r.get("total_logistics")  or 0)
        by_ch[ch]["ad_spend"]   += float(r.get("total_ad_spend")   or 0)
        by_ch[ch]["nm"]         += float(r.get("total_net_margin") or 0)

    grand_rev = sum(v["revenue"] for v in by_ch.values())
    grand_nm  = sum(v["nm"]      for v in by_ch.values())

    lines = [f"## Channel P&L — Last {months} Months\n"]
    lines.append(
        f"**Grand total:** {_inr(grand_rev)} revenue | "
        f"Net margin: {_inr(grand_nm)} ({_pct(grand_nm, grand_rev)})\n"
    )

    for ch, v in sorted(by_ch.items(), key=lambda x: -x[1]["revenue"]):
        rev = v["revenue"]
        nm  = v["nm"]
        ret_rate = _pct(v["returns"], v["units"])
        icon = "✅" if nm >= 0 else "🔴"
        lines.append(f"### {icon} {ch}")
        lines.append(f"  Units sold: {v['units']}  |  Returns: {v['returns']} ({ret_rate})")
        lines.append(f"  Revenue:    {_inr(rev)}")
        lines.append(f"  COGS:       {_inr(v['cogs'])}  ({_pct(v['cogs'], rev)})")
        lines.append(f"  Commission: {_inr(v['commission'])}  ({_pct(v['commission'], rev)})")
        lines.append(f"  Ad Spend:   {_inr(v['ad_spend'])}  ({_pct(v['ad_spend'], rev)})")
        lines.append(f"  Logistics:  {_inr(v['logistics'])}  ({_pct(v['logistics'], rev)})")
        lines.append(f"  Net Margin: **{_inr(nm)}  ({_pct(nm, rev)})**")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def get_return_summary(months: int = 3) -> str:
    """
    Return rates and breakdown by channel, SKU, return reason, and responsible party.

    Args:
        months: Number of past months to include (default 3)
    """
    from dateutil.relativedelta import relativedelta

    db     = get_client()
    cutoff = (date.today() - relativedelta(months=months)).strftime("%Y-%m-%d")

    rows = (
        db.table("orders")
        .select("channel_id, sku_id, quantity, status, return_reason, return_responsible")
        .gte("order_date", cutoff)
        .in_("status", ["FULFILLED", "RTO", "SALE_RETURN", "REPLACEMENT", "PENDING"])
        .execute()
        .data
    )

    if not rows:
        return "No orders found."

    channels = {r["channel_id"]: r["name"] for r in db.table("channels").select("channel_id, name").execute().data}
    skus     = {r["sku_id"]:     r["name"] for r in db.table("skus").select("sku_id, name").execute().data}

    RETURN_STATUSES = {"RTO", "SALE_RETURN"}

    by_ch:          dict[str, dict] = defaultdict(lambda: {"total": 0, "returned": 0})
    by_sku:         dict[str, dict] = defaultdict(lambda: {"total": 0, "returned": 0})
    by_reason:      dict[str, int]  = defaultdict(int)
    by_responsible: dict[str, int]  = defaultdict(int)

    for r in rows:
        ch     = channels.get(r["channel_id"], str(r["channel_id"]))
        sk     = r["sku_id"]
        qty    = r["quantity"] or 0
        is_ret = r["status"] in RETURN_STATUSES

        by_ch[ch]["total"]   += qty
        by_sku[sk]["total"]  += qty
        if is_ret:
            by_ch[ch]["returned"]   += qty
            by_sku[sk]["returned"]  += qty
            if r.get("return_reason"):
                by_reason[r["return_reason"]] += qty
            if r.get("return_responsible"):
                by_responsible[r["return_responsible"]] += qty

    lines = [f"## Returns — Last {months} Months\n"]

    lines.append("### By Channel\n")
    lines.append(f"{'Channel':<25} {'Total':>7} {'Returns':>8} {'Rate':>7}")
    lines.append("─" * 52)
    for ch, v in sorted(by_ch.items(), key=lambda x: -x[1]["total"]):
        lines.append(
            f"{ch:<25} {v['total']:>7} {v['returned']:>8} {_pct(v['returned'], v['total']):>7}"
        )

    lines.append("\n### By SKU (sorted by return volume)\n")
    lines.append(f"{'SKU':<10} {'Name':<38} {'Total':>7} {'Returns':>8} {'Rate':>7}")
    lines.append("─" * 75)
    for sk, v in sorted(by_sku.items(), key=lambda x: -x[1]["returned"])[:20]:
        name = skus.get(sk, sk)
        lines.append(
            f"{sk:<10} {name:<38} {v['total']:>7} {v['returned']:>8} {_pct(v['returned'], v['total']):>7}"
        )

    if by_reason:
        lines.append("\n### Return Reasons\n")
        for reason, qty in sorted(by_reason.items(), key=lambda x: -x[1]):
            lines.append(f"  {reason}: {qty} units")

    if by_responsible:
        lines.append("\n### Responsible Party\n")
        for party, qty in sorted(by_responsible.items(), key=lambda x: -x[1]):
            lines.append(f"  {party}: {qty} units")

    return "\n".join(lines)


@mcp.tool()
def get_po_status() -> str:
    """
    All open purchase orders (DRAFT, SENT, CONFIRMED, PARTIAL) with their line items.
    """
    db  = get_client()
    pos = (
        db.table("purchase_orders")
        .select("*, suppliers(name)")
        .in_("status", ["DRAFT", "SENT", "CONFIRMED", "PARTIAL"])
        .order("created_date", desc=True)
        .execute()
        .data
    )

    if not pos:
        return "No open purchase orders."

    lines = [f"## Open Purchase Orders ({len(pos)})\n"]

    for po in pos:
        supplier = (po.get("suppliers") or {}).get("name", "Unknown")
        lines.append(f"### PO {po['po_number']} — {supplier}  [{po['status']}]")
        lines.append(f"  Created: {po['created_date']}  |  Expected: {po.get('expected_date') or 'TBD'}")
        if po.get("total_value"):
            lines.append(
                f"  Value: {_inr(po['total_value'])}  |  Advance: {_inr(po.get('advance_paid', 0))}  |  Balance: {_inr(po.get('balance_due', 0))}"
            )
        if po.get("notes"):
            lines.append(f"  Notes: {po['notes']}")

        items = (
            db.table("purchase_order_items")
            .select("*, items(name, unit)")
            .eq("po_id", po["po_id"])
            .execute()
            .data
        )
        if items:
            lines.append(f"\n  {'Item':<40} {'Ord':>6} {'Rcvd':>6} {'Cost/u':>8} {'Total':>10}")
            lines.append("  " + "─" * 74)
            for it in items:
                name = (it.get("items") or {}).get("name", str(it["item_id"]))
                unit = (it.get("items") or {}).get("unit", "")
                lines.append(
                    f"  {name:<40} {it['quantity_ordered']:>5}{unit:<2} "
                    f"{it['quantity_received']:>6} {_inr(it.get('cost_per_unit', 0)):>8} "
                    f"{_inr(it.get('line_total', 0)):>10}"
                )
        lines.append("")

    return "\n".join(lines)


# ── Write tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def create_purchase_order(
    supplier_name: str,
    items: list[dict[str, Any]],
    expected_date: str = "",
    notes: str = "",
) -> str:
    """
    Create a DRAFT purchase order for a supplier and save it to the database.

    Args:
        supplier_name: Supplier name, partial match OK (e.g. "Ram Textiles", "Shubhra")
        items:         List of items to order. Each item must have:
                         - "item_code": string (e.g. "ITM001")
                         - "qty":       integer
                         - "cost_per_unit": float in ₹
                       Example: [{"item_code": "ITM003", "qty": 100, "cost_per_unit": 45.0}]
        expected_date: Expected delivery date as YYYY-MM-DD (optional)
        notes:         Free-text notes for the supplier (optional)

    Returns: PO number and line-item confirmation.
    """
    db = get_client()

    # Resolve supplier
    suppliers = (
        db.table("suppliers")
        .select("supplier_id, name")
        .ilike("name", f"%{supplier_name}%")
        .execute()
        .data
    )
    if not suppliers:
        return f"No supplier found matching '{supplier_name}'. Check the name and try again."
    if len(suppliers) > 1:
        names = ", ".join(s["name"] for s in suppliers)
        return f"Multiple suppliers match '{supplier_name}': {names}\nBe more specific."
    supplier = suppliers[0]

    # Resolve items
    all_items = {
        r["item_code"]: r
        for r in db.table("items").select("item_id, item_code, name, unit").execute().data
    }

    resolved, errors = [], []
    for it in items:
        code = str(it.get("item_code", "")).upper()
        if not code:
            errors.append("One item is missing 'item_code'")
            continue
        if code not in all_items:
            errors.append(f"Item code '{code}' not found — use get_inventory_status to check codes")
            continue
        qty = int(it.get("qty", 0))
        cpu = float(it.get("cost_per_unit", 0))
        if qty <= 0:
            errors.append(f"'{code}': qty must be > 0")
            continue
        item_row = all_items[code]
        resolved.append({
            "item_id":          item_row["item_id"],
            "name":             item_row["name"],
            "unit":             item_row["unit"],
            "quantity_ordered": qty,
            "cost_per_unit":    cpu,
            "line_total":       round(qty * cpu, 2),
        })

    if errors:
        return "Cannot create PO. Fix these errors:\n" + "\n".join(f"  • {e}" for e in errors)
    if not resolved:
        return "No valid items provided."

    total_value = round(sum(r["line_total"] for r in resolved), 2)

    # Generate sequential PO number for today
    today_str = date.today().strftime("%Y%m%d")
    existing  = (
        db.table("purchase_orders")
        .select("po_number")
        .like("po_number", f"PO-{today_str}-%")
        .execute()
        .data
    )
    po_number = f"PO-{today_str}-{len(existing) + 1:03d}"

    po_row = (
        db.table("purchase_orders")
        .insert({
            "po_number":     po_number,
            "supplier_id":   supplier["supplier_id"],
            "expected_date": expected_date or None,
            "status":        "DRAFT",
            "total_value":   total_value,
            "balance_due":   total_value,
            "notes":         notes or None,
        })
        .execute()
        .data
    )
    po_id = po_row[0]["po_id"]

    for it in resolved:
        db.table("purchase_order_items").insert({
            "po_id":             po_id,
            "item_id":           it["item_id"],
            "quantity_ordered":  it["quantity_ordered"],
            "cost_per_unit":     it["cost_per_unit"],
            "line_total":        it["line_total"],
            "quantity_received": 0,
        }).execute()

    # Verify both rows exist
    item_count = len(
        db.table("purchase_order_items").select("poi_id").eq("po_id", po_id).execute().data
    )
    if item_count != len(resolved):
        return (
            f"⚠️ PO {po_number} was created (po_id={po_id}) but only {item_count}/{len(resolved)} "
            "line items saved. Check purchase_order_items manually."
        )

    lines = [f"## ✅ PO Created: {po_number}\n"]
    lines.append(f"**Supplier:** {supplier['name']}")
    lines.append(f"**Status:**   DRAFT")
    lines.append(f"**Expected:** {expected_date or 'TBD'}")
    lines.append(f"**Total:**    {_inr(total_value)}")
    if notes:
        lines.append(f"**Notes:**   {notes}")
    lines.append(f"\n{'Item':<42} {'Qty':>6} {'Unit':<5} {'Cost/u':>8} {'Total':>10}")
    lines.append("─" * 75)
    for it in resolved:
        lines.append(
            f"{it['name']:<42} {it['quantity_ordered']:>6} {it['unit']:<5} "
            f"{_inr(it['cost_per_unit']):>8} {_inr(it['line_total']):>10}"
        )
    lines.append(f"\nPO saved as DRAFT. Mark as SENT once you share it with {supplier['name']}.")

    return "\n".join(lines)


@mcp.tool()
def record_stock_receipt(
    item_code: str,
    qty: int,
    cost_per_unit: float,
    receipt_date: str = "",
    notes: str = "",
) -> str:
    """
    Record inward receipt of items into the Own Warehouse.
    Updates inventory and creates a batch record. Same-day receipts of the same item are merged.

    Args:
        item_code:     Item code (e.g. "ITM001") — use get_inventory_status to look up codes
        qty:           Number of units received
        cost_per_unit: Cost per unit in ₹
        receipt_date:  YYYY-MM-DD (default: today)
        notes:         Optional notes (e.g. PO number, supplier invoice)
    """
    db = get_client()

    item_code = item_code.upper()
    item_rows = (
        db.table("items")
        .select("item_id, name, unit")
        .eq("item_code", item_code)
        .execute()
        .data
    )
    if not item_rows:
        return f"Item '{item_code}' not found. Use get_inventory_status to check item codes."

    item = item_rows[0]

    recv_date = None
    if receipt_date:
        recv_date = datetime.strptime(receipt_date, "%Y-%m-%d").date()

    stock_before = get_item_stock().get(item["item_id"], {}).get("qty", 0)

    batch_id = receive_item(
        item_id=item["item_id"],
        qty=qty,
        cost_per_unit=cost_per_unit,
        receipt_date=recv_date,
        notes=notes,
        created_by="vignesh_mcp",
    )

    stock_after = get_item_stock().get(item["item_id"], {}).get("qty", 0)

    return (
        f"## ✅ Stock Receipt Recorded\n\n"
        f"**Item:**      {item['name']} ({item_code})\n"
        f"**Received:**  {qty} {item['unit']}\n"
        f"**Cost/unit:** {_inr(cost_per_unit)}\n"
        f"**Total cost:** {_inr(qty * cost_per_unit)}\n"
        f"**Date:**      {receipt_date or date.today().isoformat()}\n"
        f"**Batch ID:**  {batch_id}\n\n"
        f"Stock: {stock_before} → {stock_after} {item['unit']}"
    )


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
