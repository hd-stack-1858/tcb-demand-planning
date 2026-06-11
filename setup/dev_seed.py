"""
Dev DB seed script — self-contained, no Excel files needed.
Seeds all reference data + dummy inventory quantities.
Run after dev_schema.sql has been executed in Supabase SQL Editor.

Usage:
  python setup/dev_seed.py
(with .env pointing to your DEV Supabase project)
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tcb.db import get_client
from datetime import date

db = get_client()

def upsert(table, rows, conflict_col):
    for row in rows:
        db.table(table).upsert(row, on_conflict=conflict_col).execute()
    print(f"  {table}: {len(rows)} rows")

def insert_ignore(table, rows, conflict_col):
    for row in rows:
        db.table(table).upsert(row, on_conflict=conflict_col).execute()
    print(f"  {table}: {len(rows)} rows")


# ── 1. CHANNELS ───────────────────────────────────────────────────────────────
print("Seeding channels...")
upsert("channels", [
    {"name": "Own Warehouse",  "code": "OWN_WH",    "business_model": None,        "fulfillment_from": "OWN_WH",              "is_location": True,  "is_active": True,  "legal_name": "Goodsense Trading India Private Limited"},
    {"name": "Amazon",         "code": "AZ",        "business_model": "SOR",       "fulfillment_from": "FBA",                 "is_location": False, "is_active": True,  "legal_name": "Amazon Seller Services Private Limited"},
    {"name": "Amazon FBM",     "code": "AZ_FBM",    "business_model": "DROP_SHIP", "fulfillment_from": "OWN_WH",              "is_location": False, "is_active": True,  "legal_name": "Amazon Seller Services Private Limited"},
    {"name": "Blinkit",        "code": "BLK",       "business_model": "SOR",       "fulfillment_from": "BLK_DARKSTORE",       "is_location": False, "is_active": True,  "legal_name": "Blink Commerce Private Limited"},
    {"name": "Ferns & Petals", "code": "FNP",       "business_model": "DROP_SHIP", "fulfillment_from": "OWN_WH",              "is_location": False, "is_active": True,  "legal_name": "FNP E Retail Private Limited"},
    {"name": "First Cry",      "code": "FC",        "business_model": "DROP_SHIP", "fulfillment_from": "OWN_WH",              "is_location": False, "is_active": True,  "legal_name": "Digital Age Retail Private Limited"},
    {"name": "Peeko",          "code": "PEEKO",     "business_model": "OUTRIGHT",  "fulfillment_from": "PEEKO_DARKSTORE",     "is_location": False, "is_active": True,  "legal_name": "Zippycubs Private Limited"},
    {"name": "Ozi",            "code": "OZI",       "business_model": "SOR",       "fulfillment_from": "OZI_DARKSTORE",       "is_location": False, "is_active": True,  "legal_name": "Ozi Technologies Private Limited"},
    {"name": "Kiddo",          "code": "KIDDO",     "business_model": "OUTRIGHT",  "fulfillment_from": "KIDDO_DARKSTORE",     "is_location": False, "is_active": True,  "legal_name": "Babyswift Private Limited"},
    {"name": "Own Website",    "code": "D2C",       "business_model": "DIRECT",    "fulfillment_from": "OWN_WH",              "is_location": False, "is_active": True,  "legal_name": "Goodsense Trading India Private Limited"},
    {"name": "Zepto",          "code": "ZEPTO",     "business_model": None,        "fulfillment_from": "ZEPTO_DARKSTORE",     "is_location": False, "is_active": False, "legal_name": "Zepto Private Limited"},
    {"name": "Instamart",      "code": "INSTAMART", "business_model": None,        "fulfillment_from": "INSTAMART_DARKSTORE", "is_location": False, "is_active": False, "legal_name": "Swiggy Instamart Private Limited"},
], "code")

# ── 2. SKUs ───────────────────────────────────────────────────────────────────
print("Seeding SKUs...")
upsert("skus", [
    {"sku_id": "TCB001",   "name": "Tiny Splash Hamper Pink (5pcs)",      "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": False},
    {"sku_id": "TCB002",   "name": "Tiny Splash Hamper Blue (5pcs)",      "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": False},
    {"sku_id": "TCB003",   "name": "Little Looker Hamper (6pcs)",         "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": False},
    {"sku_id": "TCB004",   "name": "Cosy Cub (5pcs)",                     "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": False},
    {"sku_id": "TCB005",   "name": "Growing Joy 0-6 Months",              "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": False},
    {"sku_id": "TCB006",   "name": "Growing Joy 7-12 Months",             "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": False},
    {"sku_id": "TCB007",   "name": "Welcome to Us Hamper (4pcs)",         "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": True,  "discontinued_note": "Good quality photo frame could not be procured"},
    {"sku_id": "TCB008",   "name": "Just Arrived Hamper – Bunny (2pcs)",  "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": False},
    {"sku_id": "TCB009",   "name": "Hello Parenthood Hamper (2 mugs)",    "hsn_code": "69120010", "gst_pct": 5.0, "is_discontinued": True,  "discontinued_note": "Replaced by TCB009_1 (2026 mugs)"},
    {"sku_id": "TCB009_1", "name": "Hello Parenthood Hamper 2026 (2pcs)", "hsn_code": "69120010", "gst_pct": 5.0, "is_discontinued": False},
    {"sku_id": "TCB010",   "name": "Growing Joy 0-12 Months (12pcs)",     "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": False},
    {"sku_id": "TCB011",   "name": "Just Arrived Hamper – Bear (2pcs)",   "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": False},
    {"sku_id": "TCB012",   "name": "Little Looker Hamper (4pcs)",         "hsn_code": "61112000", "gst_pct": 5.0, "is_discontinued": False},
], "sku_id")

# ── 3. SUPPLIERS ──────────────────────────────────────────────────────────────
print("Seeding suppliers...")
upsert("suppliers", [
    {"name": "Sunrise Textiles",      "city": "Tirupur",   "lead_time_days": 10, "moq": 50, "payment_terms": "50% advance, 50% on dispatch"},
    {"name": "Craftworks Handicrafts","city": "Jaipur",    "lead_time_days": 14, "moq": 20, "payment_terms": "100% advance"},
    {"name": "Earthen Pottery Co.",   "city": "Khurja",    "lead_time_days": 7,  "moq": 24, "payment_terms": "100% advance"},
    {"name": "WoodWorks Studio",      "city": "Jodhpur",   "lead_time_days": 12, "moq": 30, "payment_terms": "50% advance, 50% on dispatch"},
    {"name": "PackRight Solutions",   "city": "Bengaluru", "lead_time_days": 5,  "moq": 100,"payment_terms": "Net 15"},
], "name")

sup = {r["name"]: r["supplier_id"]
       for r in db.table("suppliers").select("supplier_id,name").execute().data}

# ── 4. ITEMS ──────────────────────────────────────────────────────────────────
print("Seeding items...")
# fmt: (item_code, name, item_type, unit, reorder_point, supplier_name)
ITEMS = [
    # ── Bath products (TCB001 / TCB002) ──
    ("TCBP00001", "Hooded Towel – Pink",              "PRODUCT",   "piece", 15, "Sunrise Textiles"),
    ("TCBP00002", "Hooded Towel – Blue",              "PRODUCT",   "piece", 15, "Sunrise Textiles"),
    ("TCBP00003", "Muslin Washcloth",                 "PRODUCT",   "piece", 20, "Sunrise Textiles"),
    ("TCBP00004", "Wooden Hairbrush",                 "PRODUCT",   "piece", 15, "WoodWorks Studio"),
    ("TCBP00005", "Shower Cap – Baby",                "PRODUCT",   "piece", 15, "Craftworks Handicrafts"),
    ("TCBP00006", "Wooden Rattle Toy",                "PRODUCT",   "piece", 15, "WoodWorks Studio"),
    # ── Clothing basics (TCB003 / TCB012) ──
    ("TCBP00007", "Cotton T-Shirt – Newborn",         "PRODUCT",   "piece", 20, "Sunrise Textiles"),
    ("TCBP00008", "Cotton Pajama – Newborn",          "PRODUCT",   "piece", 20, "Sunrise Textiles"),
    ("TCBP00009", "Muslin Swaddle Blanket",           "PRODUCT",   "piece", 15, "Sunrise Textiles"),
    ("TCBP00010", "T-Shirt + Pajama + Cap + Mittens", "PRODUCT",   "set",   10, "Sunrise Textiles"),
    # ── Cosy Cub (TCB004) ──
    ("TCBP00011", "Bear-Embroidered Romper",          "PRODUCT",   "piece", 15, "Sunrise Textiles"),
    ("TCBP00012", "Bear Cap",                         "PRODUCT",   "piece", 20, "Sunrise Textiles"),
    ("TCBP00013", "Baby Mittens",                     "PRODUCT",   "piece", 20, "Sunrise Textiles"),
    ("TCBP00014", "Crocheted Bear Rattle",            "PRODUCT",   "piece", 15, "Craftworks Handicrafts"),
    ("TCBP00015", "Romper + Cap + Mittens",           "PRODUCT",   "set",   10, "Sunrise Textiles"),
    # ── Growing Joy series ──
    ("TCBP00020", "Milestone T-Shirt Set 0-6M",       "PRODUCT",   "set",   15, "Sunrise Textiles"),
    ("TCBP00021", "Milestone T-Shirt Set 7-12M",      "PRODUCT",   "set",   15, "Sunrise Textiles"),
    # ── Just Arrived range (TCB008 / TCB011) ──
    ("TCBP00030", "Cotton Just Arrived T-Shirt",      "PRODUCT",   "piece", 20, "Sunrise Textiles"),
    ("TCBP00031", "Crocheted Bunny Pip",              "PRODUCT",   "piece", 15, "Craftworks Handicrafts"),
    ("TCBP00032", "Crocheted Bear Tumble",            "PRODUCT",   "piece", 15, "Craftworks Handicrafts"),
    # ── Parenthood mugs (TCB009_1) ──
    ("TCBP00040", "Mommy Est. 2026 Ceramic Mug",      "PRODUCT",   "piece", 12, "Earthen Pottery Co."),
    ("TCBP00041", "Daddy Est. 2026 Ceramic Mug",      "PRODUCT",   "piece", 12, "Earthen Pottery Co."),
    # ── Long-sleeve tee for TCB012 ──
    ("TCBP00050", "Cotton Long-Sleeve Tee – Newborn", "PRODUCT",   "piece", 15, "Sunrise Textiles"),
    # ── Growing Joy full year (TCB010) ──
    ("TCBP00060", "Milestone T-Shirt Set 0-12M",      "PRODUCT",   "set",   10, "Sunrise Textiles"),
    # ── Packaging (shared across all SKUs) ──
    ("TCBK00001", "Keepsake Gift Box – Large",        "PACKAGING", "piece", 30, "PackRight Solutions"),
    ("TCBK00002", "Keepsake Gift Box – Medium",       "PACKAGING", "piece", 30, "PackRight Solutions"),
    ("TCBK00003", "Hello Sweet Baby Gift Card",       "PACKAGING", "piece", 50, "PackRight Solutions"),
    ("TCBK00004", "Tissue Paper Set",                 "PACKAGING", "piece", 50, "PackRight Solutions"),
    ("TCBK00005", "Raffia / Filler Paper",            "PACKAGING", "piece", 50, "PackRight Solutions"),
    ("TCBK00006", "Ribbon Tie",                       "PACKAGING", "piece", 50, "PackRight Solutions"),
]

items_rows = []
for item_code, name, itype, unit, rp, supplier_name in ITEMS:
    items_rows.append({
        "item_code":      item_code,
        "name":           name,
        "item_type":      itype,
        "unit":           unit,
        "reorder_point":  rp,
        "safety_stock":   rp // 2,
        "latest_supplier_id": sup.get(supplier_name),
        "lead_time_days": 14 if supplier_name in ("Craftworks Handicrafts", "WoodWorks Studio") else 7,
        "moq":            1,
        "is_active":      True,
    })
upsert("items", items_rows, "item_code")

item_map = {r["item_code"]: r["item_id"]
            for r in db.table("items").select("item_id,item_code").execute().data}

# ── 5. BOM ────────────────────────────────────────────────────────────────────
print("Seeding BOM...")
# Each entry: (sku_id, item_code, qty)
BOM = [
    # TCB001 — Tiny Splash Pink
    ("TCB001", "TCBP00001", 1), ("TCB001", "TCBP00003", 1), ("TCB001", "TCBP00004", 1),
    ("TCB001", "TCBP00005", 1), ("TCB001", "TCBP00006", 1),
    ("TCB001", "TCBK00001", 1), ("TCB001", "TCBK00003", 1), ("TCB001", "TCBK00004", 1),
    ("TCB001", "TCBK00005", 1), ("TCB001", "TCBK00006", 1),
    # TCB002 — Tiny Splash Blue
    ("TCB002", "TCBP00002", 1), ("TCB002", "TCBP00003", 1), ("TCB002", "TCBP00004", 1),
    ("TCB002", "TCBP00005", 1), ("TCB002", "TCBP00006", 1),
    ("TCB002", "TCBK00001", 1), ("TCB002", "TCBK00003", 1), ("TCB002", "TCBK00004", 1),
    ("TCB002", "TCBK00005", 1), ("TCB002", "TCBK00006", 1),
    # TCB003 — Little Looker 6pcs
    ("TCB003", "TCBP00007", 1), ("TCB003", "TCBP00008", 1), ("TCB003", "TCBP00009", 1),
    ("TCB003", "TCBP00012", 1), ("TCB003", "TCBP00013", 1), ("TCB003", "TCBP00014", 1),
    ("TCB003", "TCBK00001", 1), ("TCB003", "TCBK00003", 1), ("TCB003", "TCBK00004", 1),
    ("TCB003", "TCBK00005", 1), ("TCB003", "TCBK00006", 1),
    # TCB004 — Cosy Cub
    ("TCB004", "TCBP00011", 1), ("TCB004", "TCBP00012", 1), ("TCB004", "TCBP00013", 1),
    ("TCB004", "TCBP00009", 1), ("TCB004", "TCBP00014", 1),
    ("TCB004", "TCBK00001", 1), ("TCB004", "TCBK00003", 1), ("TCB004", "TCBK00004", 1),
    ("TCB004", "TCBK00005", 1), ("TCB004", "TCBK00006", 1),
    # TCB005 — Growing Joy 0-6M
    ("TCB005", "TCBP00020", 1),
    ("TCB005", "TCBK00002", 1), ("TCB005", "TCBK00003", 1), ("TCB005", "TCBK00004", 1),
    ("TCB005", "TCBK00005", 1), ("TCB005", "TCBK00006", 1),
    # TCB006 — Growing Joy 7-12M
    ("TCB006", "TCBP00021", 1),
    ("TCB006", "TCBK00002", 1), ("TCB006", "TCBK00003", 1), ("TCB006", "TCBK00004", 1),
    ("TCB006", "TCBK00005", 1), ("TCB006", "TCBK00006", 1),
    # TCB008 — Just Arrived Bunny
    ("TCB008", "TCBP00030", 1), ("TCB008", "TCBP00031", 1),
    ("TCB008", "TCBK00002", 1), ("TCB008", "TCBK00003", 1), ("TCB008", "TCBK00004", 1),
    ("TCB008", "TCBK00005", 1), ("TCB008", "TCBK00006", 1),
    # TCB009_1 — Hello Parenthood 2026
    ("TCB009_1", "TCBP00040", 1), ("TCB009_1", "TCBP00041", 1),
    ("TCB009_1", "TCBK00002", 1), ("TCB009_1", "TCBK00003", 1), ("TCB009_1", "TCBK00004", 1),
    ("TCB009_1", "TCBK00005", 1), ("TCB009_1", "TCBK00006", 1),
    # TCB010 — Growing Joy 0-12M
    ("TCB010", "TCBP00060", 1),
    ("TCB010", "TCBK00001", 1), ("TCB010", "TCBK00003", 1), ("TCB010", "TCBK00004", 1),
    ("TCB010", "TCBK00005", 1), ("TCB010", "TCBK00006", 1),
    # TCB011 — Just Arrived Bear
    ("TCB011", "TCBP00030", 1), ("TCB011", "TCBP00032", 1),
    ("TCB011", "TCBK00002", 1), ("TCB011", "TCBK00003", 1), ("TCB011", "TCBK00004", 1),
    ("TCB011", "TCBK00005", 1), ("TCB011", "TCBK00006", 1),
    # TCB012 — Little Looker 4pcs
    ("TCB012", "TCBP00050", 1), ("TCB012", "TCBP00008", 1),
    ("TCB012", "TCBP00012", 1), ("TCB012", "TCBP00013", 1),
    ("TCB012", "TCBK00002", 1), ("TCB012", "TCBK00003", 1), ("TCB012", "TCBK00004", 1),
    ("TCB012", "TCBK00005", 1), ("TCB012", "TCBK00006", 1),
]
bom_rows = [{"sku_id": s, "item_id": item_map[i], "quantity_per_sku": q} for s, i, q in BOM]
upsert("bom", bom_rows, "sku_id,item_id")

# ── 6. ITEM BATCHES + INVENTORY ───────────────────────────────────────────────
print("Seeding item_batches and inventory...")

own_wh_id = db.table("channels").select("channel_id").eq("code", "OWN_WH").single().execute().data["channel_id"]

# (item_code, batch_date, cost_per_unit, qty_received, qty_remaining)
BATCHES = [
    # Textiles
    ("TCBP00001", "2026-03-10",  85.00,  50, 38),
    ("TCBP00002", "2026-03-10",  85.00,  50, 42),
    ("TCBP00003", "2026-03-10",  22.00, 100, 74),
    ("TCBP00004", "2026-02-15",  55.00,  60, 41),
    ("TCBP00005", "2026-03-05",  18.00,  80, 63),
    ("TCBP00006", "2026-02-20",  48.00,  60, 45),
    ("TCBP00007", "2026-03-12",  38.00,  80, 59),
    ("TCBP00008", "2026-03-12",  42.00,  80, 63),
    ("TCBP00009", "2026-03-08",  65.00,  60, 44),
    ("TCBP00010", "2026-03-10", 160.00,  40, 31),
    ("TCBP00011", "2026-03-15",  95.00,  50, 38),
    ("TCBP00012", "2026-03-10",  28.00,  80, 67),
    ("TCBP00013", "2026-03-10",  20.00, 100, 82),
    ("TCBP00014", "2026-03-20", 105.00,  40, 28),
    ("TCBP00015", "2026-03-10", 165.00,  40, 32),
    ("TCBP00020", "2026-03-10", 195.00,  40, 29),
    ("TCBP00021", "2026-03-10", 195.00,  40, 27),
    ("TCBP00030", "2026-03-15",  38.00,  80, 64),
    ("TCBP00031", "2026-03-22", 145.00,  30, 22),
    ("TCBP00032", "2026-03-22", 135.00,  30, 19),
    ("TCBP00040", "2026-03-18", 145.00,  48, 35),
    ("TCBP00041", "2026-03-18", 145.00,  48, 37),
    ("TCBP00050", "2026-03-12",  48.00,  60, 51),
    ("TCBP00060", "2026-03-10", 385.00,  24, 17),
    # Packaging
    ("TCBK00001", "2026-03-01",  55.00, 200, 142),
    ("TCBK00002", "2026-03-01",  42.00, 200, 168),
    ("TCBK00003", "2026-03-01",   4.50, 500, 372),
    ("TCBK00004", "2026-03-01",   8.00, 500, 418),
    ("TCBK00005", "2026-03-01",   6.50, 500, 435),
    ("TCBK00006", "2026-03-01",   3.50, 500, 461),
]

batch_rows = []
inv_rows   = []
for item_code, recv_date_str, cost, qty_recv, qty_rem in BATCHES:
    if item_code not in item_map:
        continue
    item_id    = item_map[item_code]
    batch_code = recv_date_str.replace("-", "")
    batch_rows.append({
        "item_id":       item_id,
        "batch_code":    batch_code,
        "received_date": recv_date_str,
        "cost_per_unit": cost,
        "qty_received":  qty_recv,
        "qty_remaining": qty_rem,
        "is_current":    qty_rem > 0,
    })
    if qty_rem > 0:
        inv_rows.append({
            "item_id":            item_id,
            "batch_code":         batch_code,
            "channel_id":         own_wh_id,
            "quantity_on_hand":   qty_rem,
            "quantity_reserved":  0,
            "quantity_intransit": 0,
        })

for row in batch_rows:
    db.table("item_batches").upsert(row, on_conflict="item_id,batch_code").execute()
print(f"  item_batches: {len(batch_rows)} rows")

batch_id_map = {
    (r["item_id"], r["batch_code"]): r["batch_id"]
    for r in db.table("item_batches").select("batch_id,item_id,batch_code").execute().data
}
for row in inv_rows:
    row["batch_id"] = batch_id_map[(row["item_id"], row["batch_code"])]
    del row["batch_code"]
for row in inv_rows:
    db.table("inventory").upsert(row, on_conflict="item_id,batch_id,channel_id").execute()
print(f"  inventory: {len(inv_rows)} rows")

# ── 7. SKU INVENTORY (packed hampers at OWN_WH) ───────────────────────────────
print("Seeding sku_inventory...")
SKU_STOCK = {
    "TCB001":   8,
    "TCB002":  10,
    "TCB003":   5,
    "TCB004":   6,
    "TCB005":  12,
    "TCB006":   7,
    "TCB008":  15,
    "TCB009_1": 9,
    "TCB010":   3,
    "TCB011":  18,
    "TCB012":  11,
}
for sku_id, qty in SKU_STOCK.items():
    db.table("sku_inventory").upsert(
        {"sku_id": sku_id, "channel_id": own_wh_id, "qty_on_hand": qty, "qty_reserved": 0},
        on_conflict="sku_id,channel_id",
    ).execute()

# Log opening stock transactions (skip if already present)
existing_refs = {
    r["sku_id"]
    for r in db.table("sku_inventory_transactions")
               .select("sku_id")
               .eq("reference", "DEV_OPENING_STOCK")
               .execute().data
}
for sku_id, qty in SKU_STOCK.items():
    if sku_id not in existing_refs and qty > 0:
        db.table("sku_inventory_transactions").insert({
            "type":          "ADJUSTMENT",
            "sku_id":        sku_id,
            "to_channel_id": own_wh_id,
            "quantity":      qty,
            "reference":     "DEV_OPENING_STOCK",
            "notes":         "Dev DB opening stock",
            "created_by":    "dev_seed",
        }).execute()
print(f"  sku_inventory: {len(SKU_STOCK)} SKUs")

# ── 8. BLINKIT LOCATIONS ─────────────────────────────────────────────────────
print("Seeding blinkit_locations...")
blk_ch_id = db.table("channels").select("channel_id").eq("code", "BLK").single().execute().data["channel_id"]

# Warehouses first
WHS = [
    {"name": "Blinkit WH Gurgaon",    "code": "BLK_WH_GGN",  "city": "Gurgaon",    "state": "Haryana",        "location_type": "WH", "stock_sent": True},
    {"name": "Blinkit WH Bengaluru",  "code": "BLK_WH_BLR",  "city": "Bengaluru",  "state": "Karnataka",      "location_type": "WH", "stock_sent": True},
    {"name": "Blinkit WH Hyderabad",  "code": "BLK_WH_HYD",  "city": "Hyderabad",  "state": "Telangana",      "location_type": "WH", "stock_sent": False},
    {"name": "Blinkit WH Mumbai",     "code": "BLK_WH_MUM",  "city": "Mumbai",     "state": "Maharashtra",    "location_type": "WH", "stock_sent": False},
]
for wh in WHS:
    db.table("blinkit_locations").upsert(
        {**wh, "channel_id": blk_ch_id, "is_active": True},
        on_conflict="code",
    ).execute()

# Fetch WH IDs for parent references
wh_id_map = {r["code"]: r["location_id"]
             for r in db.table("blinkit_locations").select("location_id,code").execute().data}

# Darkstores
DARKSTORES = [
    ("BLK_DS_GGN_01", "Blinkit DS Sector 14 Gurgaon",   "Gurgaon",   "Haryana",     "BLK_WH_GGN"),
    ("BLK_DS_GGN_02", "Blinkit DS DLF Phase 2 Gurgaon", "Gurgaon",   "Haryana",     "BLK_WH_GGN"),
    ("BLK_DS_BLR_01", "Blinkit DS Koramangala BLR",      "Bengaluru", "Karnataka",   "BLK_WH_BLR"),
    ("BLK_DS_BLR_02", "Blinkit DS Indiranagar BLR",      "Bengaluru", "Karnataka",   "BLK_WH_BLR"),
    ("BLK_DS_HYD_01", "Blinkit DS Banjara Hills HYD",    "Hyderabad", "Telangana",   "BLK_WH_HYD"),
]
for ds_code, ds_name, city, state, parent_code in DARKSTORES:
    db.table("blinkit_locations").upsert({
        "code":          ds_code,
        "name":          ds_name,
        "city":          city,
        "state":         state,
        "channel_id":    blk_ch_id,
        "location_type": "DARKSTORE",
        "parent_wh_id":  wh_id_map.get(parent_code),
        "stock_sent":    True,
        "is_active":     True,
    }, on_conflict="code").execute()
print(f"  blinkit_locations: {len(WHS)} WHs + {len(DARKSTORES)} darkstores")

print("\n✅ Dev seed complete.")
print("   Items: loosestockseeded at OWN_WH")
print("   SKU stock: 11 active SKUs packed and ready")
print("   Blinkit: 4 WHs, 5 darkstores")
print("\nNext: point your browser to localhost:8501 and test away.")
