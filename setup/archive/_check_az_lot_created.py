import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
db = get_client()

lots = (db.table('sku_cogs_lots')
          .select('lot_id, sku_id, qty_assembled, qty_remaining, assembled_at, created_at')
          .eq('channel_id', 2)
          .eq('assembled_at', '2025-12-01')
          .order('created_at')
          .execute().data)

for l in lots:
    print(f"lot={l['lot_id']}  {l['sku_id']:12s}  qty={l['qty_assembled']}  created={l['created_at']}")
