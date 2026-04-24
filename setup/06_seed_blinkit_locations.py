"""
Seed script: loads Blinkit feeder warehouses from Blinkit-warehouses.xlsx
into blinkit_locations table (location_type='WH').
Darkstores will be added later when Blinkit inventory reports are available.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8')
from tcb.db import get_client
import openpyxl

EXCEL = os.path.join(os.path.dirname(__file__), '..', 'master files', 'Blinkit-warehouses.xlsx')
db = get_client()

blk_channel_id = (db.table("channels").select("channel_id")
                    .eq("code", "BLK").single().execute().data["channel_id"])

wb = openpyxl.load_workbook(EXCEL, data_only=True)
ws = wb["Blinkit WH"]
rows = list(ws.iter_rows(values_only=True))[1:]  # skip header

print("Seeding blinkit_locations (WHs)...")

wh_rows = []
for r in rows:
    if not r[0]:
        continue
    name        = str(r[0]).strip()
    facility_id = int(r[1]) if r[1] else None
    state       = str(r[2]).strip() if r[2] else None
    address     = str(r[3]).strip() if r[3] else None
    stock_sent  = str(r[4]).strip().lower() == "yes" if r[4] else False

    # code: BLK_WH_<facility_id>
    code = f"BLK_WH_{facility_id}" if facility_id else None

    # city: first word(s) before first space+uppercase pattern — just use name prefix
    city = name.split(" ")[0]

    wh_rows.append({
        "channel_id":         blk_channel_id,
        "name":               name,
        "code":               code,
        "city":               city,
        "state":              state,
        "address":            address,
        "blinkit_facility_id": facility_id,
        "stock_sent":         stock_sent,
        "location_type":      "WH",
        "is_active":          True,
    })

for row in wh_rows:
    db.table("blinkit_locations").upsert(row, on_conflict="code").execute()

print(f"  blinkit_locations: {len(wh_rows)} WHs upserted")
sent = sum(1 for r in wh_rows if r["stock_sent"])
print(f"  Stock sent to {sent} WHs: {[r['name'] for r in wh_rows if r['stock_sent']]}")
print("\nDone. Darkstores will be added from Blinkit inventory reports.")
