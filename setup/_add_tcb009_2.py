"""
Add TCB009_2 — Hello Parenthood Hamper — Mommy Mug (Amazon-only, single mug variant).
Adds to: skus, bom (Mommy mug + Shrink Wrap), sku_pricing.
Run against dev first, then prod.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from tcb.db import get_client

SKU_ID   = 'TCB009_2'
SKU_NAME = 'Hello Parenthood Hamper — Mommy Mug'
TODAY    = '2026-05-07'

db = get_client()

# 1. skus
existing = db.table('skus').select('sku_id').eq('sku_id', SKU_ID).execute().data
if existing:
    print(f'skus: {SKU_ID} already exists — skipping')
else:
    db.table('skus').insert({
        'sku_id':         SKU_ID,
        'name':           SKU_NAME,
        'hsn_code':       '69120010',   # same as TCB009_1 (ceramic mugs)
        'gst_pct':        5.0,
        'is_discontinued': False,
    }).execute()
    print(f'skus: inserted {SKU_ID}')

# 2. bom — Mommy mug (item 22) + Shrink Wrap Mugs 2026 (item 31)
BOM_LINES = [
    {'item_id': 22, 'quantity_per_sku': 1},   # Ceramic Mug Mommy 2026
    {'item_id': 31, 'quantity_per_sku': 1},   # Shrink Wrap Mugs 2026
]
for line in BOM_LINES:
    exists = (db.table('bom').select('bom_id')
                .eq('sku_id', SKU_ID)
                .eq('item_id', line['item_id'])
                .execute().data)
    if exists:
        print(f"bom: item_id={line['item_id']} already exists — skipping")
    else:
        db.table('bom').insert({'sku_id': SKU_ID, **line}).execute()
        print(f"bom: inserted sku_id={SKU_ID} item_id={line['item_id']} qty={line['quantity_per_sku']}")

# 3. sku_pricing
exists = (db.table('sku_pricing').select('pricing_id')
            .eq('sku_id', SKU_ID)
            .eq('effective_date', TODAY)
            .execute().data)
if exists:
    print(f'sku_pricing: entry for {TODAY} already exists — skipping')
else:
    db.table('sku_pricing').insert({
        'sku_id':         SKU_ID,
        'effective_date': TODAY,
        'mrp':            599,
        'sp':             495,
        'notes':          'Launch pricing May 2026 — Amazon only',
    }).execute()
    print(f'sku_pricing: inserted MRP=599 SP=495 effective {TODAY}')

print('\nDone.')
