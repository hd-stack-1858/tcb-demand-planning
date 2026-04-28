"""
One-time cleanup: reverse TCB005 ASSEMBLY transactions from the last N hours.

What it does:
  1. Finds all item-level ASSEMBLY rows in inventory_transactions for TCB005
  2. Adds quantities back to item inventory batches (LIFO — newest batch first)
  3. Resets sku_inventory packed count for TCB005
  4. Deletes all those transaction rows to leave a clean slate

After running: assemble 26 units of TCB005 from the app in one clean entry.

Usage (run from DemandPlanning directory):
  python setup/reverse_assembly.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timezone, timedelta
from collections import defaultdict
from tcb.db import get_client

# ── Config ────────────────────────────────────────────────────────────────────
SKU_ID       = 'TCB005'
LOOKBACK_HRS = 4          # catches everything from today's session

db       = get_client()
cutoff   = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HRS)).isoformat()
own_wh   = (db.table("channels").select("channel_id")
              .eq("code", "OWN_WH").single().execute().data["channel_id"])

print(f"=== Reversing {SKU_ID} ASSEMBLY transactions (last {LOOKBACK_HRS}h) ===")
print(f"    cutoff: {cutoff}\n")

# ── Step 1: find item-level transactions ──────────────────────────────────────
item_txns = (db.table("inventory_transactions")
               .select("txn_id, item_id, quantity")
               .eq("type", "ASSEMBLY")
               .eq("sku_id", SKU_ID)
               .gte("created_at", cutoff)
               .execute().data)

print(f"Item-level rows found: {len(item_txns)}")
if not item_txns:
    print("  Nothing to reverse.")
else:
    # Aggregate total to restore per item
    restore = defaultdict(int)
    for t in item_txns:
        restore[t["item_id"]] += t["quantity"]

    # ── Step 2: restore loose inventory ──────────────────────────────────────
    print("\nRestoring loose stock:")
    for item_id, total in restore.items():
        item_name = (db.table("items").select("name").eq("item_id", item_id)
                       .single().execute().data["name"])

        # All batches for this item at OWN_WH, newest first (LIFO restore)
        inv_rows = (db.table("inventory")
                      .select("inv_id, batch_id, quantity_on_hand, "
                              "item_batches(received_date, qty_received)")
                      .eq("item_id", item_id)
                      .eq("channel_id", own_wh)
                      .execute().data)
        inv_rows.sort(key=lambda r: r["item_batches"]["received_date"], reverse=True)

        remaining = total
        for row in inv_rows:
            if remaining <= 0:
                break
            capacity = row["item_batches"]["qty_received"] - row["quantity_on_hand"]
            add_back = min(capacity, remaining)
            new_qty  = row["quantity_on_hand"] + add_back
            db.table("inventory").update({"quantity_on_hand": new_qty})\
              .eq("inv_id", row["inv_id"]).execute()
            db.table("item_batches").update({"is_current": True})\
              .eq("batch_id", row["batch_id"]).execute()
            remaining -= add_back

        print(f"  ✓ {item_name}: +{total}")

    # ── Step 3: delete item-level transaction rows ────────────────────────────
    for t in item_txns:
        db.table("inventory_transactions").delete().eq("txn_id", t["txn_id"]).execute()
    print(f"\nDeleted {len(item_txns)} inventory_transactions rows")

# ── Step 4: find SKU-level transactions ──────────────────────────────────────
sku_txns = (db.table("sku_inventory_transactions")
              .select("txn_id, quantity")
              .eq("type", "ASSEMBLY")
              .eq("sku_id", SKU_ID)
              .gte("created_at", cutoff)
              .execute().data)

total_packed = sum(t["quantity"] for t in sku_txns)
print(f"\nSKU-level rows found: {len(sku_txns)} (total packed qty: {total_packed})")

# ── Step 5: reset packed SKU count ───────────────────────────────────────────
sku_inv = (db.table("sku_inventory").select("sku_inv_id, qty_on_hand")
             .eq("sku_id", SKU_ID).eq("channel_id", own_wh).execute().data)

if sku_inv and total_packed > 0:
    old = sku_inv[0]["qty_on_hand"]
    new = max(0, old - total_packed)
    db.table("sku_inventory").update({"qty_on_hand": new})\
      .eq("sku_inv_id", sku_inv[0]["sku_inv_id"]).execute()
    print(f"  ✓ SKU inventory: {old} → {new}")

# ── Step 6: delete SKU-level transaction rows ─────────────────────────────────
for t in sku_txns:
    db.table("sku_inventory_transactions").delete().eq("txn_id", t["txn_id"]).execute()
print(f"  ✓ Deleted {len(sku_txns)} sku_inventory_transactions rows")

print(f"\n✅ Done. Loose stock is restored to pre-assembly state.")
print(f"   Now assemble 26 units of {SKU_ID} from the app.\n")
