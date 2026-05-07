"""
Fix: TCB005 and TCB006 OZI TPs at 2025-10-01 were wrongly inserted as 1200.
Historical value was 1124.2455 (became 1200 effective 2026-05-05).
Deletes the wrong rows and re-inserts at the correct value, then re-patches
any Ozi orders whose transfer_price was set from the wrong entry.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from tcb.db import get_client

CORRECT_TP  = 1124.2455
EFFECTIVE   = '2025-10-01'
OZI_CODE    = 'OZI'
OZI_ID      = 8
SKUS        = ['TCB005', 'TCB006']

db = get_client()

# 1. Delete the wrong entries
for sku_id in SKUS:
    db.table('sku_channel_tp') \
      .delete() \
      .eq('sku_id', sku_id) \
      .eq('channel_code', OZI_CODE) \
      .eq('effective_date', EFFECTIVE) \
      .execute()
    print(f'Deleted wrong entry: {sku_id} OZI {EFFECTIVE} tp=1200')

# 2. Re-insert with correct historical TP
for sku_id in SKUS:
    db.table('sku_channel_tp').insert({
        'sku_id':         sku_id,
        'channel_code':   OZI_CODE,
        'effective_date': EFFECTIVE,
        'transfer_price': CORRECT_TP,
    }).execute()
    print(f'Inserted correct: {sku_id} OZI {EFFECTIVE} tp={CORRECT_TP}')

# 3. Re-patch Ozi orders where tp may have been set from the wrong entry
#    (anything with tp=1200 that should be 1124.2455 based on order_date)
affected = (db.table('orders')
              .select('order_id, sku_id, order_date, transfer_price')
              .eq('channel_id', OZI_ID)
              .in_('sku_id', SKUS)
              .execute().data)

for row in affected:
    tp_row = (db.table('sku_channel_tp').select('transfer_price')
                .eq('sku_id', row['sku_id'])
                .eq('channel_code', OZI_CODE)
                .lte('effective_date', row['order_date'])
                .order('effective_date', desc=True)
                .limit(1).execute().data)
    correct_tp = float(tp_row[0]['transfer_price']) if tp_row else None
    if correct_tp != row['transfer_price']:
        db.table('orders').update({'transfer_price': correct_tp}) \
          .eq('order_id', row['order_id']).execute()
        print(f"  Re-patched {row['sku_id']} {row['order_date']}  "
              f"{row['transfer_price']} -> {correct_tp}")

print('\nDone.')
