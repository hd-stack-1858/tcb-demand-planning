import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
from tcb.geo import city_to_state
db = get_client()

SKU    = 'TCB009_1'
CH     = 7        # Peeko
DATE   = '2025-12-15'
SP     = 899.0    # confirmed by Himanshu for Dec 2025
QTY    = 1

# MRP: use earliest entry in sku_pricing (no entry at this date, take oldest available)
mrp_row = (db.table('sku_pricing').select('mrp')
             .eq('sku_id', SKU)
             .order('effective_date')
             .limit(1).execute().data)
mrp = float(mrp_row[0]['mrp']) if mrp_row else None
disc = round((mrp - SP) / mrp * 100, 2) if mrp and mrp > 0 else None

# TP: earliest available entry for PEEKO
tp_row = (db.table('sku_channel_tp').select('transfer_price')
            .eq('sku_id', SKU).eq('channel_code', 'PEEKO')
            .order('effective_date')
            .limit(1).execute().data)
tp = float(tp_row[0]['transfer_price']) if tp_row else None

db.table('orders').insert({
    'channel_id':         CH,
    'order_date':         DATE,
    'sku_id':             SKU,
    'quantity':           QTY,
    'mrp':                mrp,
    'selling_price':      SP,
    'gross_value':        round(QTY * SP, 2),
    'discount_pct':       disc,
    'cogs':               0.0,
    'transfer_price':     tp,
    'fulfillment_type':   'OUTRIGHT',
    'platform_order_id':  None,
    'status':             'FULFILLED',
    'source_file':        'backfill',
    'city':               'Bengaluru',
    'state':              city_to_state('Bengaluru'),
    'lot_cogs_finalized': True,
}).execute()
print(f'Inserted {SKU}  qty={QTY}  sp={SP}  mrp={mrp}  tp={tp}  disc={disc}%')
