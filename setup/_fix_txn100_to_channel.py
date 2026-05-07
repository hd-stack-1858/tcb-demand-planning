import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
db = get_client()

FNP_CHANNEL_ID = 5
result = (db.table('sku_inventory_transactions')
            .update({'to_channel_id': FNP_CHANNEL_ID})
            .eq('txn_id', 100)
            .is_('to_channel_id', 'null')
            .execute())
print(f'Updated {len(result.data)} row(s) — txn_id=100 to_channel_id set to {FNP_CHANNEL_ID} (FnP)')
