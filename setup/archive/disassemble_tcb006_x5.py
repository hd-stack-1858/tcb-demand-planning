"""
One-off: disassemble 5 units of TCB006 (Growing Joy 7–12 Months) at OWN_WH.

Shrink Wrap Big (item_id=28) is destroyed during disassembly — written off.
All other 6 BOM items are returned to their latest inventory batch.

DB writes:
  inventory                  — +5 on latest batch for each of the 6 returned items
  inventory_transactions     — RECEIPT txn per returned item, DAMAGE_WRITE_OFF for shrink wrap
  sku_inventory              — qty_on_hand: 18 → 13
  sku_inventory_transactions — ADJUSTMENT row with note
  sku_cogs_lots              — lot_id=9 qty_remaining: 18 → 13

Run with --dry-run first to verify before committing.
Usage:
    python setup/archive/disassemble_tcb006_x5.py --dry-run
    python setup/archive/disassemble_tcb006_x5.py
"""

import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tcb.db import get_client

SKU_ID      = "TCB006"
QTY         = 5
SHRINK_WRAP = 28          # item_id of Shrink Wrap Big — destroyed, not returned
NOTES       = f"DISASSEMBLY_{SKU_ID}_x{QTY}"
CREATED_BY  = "himanshu"


def run(dry_run: bool):
    db       = get_client()
    own_wh   = (db.table("channels").select("channel_id")
                  .eq("code", "OWN_WH").single().execute().data["channel_id"])

    # ── Fetch BOM ─────────────────────────────────────────────────────────────
    bom = (db.table("bom")
             .select("item_id, quantity_per_sku, items(name)")
             .eq("sku_id", SKU_ID).execute().data)

    print(f"\n{'DRY RUN — ' if dry_run else ''}Disassemble {QTY} × {SKU_ID} at OWN_WH (channel_id={own_wh})")
    print("=" * 65)

    # ── Plan: find latest inv row per item ────────────────────────────────────
    plan = []
    for b in bom:
        item_id = b["item_id"]
        qty_back = int(b["quantity_per_sku"]) * QTY
        name     = (b.get("items") or {}).get("name", f"item_{item_id}")
        destroyed = (item_id == SHRINK_WRAP)

        rows = (db.table("inventory")
                  .select("inv_id, batch_id, quantity_on_hand")
                  .eq("item_id", item_id)
                  .eq("channel_id", own_wh)
                  .order("inv_id", desc=True)     # latest batch first
                  .limit(1).execute().data)

        if not rows:
            print(f"  ERROR: no inventory row found for item_id={item_id} ({name}) — aborting.")
            sys.exit(1)

        row = rows[0]
        action = "WRITE OFF (destroyed)" if destroyed else f"RETURN  -> inv_id={row['inv_id']} (qty {row['quantity_on_hand']} + {qty_back})"
        print(f"  item_id={item_id:3d}  qty={qty_back}  {name[:35]:<35}  {action}")
        plan.append({
            "item_id":   item_id,
            "name":      name,
            "qty_back":  qty_back,
            "destroyed": destroyed,
            "inv_id":    row["inv_id"],
            "batch_id":  row["batch_id"],
            "qty_cur":   row["quantity_on_hand"],
        })

    # ── sku_inventory check ───────────────────────────────────────────────────
    sku_inv = (db.table("sku_inventory").select("sku_inv_id, qty_on_hand")
                 .eq("sku_id", SKU_ID).eq("channel_id", own_wh).single().execute().data)
    print(f"\n  sku_inventory: qty_on_hand {sku_inv['qty_on_hand']} -> {sku_inv['qty_on_hand'] - QTY}")

    lot = (db.table("sku_cogs_lots").select("lot_id, qty_remaining")
             .eq("sku_id", SKU_ID).eq("channel_id", own_wh)
             .is_("partner_location_id", "null")
             .gt("qty_remaining", 0)
             .order("assembled_at").limit(1).execute().data)
    if lot:
        print(f"  sku_cogs_lots: lot_id={lot[0]['lot_id']} qty_remaining {lot[0]['qty_remaining']} -> {lot[0]['qty_remaining'] - QTY}")

    if dry_run:
        print("\nDry run complete — no changes written.")
        return

    print("\nWriting to DB...")

    # ── 1. Update inventory + log inventory_transactions ──────────────────────
    for p in plan:
        if p["destroyed"]:
            # Shrink wrap: deduct 5 from item inventory (it was consumed in assembly,
            # now we confirm it's gone — quantity_on_hand is already 0 from assembly,
            # so we just log the write-off for audit trail without touching qty)
            db.table("inventory_transactions").insert({
                "type":          "DISASSEMBLY",
                "item_id":       p["item_id"],
                "sku_id":        SKU_ID,
                "batch_id":      p["batch_id"],
                "from_channel_id": own_wh,
                "quantity":      p["qty_back"],
                "reference":     NOTES,
                "notes":         "destroyed during disassembly — not recoverable",
                "created_by":    CREATED_BY,
            }).execute()
            print(f"  item_id={p['item_id']} ({p['name']}) — DAMAGE_WRITE_OFF txn logged")
        else:
            # Return item to inventory
            new_qty = p["qty_cur"] + p["qty_back"]
            db.table("inventory").update({"quantity_on_hand": new_qty})\
              .eq("inv_id", p["inv_id"]).execute()
            db.table("inventory_transactions").insert({
                "type":        "DISASSEMBLY",
                "item_id":     p["item_id"],
                "sku_id":      SKU_ID,
                "batch_id":    p["batch_id"],
                "to_channel_id": own_wh,
                "quantity":    p["qty_back"],
                "reference":   NOTES,
                "notes":       "returned to stock from disassembly",
                "created_by":  CREATED_BY,
            }).execute()
            print(f"  item_id={p['item_id']} ({p['name']}) — inventory {p['qty_cur']} → {new_qty}")

    # ── 2. Decrement sku_inventory ────────────────────────────────────────────
    new_sku_qty = sku_inv["qty_on_hand"] - QTY
    db.table("sku_inventory").update({
        "qty_on_hand":  new_sku_qty,
        "last_updated": date.today().isoformat(),
    }).eq("sku_inv_id", sku_inv["sku_inv_id"]).execute()
    print(f"  sku_inventory updated: qty_on_hand → {new_sku_qty}")

    # ── 3. Log sku_inventory_transactions ─────────────────────────────────────
    db.table("sku_inventory_transactions").insert({
        "type":            "DISASSEMBLY",
        "sku_id":          SKU_ID,
        "from_channel_id": own_wh,
        "quantity":        QTY,
        "notes":           NOTES + " — shrink wrap destroyed, all other items returned",
        "created_by":      CREATED_BY,
    }).execute()
    print(f"  sku_inventory_transactions — ADJUSTMENT logged")

    # ── 4. Reduce sku_cogs_lots ───────────────────────────────────────────────
    if lot:
        new_lot_qty = lot[0]["qty_remaining"] - QTY
        db.table("sku_cogs_lots").update({"qty_remaining": new_lot_qty})\
          .eq("lot_id", lot[0]["lot_id"]).execute()
        print(f"  sku_cogs_lots lot_id={lot[0]['lot_id']} qty_remaining → {new_lot_qty}")

    # ── 5. Verify ─────────────────────────────────────────────────────────────
    final = (db.table("sku_inventory").select("qty_on_hand")
               .eq("sku_id", SKU_ID).eq("channel_id", own_wh).single().execute().data)
    print(f"\nVerified: TCB006 sku_inventory.qty_on_hand = {final['qty_on_hand']}  (expected {new_sku_qty})")
    assert final["qty_on_hand"] == new_sku_qty, "Verification failed — check DB!"
    print("Done.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run(dry_run=dry_run)
