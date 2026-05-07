"""
Fix txn_id=98: First Cry (FC) DISPATCH has to_channel_id=NULL.
The app was running old code before the dispatch_sku fix was deployed.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
db = get_client()

FC_CHANNEL_ID = 6  # First Cry
result = (db.table('sku_inventory_transactions')
            .update({'to_channel_id': FC_CHANNEL_ID})
            .eq('txn_id', 98)
            .is_('to_channel_id', 'null')
            .execute())
print(f'Updated {len(result.data)} row(s) — txn_id=98 to_channel_id set to {FC_CHANNEL_ID}')
