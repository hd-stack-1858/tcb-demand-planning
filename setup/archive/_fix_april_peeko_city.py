import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
db = get_client()

result = (db.table('orders')
            .update({'city': 'Bengaluru', 'state': 'Karnataka'})
            .eq('platform_order_id', 'GT/26-27/008')
            .eq('channel_id', 7)
            .is_('city', 'null')
            .execute())
print(f'Updated {len(result.data)} rows')
