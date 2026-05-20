import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
db = get_client()

# Check both Peeko (7) and Kiddo (9) for null city
rows = (db.table('orders')
          .select('order_id, sku_id, order_date, platform_order_id, city, fulfillment_type')
          .in_('channel_id', [7, 9])
          .is_('city', 'null')
          .execute().data)
print(f'{len(rows)} OUTRIGHT orders with NULL city:')
for r in rows:
    print(f"  {r['order_id']}  {r['sku_id']}  {r['order_date']}  ref={r['platform_order_id']}")
