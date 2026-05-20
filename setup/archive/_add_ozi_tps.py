"""
Seed OZI transfer prices in sku_channel_tp, effective 2025-10-01 (first Ozi stock sent).
Also patches any existing Ozi orders where transfer_price is NULL.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from tcb.db import get_client

OZI_TPS = [
    ('TCB001',   974.253),
    ('TCB002',   974.253),
    ('TCB003',  1349.25),
    ('TCB004',  1349.25),
    ('TCB005',  1200.0),
    ('TCB006',  1200.0),
    ('TCB007',  1349.25),
    ('TCB008',   636.7515),
    ('TCB009_1', 636.7515),   # TCB009 in invoices = TCB009_1 in DB
]
EFFECTIVE = '2025-10-01'
OZI_CODE  = 'OZI'
OZI_ID    = 8

db = get_client()

print('--- sku_channel_tp ---')
for sku_id, tp in OZI_TPS:
    existing = (db.table('sku_channel_tp').select('tp_id')
                  .eq('sku_id', sku_id)
                  .eq('channel_code', OZI_CODE)
                  .eq('effective_date', EFFECTIVE)
                  .execute().data)
    if existing:
        print(f'  SKIP   {sku_id}  (already exists)')
    else:
        db.table('sku_channel_tp').insert({
            'sku_id':         sku_id,
            'channel_code':   OZI_CODE,
            'effective_date': EFFECTIVE,
            'transfer_price': tp,
        }).execute()
        print(f'  INSERT {sku_id:10s}  tp={tp}')

# Patch Ozi orders where transfer_price is NULL
print('\n--- patching NULL transfer_price on existing Ozi orders ---')
null_orders = (db.table('orders')
                 .select('order_id, sku_id, order_date')
                 .eq('channel_id', OZI_ID)
                 .is_('transfer_price', 'null')
                 .execute().data)
print(f'Found {len(null_orders)} orders with NULL transfer_price')

for row in null_orders:
    tp_row = (db.table('sku_channel_tp').select('transfer_price')
                .eq('sku_id', row['sku_id'])
                .eq('channel_code', OZI_CODE)
                .lte('effective_date', row['order_date'])
                .order('effective_date', desc=True)
                .limit(1).execute().data)
    if not tp_row:
        print(f"  WARN  {row['sku_id']}  {row['order_date']}  still no TP found")
        continue
    tp = float(tp_row[0]['transfer_price'])
    db.table('orders').update({'transfer_price': tp}) \
      .eq('order_id', row['order_id']).execute()
    print(f"  PATCH {row['sku_id']:10s}  {row['order_date']}  tp={tp}")

print('\nDone.')
