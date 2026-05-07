"""
Backfill orders rows for historical OUTRIGHT TRANSFER_OUTs (Peeko=7, Kiddo=9)
that predate the record_outright_transfer implementation.

Safe to re-run: skips any txn that already has a matching orders row.
Run ONLY after migration 012 (transfer_price column) is applied to prod.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
from tcb.geo import city_to_state
db = get_client()

OUTRIGHT_CHANNELS = [7, 9]  # Peeko=7, Kiddo=9
CH_CODES  = {7: 'PEEKO', 9: 'KIDDO'}
CH_CITIES = {7: 'Bengaluru', 9: 'Noida'}

txns = (db.table('sku_inventory_transactions')
          .select('txn_id, sku_id, quantity, unit_cogs, reference, created_at, to_channel_id')
          .eq('type', 'TRANSFER_OUT')
          .in_('to_channel_id', OUTRIGHT_CHANNELS)
          .order('created_at')
          .execute().data)

print(f"Found {len(txns)} OUTRIGHT TRANSFER_OUT transactions")
inserted = skipped = 0

for t in txns:
    channel_id   = t['to_channel_id']
    channel_code = CH_CODES[channel_id]
    city         = CH_CITIES[channel_id]
    date_str     = t['created_at'][:10]
    sku_id       = t['sku_id']
    qty          = int(t['quantity'])
    unit_cogs    = float(t['unit_cogs']) if t['unit_cogs'] else 0.0
    reference    = t['reference'] or None

    # Skip if orders row already exists (idempotent)
    if reference:
        existing = (db.table('orders')
                      .select('order_id')
                      .eq('platform_order_id', reference)
                      .eq('channel_id', channel_id)
                      .eq('sku_id', sku_id)
                      .execute().data)
    else:
        existing = (db.table('orders')
                      .select('order_id')
                      .eq('channel_id', channel_id)
                      .eq('sku_id', sku_id)
                      .eq('order_date', date_str)
                      .eq('fulfillment_type', 'OUTRIGHT')
                      .execute().data)
    if existing:
        print(f"  SKIP   txn={t['txn_id']:3d}  {sku_id:10s}  (orders row exists)")
        skipped += 1
        continue

    # SP + MRP at dispatch date
    pricing = (db.table('sku_pricing')
                 .select('sp, mrp')
                 .eq('sku_id', sku_id)
                 .lte('effective_date', date_str)
                 .order('effective_date', desc=True)
                 .limit(1).execute().data)
    if not pricing or not pricing[0].get('sp'):
        print(f"  WARN   txn={t['txn_id']:3d}  {sku_id:10s}  no SP in sku_pricing — skipping")
        skipped += 1
        continue
    selling_price = float(pricing[0]['sp'])
    mrp           = float(pricing[0]['mrp']) if pricing[0].get('mrp') else None
    discount_pct  = round((mrp - selling_price) / mrp * 100, 2) if mrp and mrp > 0 else None

    # TP at dispatch date
    tp_row = (db.table('sku_channel_tp')
                .select('transfer_price')
                .eq('sku_id', sku_id)
                .eq('channel_code', channel_code)
                .lte('effective_date', date_str)
                .order('effective_date', desc=True)
                .limit(1).execute().data)
    transfer_price = float(tp_row[0]['transfer_price']) if tp_row else None

    db.table('orders').insert({
        'channel_id':         channel_id,
        'order_date':         date_str,
        'sku_id':             sku_id,
        'quantity':           qty,
        'mrp':                mrp,
        'selling_price':      selling_price,
        'gross_value':        round(qty * selling_price, 2),
        'discount_pct':       discount_pct,
        'cogs':               round(qty * unit_cogs, 2),
        'transfer_price':     transfer_price,
        'fulfillment_type':   'OUTRIGHT',
        'platform_order_id':  reference,
        'status':             'FULFILLED',
        'source_file':        'warehouse_app',
        'city':               city,
        'state':              city_to_state(city),
        'lot_cogs_finalized': True,
    }).execute()
    print(f"  INSERT txn={t['txn_id']:3d}  {sku_id:10s}  qty={qty}  "
          f"sp={selling_price}  tp={transfer_price}  cogs={round(qty * unit_cogs, 2)}")
    inserted += 1

print(f"\nDone: {inserted} inserted, {skipped} skipped")
