import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
db = get_client()

# Peeko=7, Kiddo=9
OUTRIGHT_CHANNELS = [7, 9]

txns = (db.table('sku_inventory_transactions')
          .select('txn_id, sku_id, quantity, unit_cogs, reference, created_at, to_channel_id')
          .eq('type', 'TRANSFER_OUT')
          .in_('to_channel_id', OUTRIGHT_CHANNELS)
          .order('created_at')
          .execute().data)

ch_names = {7: 'Peeko', 9: 'Kiddo'}

print(f"OUTRIGHT TRANSFER_OUT transactions: {len(txns)}")
for t in txns:
    ch = ch_names[t['to_channel_id']]
    date = t['created_at'][:10]

    # Look up TP at dispatch date
    tp_row = (db.table('sku_channel_tp')
                .select('transfer_price')
                .eq('sku_id', t['sku_id'])
                .eq('channel_code', 'PEEKO' if t['to_channel_id'] == 7 else 'KIDDO')
                .lte('effective_date', date)
                .order('effective_date', desc=True)
                .limit(1).execute().data)
    tp = tp_row[0]['transfer_price'] if tp_row else None

    # Look up MRP at dispatch date
    mrp_row = (db.table('sku_pricing')
                 .select('mrp')
                 .eq('sku_id', t['sku_id'])
                 .lte('effective_date', date)
                 .order('effective_date', desc=True)
                 .limit(1).execute().data)
    mrp = mrp_row[0]['mrp'] if mrp_row else None

    # Check if orders row already exists
    existing = (db.table('orders')
                  .select('order_id')
                  .eq('platform_order_id', t['reference'])
                  .eq('channel_id', t['to_channel_id'])
                  .eq('sku_id', t['sku_id'])
                  .execute().data)

    status = 'ALREADY IN ORDERS' if existing else 'MISSING'
    print(f"  {status}  txn={t['txn_id']}  {ch}  {t['sku_id']}  qty={t['quantity']}  ref={t['reference']}  date={date}  tp={tp}  mrp={mrp}  unit_cogs={t['unit_cogs']}")
