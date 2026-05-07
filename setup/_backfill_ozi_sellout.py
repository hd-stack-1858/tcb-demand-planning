"""
Backfill Ozi sell-out orders Nov-25 to Apr-26.
Ozi is SOR (channel_id=8). Stock was sent Oct-25 (pre-system, already in opening balance).
Only orders rows needed — no stock/lot adjustments.
City = Gurugram (state = Haryana) for all Ozi orders.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
from tcb.geo import city_to_state
db = get_client()

OZI      = 8
CITY     = 'Gurgaon'   # city_to_state maps 'Gurgaon' -> Haryana
STATE    = city_to_state(CITY)   # 'Haryana'

# Sell-out data: (sku_id, order_date, qty)
# Dates = last day of the sell-out month
SELLOUTS = [
    ('TCB008',   '2025-11-30', 1),
    ('TCB001',   '2025-12-31', 1),
    ('TCB002',   '2025-12-31', 1),
    ('TCB005',   '2026-01-31', 1),
    ('TCB008',   '2026-01-31', 1),
    ('TCB005',   '2026-02-28', 1),
    ('TCB006',   '2026-02-28', 2),
    ('TCB002',   '2026-03-31', 1),
    ('TCB003',   '2026-04-30', 2),
    ('TCB004',   '2026-04-30', 1),
]

inserted = skipped = warned = 0

for sku_id, date_str, qty in SELLOUTS:
    # Idempotency: (channel, sku, date, fulfillment_type)
    existing = (db.table('orders')
                  .select('order_id')
                  .eq('channel_id', OZI)
                  .eq('sku_id', sku_id)
                  .eq('order_date', date_str)
                  .eq('fulfillment_type', 'SOR')
                  .execute().data)
    if existing:
        print(f'  SKIP   {sku_id}  {date_str}')
        skipped += 1
        continue

    # SP + MRP at sell-out date
    pricing = (db.table('sku_pricing')
                 .select('sp, mrp')
                 .eq('sku_id', sku_id)
                 .lte('effective_date', date_str)
                 .order('effective_date', desc=True)
                 .limit(1).execute().data)
    if not pricing or not pricing[0].get('sp'):
        print(f'  WARN   {sku_id}  {date_str}  no SP in sku_pricing — skipping')
        warned += 1
        continue
    sp  = float(pricing[0]['sp'])
    mrp = float(pricing[0]['mrp']) if pricing[0].get('mrp') else None
    disc = round((mrp - sp) / mrp * 100, 2) if mrp and mrp > 0 else None

    # TP at sell-out date
    tp_row = (db.table('sku_channel_tp')
                .select('transfer_price')
                .eq('sku_id', sku_id)
                .eq('channel_code', 'OZI')
                .lte('effective_date', date_str)
                .order('effective_date', desc=True)
                .limit(1).execute().data)
    tp = float(tp_row[0]['transfer_price']) if tp_row else None

    db.table('orders').insert({
        'channel_id':         OZI,
        'order_date':         date_str,
        'sku_id':             sku_id,
        'quantity':           qty,
        'mrp':                mrp,
        'selling_price':      sp,
        'gross_value':        round(qty * sp, 2),
        'discount_pct':       disc,
        'cogs':               0.0,
        'transfer_price':     tp,
        'fulfillment_type':   'SOR',
        'platform_order_id':  None,
        'status':             'FULFILLED',
        'source_file':        'backfill',
        'city':               CITY,
        'state':              STATE,
        'lot_cogs_finalized': True,
    }).execute()
    print(f'  INSERT {sku_id:10s}  {date_str}  qty={qty}  sp={sp}  tp={tp}')
    inserted += 1

print(f'\nDone: {inserted} inserted, {skipped} skipped, {warned} warned')
