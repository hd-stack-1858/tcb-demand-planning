"""
One-time dev setup: seed ASSEMBLY transactions for SKUs that have no history.

Dev item_batches are empty (stock was seeded as baseline, not via Assemble tab).
Without ASSEMBLY history, record_dropship_sale / record_outright_transfer will
hit the BOM fallback, find no item_batches costs, and block the shipment.

Run once after initial dev setup:
    TCB_ENV=dev python setup/07_seed_dev_assembly_cogs.py

Safe to re-run — skips SKUs that already have ASSEMBLY history.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("TCB_ENV", "dev")

from tcb.db import get_client
from tcb.catalog import CATALOG_COGS

OWN_WH_ID = 1


def main():
    db = get_client()

    existing = {
        r["sku_id"]
        for r in db.table("sku_inventory_transactions")
                   .select("sku_id")
                   .eq("type", "ASSEMBLY")
                   .execute().data
    }

    rows = [
        {"type": "ASSEMBLY", "sku_id": sku_id, "to_channel_id": OWN_WH_ID,
         "quantity": 1, "unit_cogs": unit_cogs,
         "reference": "SEED_DEV_COGS", "created_by": "setup_script"}
        for sku_id, unit_cogs in CATALOG_COGS.items()
        if sku_id not in existing
    ]

    if rows:
        db.table("sku_inventory_transactions").insert(rows).execute()

    seeded  = [r["sku_id"] for r in rows]
    skipped = [s for s in CATALOG_COGS if s not in {r["sku_id"] for r in rows}]
    print(f"Seeded : {seeded or 'none'}")
    print(f"Skipped (already had ASSEMBLY): {skipped or 'none'}")


if __name__ == "__main__":
    main()
