"""Generate seed_blinkit_ds_master.sql with smarter name matching."""
import pandas as pd
import re
import glob

wh_perf_to_code = {
    'Bengaluru B3 - Feeder': 'BLK_WH_1873', 'Bengaluru B3': 'BLK_WH_1873',
    'Bengaluru B5 - Feeder': 'BLK_WH_5397',
    'Hyderabad H3 - Feeder': 'BLK_WH_3201',
    'Kundli - Feeder': 'BLK_WH_2010', 'Kundli Feeder': 'BLK_WH_2010',
    'Faridabad - Feeder': 'BLK_WH_5096',
    'Mumbai M10 - Feeder': 'BLK_WH_2123',
    'Pune P3 - Feeder Warehouse': 'BLK_WH_4572',
}
city_state = {
    'Bengaluru': 'Karnataka', 'Bangalore': 'Karnataka',
    'Hyderabad': 'Telangana', 'Delhi': 'Delhi', 'New Delhi': 'Delhi',
    'Gurgaon': 'Haryana', 'Gurugram': 'Haryana', 'Noida': 'Uttar Pradesh',
    'Mumbai': 'Maharashtra', 'Pune': 'Maharashtra', 'Faridabad': 'Haryana',
}

AGEING_FILE = (
    'data/blinkit/manual/inventory/Ageing/'
    'Ageing Report_1-15 May 2026_1779297327_35d0a22be6554c3ea75a56aadce46df5_seller_data.csv'
)

def strip_prefix(name):
    name = str(name).strip()
    name = re.sub(r'^(Super Store|SS|LT|ES)\s+', '', name, flags=re.IGNORECASE)
    return name.strip().lower()

# ── Load ageing ────────────────────────────────────────────────────────────────
ag = pd.read_csv(AGEING_FILE, low_memory=False)
ag.columns = [c.strip() for c in ag.columns]
ag_ds = ag[['Outlet ID', 'Outlet Name']].dropna(subset=['Outlet ID']).drop_duplicates()
ag_ds['outlet_id_str'] = ag_ds['Outlet ID'].astype(int).astype(str)
ag_ds['name_key']  = ag_ds['Outlet Name'].str.strip().str.lower()
ag_ds['bare_key']  = ag_ds['Outlet Name'].apply(strip_prefix)

# ── Load performance DS ────────────────────────────────────────────────────────
active_whs = list(wh_perf_to_code.keys())
pf_frames = []
for f in glob.glob('data/blinkit/manual/product_performance/detail/*.csv'):
    df = pd.read_csv(f, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    pf_frames.append(
        df[df['Serving warehouse'].isin(active_whs)][['Darkstore name', 'Serving warehouse', 'City']]
    )
pf = pd.concat(pf_frames).drop_duplicates(subset=['Darkstore name', 'Serving warehouse'])
pf['name_key'] = pf['Darkstore name'].str.strip().str.lower()
pf['bare_key'] = pf['Darkstore name'].apply(strip_prefix)

# DS with ADS > 0
pf_ads_f = []
for f in glob.glob('data/blinkit/manual/product_performance/detail/*.csv'):
    df = pd.read_csv(f, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    df['ads_n'] = pd.to_numeric(df['Adjusted units sold per darkstore'], errors='coerce')
    pf_ads_f.append(df[df['Serving warehouse'].isin(active_whs)][['Darkstore name', 'ads_n']])
pf_ads = pd.concat(pf_ads_f)
ds_with_sales = set(pf_ads[pf_ads['ads_n'] > 0]['Darkstore name'].str.lower())

# ── Match: exact, then bare_key + city ────────────────────────────────────────
exact = pf.merge(
    ag_ds[['name_key', 'outlet_id_str']].rename(columns={'name_key': 'ag_key'}),
    left_on='name_key', right_on='ag_key', how='left'
).drop('ag_key', axis=1)

# Build bare_key lookup: bare_key → {city_prefix → outlet_id}
bare_lookup: dict[str, dict[str, str]] = {}
for _, r in ag_ds.iterrows():
    bk = r['bare_key']
    city_word = bk.split()[0] if bk else ''
    bare_lookup.setdefault(bk, {})[city_word] = r['outlet_id_str']

def bare_match(row):
    bk = row['bare_key']
    city_word = bk.split()[0] if bk else ''
    if bk not in bare_lookup:
        return None
    candidates = bare_lookup[bk]
    if city_word in candidates:
        return candidates[city_word]
    if len(candidates) == 1:
        return list(candidates.values())[0]
    return None

unmatched = exact['outlet_id_str'].isna()
for idx, row in exact[unmatched].iterrows():
    resolved = bare_match(row)
    if resolved:
        exact.at[idx, 'outlet_id_str'] = resolved

exact['has_sales']    = exact['name_key'].isin(ds_with_sales)
exact['still_missing'] = exact['outlet_id_str'].isna() & exact['has_sales']

print(f'After smarter matching:')
print(f'  With Outlet ID:            {exact["outlet_id_str"].notna().sum()}')
print(f'  Still missing (has sales): {exact["still_missing"].sum()}')
print('\n=== Still missing (need newer ageing report) ===')
for _, r in exact[exact['still_missing']].iterrows():
    print(f'  {r["Darkstore name"]!r}  [{r["Serving warehouse"]}]')

# ── Generate SQL ───────────────────────────────────────────────────────────────
def make_code(name, outlet_id):
    if pd.notna(outlet_id):
        return f'BLK_DS_{int(float(outlet_id))}'
    m = re.search(r'ES(\d+)\s*(\w*)', name)
    if m:
        suffix = ('_' + m.group(2)) if m.group(2) else ''
        return f'BLK_DS_ES{m.group(1)}{suffix}'
    safe = re.sub(r'[^A-Z0-9]', '_', name[:20].upper())
    return f'BLK_DS_{safe}'

exact['ds_code'] = exact.apply(lambda r: make_code(r['Darkstore name'], r['outlet_id_str']), axis=1)
exact['wh_code'] = exact['Serving warehouse'].map(wh_perf_to_code)
exact['state']   = exact['City'].map(city_state).fillna('')

lines = [
    '-- Blinkit Dark Store Master Seed',
    '-- Generated 2026-05-21 from performance detail CSVs + May 1-15 ageing file.',
    '-- Run AFTER migration 22 is applied to prod.',
    '--',
    '-- Matching: (1) exact name vs ageing Outlet Names;',
    '--   (2) prefix-stripped match (SS/LT/ES/Super Store = store-type tag, not identity).',
    '--',
    '-- DS marked NEEDS_OUTLET_ID: shipped to after May 15 (ageing predates shipment).',
    '-- Fix: download May 16-31 ageing report, then:',
    '--   UPDATE partner_locations SET external_id=<outlet_id> WHERE code=<code>;',
    '',
]

for _, row in exact.sort_values(['wh_code', 'City', 'Darkstore name']).iterrows():
    ds_name = row['Darkstore name'].replace("'", "''")
    ds_code = row['ds_code']
    city    = str(row['City']).replace("'", "''")
    state   = str(row['state']).replace("'", "''")
    wh_code = row['wh_code']
    ext_id  = f"'{int(float(row['outlet_id_str']))}'" if pd.notna(row['outlet_id_str']) else 'NULL'
    flag    = ' -- !! NEEDS_OUTLET_ID' if row['still_missing'] else ''

    lines.append('INSERT INTO partner_locations')
    lines.append('    (channel_id, name, code, city, state, location_type, parent_location_id, external_id, is_active)')
    lines.append(f"SELECT 4, '{ds_name}', '{ds_code}', '{city}', '{state}', 'DARKSTORE',")
    lines.append(f"    (SELECT location_id FROM partner_locations WHERE code = '{wh_code}'),")
    lines.append(f"    {ext_id}, TRUE")
    lines.append(f"ON CONFLICT (code) DO NOTHING;{flag}")
    lines.append('')

out = 'setup/seed_blinkit_ds_master.sql'
with open(out, 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(lines))
print(f'\nSeed SQL written: {out}  ({len(exact)} DS rows)')
