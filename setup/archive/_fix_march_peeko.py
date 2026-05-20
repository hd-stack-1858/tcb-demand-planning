import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
from tcb.geo import city_to_state
db = get_client()

REF  = 'GT/25-26/025'
CH   = 7   # Peeko
DATE = '2026-03-12'

# Fix TCB009_1: qty 1 -> 2
sp_009 = float(db.table('sku_pricing').select('sp').eq('sku_id', 'TCB009_1')
               .lte('effective_date', DATE).order('effective_date', desc=True)
               .limit(1).execute().data[0]['sp'])
db.table('orders').update({'quantity': 2, 'gross_value': round(2 * sp_009, 2)}) \
  .eq('platform_order_id', REF).eq('channel_id', CH).eq('sku_id', 'TCB009_1').execute()
print(f'TCB009_1 updated  qty=2  sp={sp_009}  gross_value={round(2*sp_009,2)}')

# Fix TCB010: qty 2 -> 1
sp_010 = float(db.table('sku_pricing').select('sp').eq('sku_id', 'TCB010')
               .lte('effective_date', DATE).order('effective_date', desc=True)
               .limit(1).execute().data[0]['sp'])
db.table('orders').update({'quantity': 1, 'gross_value': round(1 * sp_010, 2)}) \
  .eq('platform_order_id', REF).eq('channel_id', CH).eq('sku_id', 'TCB010').execute()
print(f'TCB010  updated  qty=1  sp={sp_010}  gross_value={round(1*sp_010,2)}')

# Insert missing TCB004 qty=2
p = db.table('sku_pricing').select('sp, mrp').eq('sku_id', 'TCB004') \
      .lte('effective_date', DATE).order('effective_date', desc=True) \
      .limit(1).execute().data[0]
sp = float(p['sp']); mrp = float(p['mrp'])
disc = round((mrp - sp) / mrp * 100, 2) if mrp else None
tp_row = db.table('sku_channel_tp').select('transfer_price').eq('sku_id', 'TCB004') \
           .eq('channel_code', 'PEEKO').lte('effective_date', DATE) \
           .order('effective_date', desc=True).limit(1).execute().data
tp = float(tp_row[0]['transfer_price']) if tp_row else None
db.table('orders').insert({
    'channel_id': CH, 'order_date': DATE, 'sku_id': 'TCB004', 'quantity': 2,
    'mrp': mrp, 'selling_price': sp, 'gross_value': round(2 * sp, 2),
    'discount_pct': disc, 'cogs': 0.0, 'transfer_price': tp,
    'fulfillment_type': 'OUTRIGHT', 'platform_order_id': REF,
    'status': 'FULFILLED', 'source_file': 'backfill',
    'city': 'Bengaluru', 'state': city_to_state('Bengaluru'),
    'lot_cogs_finalized': True,
}).execute()
print(f'TCB004  inserted  qty=2  sp={sp}  tp={tp}  gross_value={round(2*sp,2)}')
