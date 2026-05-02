"""
Replenishment analysis — pulls live stock from prod DB, computes ROP and order gaps.
Also updates items table with real MOQ + lead_time_days from supplier mapping.
Run from project root: python setup/reorder_analysis.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tcb.db import get_client

db = get_client()

# ── Real supplier data from master files/Item-supplier mapping.xlsx ────────────
# {item_code: (moq, lead_time_days, supplier_name)}
SUPPLIER = {
    "TCBP00001": (250,  90, "King Enterprises"),
    "TCBP00002": (250,  90, "King Enterprises"),
    "TCBP00003": (800,  90, "King Enterprises"),
    "TCBP00004": (100,   5, "Ekta Oversees"),
    "TCBP00005": (100,  45, "Merothiya Business"),
    "TCBP00006": (250,  90, "King Enterprises"),
    "TCBP00007": (250,  90, "King Enterprises"),
    "TCBP00008": (100,   5, "Ekta Oversees"),
    "TCBP00009": (100,  45, "Merothiya Business"),
    "TCBP00010": (500,  60, "Sobhara"),
    "TCBP00011": (500,  60, "Svatanya"),
    "TCBP00012": (500,  60, "Svatanya"),
    "TCBP00013": (500,  90, "King Enterprises"),
    "TCBP00014": (500,  90, "King Enterprises"),
    "TCBP00015": (500,  60, "Sobhara"),
    "TCBP00016": (1000, 60, "Svatanya"),
    "TCBP00017": (500,  60, "Sobhara"),
    "TCBP00018": (250,  60, "Hollyhock"),       # 2025 mugs — may be discontinued
    "TCBP00019": (250,  60, "Hollyhock"),
    "TCBP00020": (500,  60, "Sobhara"),
    "TCBP00021": (500,  60, "Sobhara"),
    "TCBP00022": (250,  60, "Hollyhock"),
    "TCBP00023": (250,  60, "Hollyhock"),
    "TCBP00024": (100,  45, "Craft India"),
    "TCBP00025": (3000, 30, "N M Prints"),
    "TCBP00026": (250,  15, "N M Prints"),
    "TCBP00027": (500,  15, "N M Prints"),
    "TCBP00028": (1000, 15, "Smart Inc"),
    "TCBP00029": (500,  15, "Smart Inc"),
    "TCBP00030": (500,  15, "Smart Inc"),
    "TCBP00031": (500,  15, "Smart Inc"),
    "TCBP00032": (1000, 15, "N M Prints"),
    "TCBP00033": (500,  15, "N M Prints"),
    "TCBP00034": (500,  15, "N M Prints"),
    "TCBP00035": (500,  15, "N M Prints"),
    "TCBP00036": (500,  15, "N M Prints"),
    "TCBP00037": (500,  15, "N M Prints"),
    "TCBP00038": (500,  15, "N M Prints"),
    "TCBP00039": (500,  15, "N M Prints"),
    "TCBP00040": (1000, 15, "N M Prints"),
    "TCBP00041": (2500,  5, "G K Enterprises"),
}

# ── Step 1: Update items table with real MOQ + lead_time_days ─────────────────
print("Updating items table with real MOQ + lead times...")
items_rows = db.table("items").select("item_id, item_code").execute().data
code_to_id = {r["item_code"]: r["item_id"] for r in items_rows}

updated = 0
for code, (moq, lt, supplier) in SUPPLIER.items():
    item_id = code_to_id.get(code)
    if item_id:
        db.table("items").update({"moq": moq, "lead_time_days": lt}).eq("item_id", item_id).execute()
        updated += 1

print(f"  Updated {updated} items.\n")

# ── Step 2: March actuals — only active (non-discontinued) SKUs ───────────────
_all_march = {
    "TCB001": 20, "TCB002": 20, "TCB003": 16, "TCB004": 47,
    "TCB005": 60, "TCB006": 36, "TCB008": 24,
    "TCB009_1": 40, "TCB010": 53, "TCB011": 27, "TCB012": 20,
}

# Filter to only non-discontinued SKUs from DB
active_skus = {r["sku_id"] for r in db.table("skus").select("sku_id").eq("is_discontinued", False).execute().data}
march_sales = {sku: qty for sku, qty in _all_march.items() if sku in active_skus}

# May plan = 2× March
may_plan = {sku: qty * 2.0 for sku, qty in march_sales.items()}

# ── Step 3: Pull BOM from prod ────────────────────────────────────────────────
bom_rows = db.table("bom").select("sku_id, item_id, quantity_per_sku").execute().data

# ── Step 4: Monthly item consumption (May) ────────────────────────────────────
item_consumption = {}
for row in bom_rows:
    sku = row["sku_id"]
    item_id = row["item_id"]
    bom_qty = row["quantity_per_sku"]
    sku_sales = may_plan.get(sku, 0)
    item_consumption[item_id] = item_consumption.get(item_id, 0) + sku_sales * bom_qty

# ── Step 5: Pull all items master ────────────────────────────────────────────
items_all = db.table("items").select("item_id, item_code, name, item_type, moq, lead_time_days").execute().data
items_map = {r["item_id"]: r for r in items_all}

# ── Step 6: Pull and SUM current OWN_WH stock (multiple batches per item) ────
own_wh = db.table("channels").select("channel_id").eq("code", "OWN_WH").single().execute().data
own_wh_id = own_wh["channel_id"]

inv_rows = db.table("inventory").select("item_id, quantity_on_hand").eq("channel_id", own_wh_id).execute().data
stock_map = {}
for r in inv_rows:
    stock_map[r["item_id"]] = stock_map.get(r["item_id"], 0) + r["quantity_on_hand"]

# ── Step 7: Compute analysis ──────────────────────────────────────────────────
BUFFER_FACTOR  = 1.20   # 20% buffer on lead time
TARGET_MONTHS  = 1.5    # stock target

PRODUCT_ITEMS   = [r for r in items_all if r["item_type"] == "PRODUCT"]
PACKAGING_ITEMS = [r for r in items_all if r["item_type"] == "PACKAGING"]

def analyse(item_list, section_title):
    print(f"\n{'='*125}")
    print(f"  {section_title}")
    print(f"{'='*125}")
    hdr = f"{'Item Code':<14} {'Item Name':<42} {'Supplier':<22} {'Mo Cons':>8} {'Stock':>7} {'ROP':>7} {'Target':>8} {'Gap ROP':>8} {'MOQ':>6} {'LT':>4}  {'Action / Alert'}"
    print(hdr)
    print("-"*125)

    urgent = []
    overstock_alerts = []

    for item in sorted(item_list, key=lambda x: x["item_code"]):
        code    = item["item_code"]
        item_id = item["item_id"]
        name    = item["name"][:40]
        moq     = item["moq"]
        lt      = item["lead_time_days"]
        sup     = SUPPLIER.get(code, (None, None, "?"))[2]

        monthly = item_consumption.get(item_id, 0)
        daily   = monthly / 30.0
        rop     = daily * (lt * BUFFER_FACTOR)
        target  = monthly * TARGET_MONTHS
        stock   = stock_map.get(item_id, 0)
        gap_rop = rop - stock       # positive = below ROP (urgent)
        gap_tgt = target - stock    # positive = below target

        below_rop = stock < rop

        # Order qty: at least MOQ, enough to reach target
        order_qty = max(moq, int(target - stock)) if below_rop else 0
        if order_qty < moq and below_rop:
            order_qty = moq

        # Overstock: MOQ covers >3 months of consumption
        mo_cover = (moq / monthly) if monthly > 0 else 999

        action = ""
        flag = ""
        if below_rop:
            flag = ">>> "
            action = f"ORDER {order_qty:,}"
            if mo_cover > 3:
                action += f"  [OVERSTOCK: {mo_cover:.0f}mo/order]"
            urgent.append((code, name, sup, monthly, stock, rop, target, order_qty, moq, lt, mo_cover))
        elif monthly == 0:
            action = "UNUSED (0 consumption)"
        elif mo_cover > 3:
            months_left = stock / monthly if monthly > 0 else 999
            action = f"OK — {months_left:.1f}mo left | MOQ={moq} = {mo_cover:.0f}mo/order"
            overstock_alerts.append((code, name, moq, monthly, mo_cover, months_left))
        else:
            months_left = stock / monthly if monthly > 0 else 999
            action = f"OK — {months_left:.1f}mo left"

        print(f"{flag}{code:<14} {name:<42} {sup:<22} {monthly:>8.0f} {stock:>7,} {rop:>7.0f} {target:>8.0f} {gap_rop:>+8.0f} {moq:>6,} {lt:>4}  {action}")

    return urgent, overstock_alerts


# ── Run analysis ──────────────────────────────────────────────────────────────
urgent_prod, os_prod   = analyse(PRODUCT_ITEMS,   "PRODUCT ITEMS — Reorder Analysis (May 2026 Plan)")
urgent_pack, os_pack   = analyse(PACKAGING_ITEMS, "PACKAGING ITEMS — Reorder Analysis (May 2026 Plan)")

all_urgent    = urgent_prod + urgent_pack
all_overstock = os_prod + os_pack

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*125}")
print(f"  SUMMARY — ITEMS TO ORDER NOW ({len(all_urgent)} items)")
print(f"{'='*125}")
print(f"  {'Item':<14} {'Name':<40} {'Supplier':<22} {'Stock':>7} {'ROP':>7} {'Order':>8}  {'LT':>4}d  Notes")
print(f"  {'-'*14} {'-'*40} {'-'*22} {'-'*7} {'-'*7} {'-'*8}  {'-'*5}  {'-'*30}")
for r in sorted(all_urgent, key=lambda x: x[8] * x[9], reverse=True):  # sort by LT desc
    code, name, sup, monthly, stock, rop, target, order_qty, moq, lt, mo_cover = r
    note = f"OVERSTOCK: MOQ={moq} = {mo_cover:.0f}mo supply" if mo_cover > 3 else f"MOQ={moq}"
    print(f"  {code:<14} {name:<40} {sup:<22} {stock:>7,} {rop:>7.0f} {order_qty:>8,}  {lt:>4}d  {note}")

print(f"\n{'='*125}")
print(f"  OVERSTOCK RISK FLAGS ({len(all_overstock)} items with MOQ > 3 months supply)")
print(f"{'='*125}")
for r in all_overstock:
    code, name, moq, monthly, mo_cover, months_left = r
    print(f"  {code:<14} {name:<40} MOQ={moq:,}  Consumption={monthly:.0f}/mo  {mo_cover:.1f}mo/order  Stock covers {months_left:.1f}mo")

print(f"\n{'='*125}")
print(f"  MAY 2026 SKU PLAN (2× March actuals)")
print(f"{'='*125}")
total = 0
for sku in sorted(may_plan.keys()):
    qty = may_plan[sku]
    total += qty
    print(f"  {sku:<12} {qty:.0f} units/month")
print(f"  {'TOTAL':<12} {total:.0f} units/month")
print()
