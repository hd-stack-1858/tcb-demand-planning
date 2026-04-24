"""
Seed script: loads current packed SKU inventory at OWN_WH from the SKU tab
of Batch wise-cost-inventory.xlsx. Logs an OPENING_STOCK adjustment transaction
for each SKU with qty > 0.
Run after 04_seed_batches.py.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8')
from tcb.db import get_client
import openpyxl
from datetime import datetime, timezone

EXCEL = os.path.join(os.path.dirname(__file__), '..', 'master files', 'Batch wise-cost-inventory.xlsx')
db = get_client()

# ── Lookups ───────────────────────────────────────────────────
own_wh_id = db.table("channels").select("channel_id").eq("code", "OWN_WH").single().execute().data["channel_id"]

# ── Load SKU tab ──────────────────────────────────────────────
wb = openpyxl.load_workbook(EXCEL, data_only=True)
ws = wb["SKU"]
rows = list(ws.iter_rows(values_only=True))[1:]  # skip header

print("Seeding sku_inventory (OWN_WH)...")

inv_rows = []
txn_rows = []

for r in rows:
    if not r[0]:
        continue
    sku_id = str(r[0]).strip()
    qty    = int(r[2]) if r[2] else 0

    inv_rows.append({
        "sku_id":       sku_id,
        "channel_id":   own_wh_id,
        "qty_on_hand":  qty,
        "qty_reserved": 0,
    })

    if qty > 0:
        txn_rows.append({
            "type":         "ADJUSTMENT",
            "sku_id":       sku_id,
            "to_channel_id": own_wh_id,
            "quantity":     qty,
            "reference":    "OPENING_STOCK",
            "notes":        "Opening stock load — approximate, to be confirmed Sat",
            "created_by":   "seed",
        })

# Upsert sku_inventory
for row in inv_rows:
    db.table("sku_inventory").upsert(row, on_conflict="sku_id,channel_id").execute()
print(f"  sku_inventory: {len(inv_rows)} rows upserted")

# Insert transactions (only for non-zero qty; skip if opening stock already loaded)
existing_refs = {r["sku_id"] for r in
    db.table("sku_inventory_transactions")
      .select("sku_id")
      .eq("reference", "OPENING_STOCK")
      .eq("to_channel_id", own_wh_id)
      .execute().data}

new_txns = [t for t in txn_rows if t["sku_id"] not in existing_refs]
if new_txns:
    db.table("sku_inventory_transactions").insert(new_txns).execute()
    print(f"  sku_inventory_transactions: {len(new_txns)} opening-stock rows inserted")
else:
    print("  sku_inventory_transactions: already seeded, skipped")

print(f"\nSKU inventory seed complete.")
non_zero = sum(1 for r in inv_rows if r["qty_on_hand"] > 0)
print(f"  {non_zero}/{len(inv_rows)} SKUs have stock > 0 at OWN_WH")
