"""
Blinkit Performance Detail Loader
==================================
Loads performance detail CSVs into blinkit_performance_ads and
updates blinkit_ds_sku_eligibility.

Usage:
    python ingest/blinkit_performance_loader.py                 # load all CSVs in detail/
    python ingest/blinkit_performance_loader.py --file path.csv # load single file

Multi-pass logic per file:
    Pass 0a: seed missing dark stores into partner_locations
    Pass 0:  refresh WH→DS parent mapping
    Pass 1:  update DS-SKU eligibility status from darkstore_remark
    Pass 2b: upsert into blinkit_performance_detail (Column Q as OOS signal)

New ADS formula (blinkit_performance_detail):
    SUM(total_orders WHERE inventory_available=True) / COUNT(inventory_available=True days)
    per (sku_id, location_id) over rolling 30-day window
"""

import os
import sys
import glob
import argparse
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

# ── Environment ────────────────────────────────────────────────────────────────
env = os.environ.get('TCB_ENV', 'prod')
load_dotenv('.env' if env == 'prod' else '.env.dev')
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

# ── Constants ──────────────────────────────────────────────────────────────────
CHANNEL_CODE   = 'BLK'
DETAIL_DIR_MAN = Path('data/blinkit/manual/product_performance/detail')
DETAIL_DIR_AUTO = Path('data/blinkit/auto/product_performance/detail')
BATCH_SIZE     = 200

INSUFFICIENT_INV = 'Insufficient Inventory at warehouse for transfers'
ITEM_NOT_RESTOCKED = 'Item not restocked by you on serving warehouse for last 30 days'
FE_MOVEMENT_BLOCKED = 'FE movement bottlenecked due to store space'

# Keyword-based remark rules — ALL keywords must appear in the remark (case-insensitive).
# More robust than exact matching: survives "(in progress)", punctuation changes, minor rewording.
# Add a new tuple here if Blinkit introduces a new status we haven't seen before.
REMARK_RULES = [
    (['redistribution', 'lack of sales'],       'sku_moved_out_low_sales'),
    (['store has been closed'],                  'darkstore_closed'),
    (['launch awaited', 'not replenished'],      'launch_awaited'),
    (['opted out of selling'],                   'sku_city_exited'),
    (['initiated recall'],                       'sku_recalled'),
]


def match_remark(remark: str) -> str | None:
    """Return eligibility status for a remark string, or None if no rule matches."""
    r = remark.strip().lower()
    for keywords, status in REMARK_RULES:
        if all(kw in r for kw in keywords):
            return status
    return None

# Performance file "Serving warehouse" → partner_locations code (all 20 active WHs)
WH_PERF_TO_CODE = {
    'Ahmedabad A2 - Feeder':       'BLK_WH_2470',
    'Bengaluru B3 - Feeder':       'BLK_WH_1873',
    'Bengaluru B3':                'BLK_WH_1873',
    'Bengaluru B5 - Feeder':       'BLK_WH_5397',
    'Chennai C5 - Feeder':         'BLK_WH_3262',
    'Coimbatore C1 - Feeder':      'BLK_WH_2681',
    'Faridabad - Feeder':          'BLK_WH_5096',
    'Guwahati G1 - Feeder':        'BLK_WH_3213',
    'Hyderabad H3 - Feeder':       'BLK_WH_3201',
    'Jaipur J3 - Feeder':          'BLK_WH_3200',
    'Kolkata K4 - Feeder':         'BLK_WH_2015',
    'Kolkata K6 - Feeder':         'BLK_WH_4842',
    'Kundli - Feeder':             'BLK_WH_2010',
    'Kundli Feeder':               'BLK_WH_2010',
    'Lucknow L4':                  'BLK_WH_1206',
    'Super Store Lucknow L4':      'BLK_WH_1206',
    'Mumbai M10 - Feeder':         'BLK_WH_2123',
    'Nagpur N1 - Feeder':          'BLK_WH_2468',
    'Noida N1 - Feeder':           'BLK_WH_2576',
    'Patna P1 - Feeder':           'BLK_WH_2960',
    'Pune P3 - Feeder':            'BLK_WH_4572',
    'Pune P3 - Feeder Warehouse':  'BLK_WH_4572',
    'Rajpura R2 - Feeder':         'BLK_WH_4571',
    'Rajpura R2 - Feeder Warehouse': 'BLK_WH_4571',
    'Visakhapatnam V1 - Feeder':   'BLK_WH_2670',
}


# ── Lookup caches (built once per run) ────────────────────────────────────────

def build_sku_lookup():
    """item_id (str) → sku_id from sku_channel_ids.platform_pid_additional"""
    rows = sb.table('sku_channel_ids') \
             .select('sku_id, platform_pid_additional') \
             .eq('channel_code', CHANNEL_CODE) \
             .execute().data
    return {str(r['platform_pid_additional']): r['sku_id']
            for r in rows if r.get('platform_pid_additional')}


def build_wh_location_lookup():
    """partner_locations code → location_id for WH rows"""
    rows = sb.table('partner_locations') \
             .select('location_id, code') \
             .eq('location_type', 'WH') \
             .eq('channel_id', 4) \
             .execute().data
    return {r['code']: r['location_id'] for r in rows}


def _bare_name(name: str) -> str:
    """Strip store-type prefix (ES/LT/SS/Super Store) — same DS, different prefix across exports."""
    return re.sub(r'^(Super Store|SS|LT|ES)\s+', '', name.strip(), flags=re.IGNORECASE).strip().lower()


def build_ds_parent_lookup() -> dict:
    """location_id → current parent_location_id for all Blinkit DS rows."""
    rows = sb.table('partner_locations') \
             .select('location_id, parent_location_id') \
             .eq('location_type', 'DARKSTORE') \
             .eq('channel_id', 4) \
             .execute().data
    return {r['location_id']: r['parent_location_id'] for r in rows}


def build_ds_location_lookup():
    """
    Returns two dicts for DS name → location_id matching:
      exact: full name (lowercase) → location_id
      bare:  prefix-stripped name  → location_id  (fallback)
    Returns a single merged dict; bare match fills gaps left by exact.
    """
    rows = sb.table('partner_locations') \
             .select('location_id, name') \
             .eq('location_type', 'DARKSTORE') \
             .eq('channel_id', 4) \
             .execute().data
    lookup = {}
    for r in rows:
        name = r['name']
        loc  = r['location_id']
        lookup[name.strip().lower()] = loc   # exact
        lookup[_bare_name(name)]     = loc   # bare (may overwrite, that's fine)
    return lookup


# ── File parsing ───────────────────────────────────────────────────────────────

REQUIRED_COLS = {'Item ID', 'Darkstore name', 'Considered for assessment (Y/N)',
                 'Serving warehouse', 'Date', 'Total orders'}

def load_file(filepath: Path) -> pd.DataFrame | None:
    """Return None if the file is not the full performance detail format."""
    df = pd.read_csv(filepath, nrows=0)
    df.columns = [c.strip() for c in df.columns]
    if not REQUIRED_COLS.issubset(set(df.columns)):
        print(f'  [SKIP] {filepath.name}: missing required columns — not a performance detail CSV')
        return None

    df = pd.read_csv(filepath, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    df['ads_n']   = pd.to_numeric(df['Adjusted units sold per darkstore'], errors='coerce')
    df['orders_n'] = pd.to_numeric(df['Total orders'], errors='coerce').fillna(0).astype(int)
    df['avail_h']  = pd.to_numeric(df['Available hours'], errors='coerce')
    df['op_h']     = pd.to_numeric(df['Operation hours'], errors='coerce')
    df['data_date'] = pd.to_datetime(
        df['Date'].str.replace(r'\s+\+\d{4}\s+UTC', '', regex=True),
        utc=True, errors='coerce'
    ).dt.date
    df['a_start'] = pd.to_datetime(
        df['Assessment Period Start Date'].str.replace(r'\s+\+\d{4}\s+UTC', '', regex=True),
        utc=True, errors='coerce'
    ).dt.date
    df['a_end'] = pd.to_datetime(
        df['Assessment Period End Date'].str.replace(r'\s+\+\d{4}\s+UTC', '', regex=True),
        utc=True, errors='coerce'
    ).dt.date

    # Column Q — inventory_available: DS-level stock flag
    # Column header is "Available (Yes/No)" with values 0/1 (may also appear as Y/N or Yes/No)
    _INV_PATTERNS = ['available (yes/no)', 'inventory available', 'available (y/n)']
    inv_col = next(
        (c for c in df.columns if any(p in c.strip().lower() for p in _INV_PATTERNS)),
        None,
    )
    if inv_col:
        raw_av = df[inv_col].astype(str).str.strip().str.upper()
        df['inv_available'] = raw_av.isin(['1', 'Y', 'YES', 'TRUE'])
    else:
        df['inv_available'] = True   # default: assume available if column absent

    # Column Y — orders with complaint attributed to seller
    complaint_col = next(
        (c for c in df.columns
         if 'complaint' in c.lower() and 'seller' in c.lower()), None
    )
    if complaint_col:
        df['complaint_orders'] = pd.to_numeric(df[complaint_col], errors='coerce').fillna(0).astype(int)
    else:
        df['complaint_orders'] = 0

    # Column J — city (may appear as "City" or "Delivery City")
    city_col = next(
        (c for c in df.columns if c.strip().lower() in ('city', 'delivery city')), None
    )
    df['city_val'] = df[city_col].fillna('').str.strip() if city_col else ''

    # Infer download_date from filename (first 10-digit numeric prefix)
    fname = filepath.name
    m = re.match(r'^(\d{10})', fname)
    ts = int(m.group(1)) if m else None
    df['download_date'] = (
        date.fromtimestamp(ts) if ts else date.today()
    )
    return df


def normalize_wh_name(name: str) -> str | None:
    """Map performance 'Serving warehouse' to partner_locations code. None if unknown."""
    return WH_PERF_TO_CODE.get(name)


_ES_RE = re.compile(r'\bES(\d+)\s*$', re.IGNORECASE)


def _ds_code(name: str) -> str:
    """Generate a stable, globally unique partner_locations code from a DS name.
    ES numbers are NOT globally unique across cities, so we hash the full name.
    Appends the ES suffix for human readability when present."""
    import hashlib
    h = hashlib.md5(name.strip().lower().encode()).hexdigest()[:8].upper()
    m = _ES_RE.search(name.strip())
    suffix = f'_ES{m.group(1)}' if m else ''
    return f'BLK_DS_{h}{suffix}'


# ── Pass 0a: seed DS master from performance file ──────────────────────────────

def scan_ds_from_files(files: list[Path]) -> tuple[dict[str, str], dict[str, str], set[str]]:
    """
    Quick 3-column scan of all performance CSVs.
    Returns:
      ds_to_wh_name: {ds_name → serving_wh_name}  (latest WH per DS name wins)
      ds_to_city:    {ds_name → delivery_city}     (latest city per DS name wins)
      latest_ds:     set of DS names in the chronologically latest file
    """
    all_pairs:  list[tuple[str, str, str, str]] = []   # (filename, ds_name, wh_name, city)
    for fpath in files:
        try:
            hdr = pd.read_csv(fpath, nrows=0)
            hdr.columns = [c.strip() for c in hdr.columns]
            if not REQUIRED_COLS.issubset(set(hdr.columns)):
                continue
            col_names = set(hdr.columns)
            city_col = 'City' if 'City' in col_names else (
                       'Delivery City' if 'Delivery City' in col_names else None)
            cols = ['Darkstore name', 'Serving warehouse']
            if city_col:
                cols.append(city_col)
            df = pd.read_csv(fpath, usecols=cols, low_memory=False)
            df.columns = [c.strip() for c in df.columns]
            df = df.dropna(subset=['Darkstore name', 'Serving warehouse'])
            for _, row in df.iterrows():
                city = str(row.get(city_col, '') or '').strip() if city_col else ''
                all_pairs.append((
                    fpath.name,
                    str(row['Darkstore name']).strip(),
                    str(row['Serving warehouse']).strip(),
                    city,
                ))
        except Exception:
            continue

    if not all_pairs:
        return {}, {}, set()

    # Latest file DS list (for is_active=False logic)
    latest_file = sorted({p[0] for p in all_pairs})[-1]
    latest_ds   = {p[1] for p in all_pairs if p[0] == latest_file}

    # ds_name → WH name and city (latest file wins, then alphabetically last)
    ds_to_wh:   dict[str, str] = {}
    ds_to_city: dict[str, str] = {}
    for fname, ds, wh, city in sorted(all_pairs, key=lambda x: x[0]):
        ds_to_wh[ds] = wh
        if city:
            ds_to_city[ds] = city

    return ds_to_wh, ds_to_city, latest_ds


def refresh_ds_master(ds_to_wh_name: dict[str, str], wh_lookup: dict,
                      ds_lookup: dict,
                      ds_to_city: dict[str, str] | None = None) -> int:
    """
    Seed any DS that appear in the performance file but are missing from
    partner_locations.  Never deletes or deactivates — only inserts.
    Returns count of new rows inserted.
    """
    # Fetch existing codes so we can skip collisions
    existing_codes: set[str] = {
        r['code'] for r in
        sb.table('partner_locations').select('code')
          .eq('channel_id', 4).execute().data
        if r.get('code')
    }

    new_rows:  list[dict] = []
    skipped_wh = set()

    for ds_name, wh_name in ds_to_wh_name.items():
        # Already seeded by name?
        if ds_lookup.get(ds_name.lower()) or ds_lookup.get(_bare_name(ds_name)):
            continue

        wh_code = WH_PERF_TO_CODE.get(wh_name)
        if not wh_code:
            skipped_wh.add(wh_name)
            continue
        wh_id = wh_lookup.get(wh_code)
        if not wh_id:
            continue

        code = _ds_code(ds_name)
        if code in existing_codes:
            continue  # code collision — DS already exists under a different name variant

        city = (ds_to_city or {}).get(ds_name) or None

        new_rows.append({
            'channel_id':         4,
            'location_type':      'DARKSTORE',
            'name':               ds_name,
            'code':               code,
            'parent_location_id': wh_id,
            'is_active':          True,
            'external_id':        None,
            'city':               city,
        })
        existing_codes.add(code)   # prevent duplicate within this batch

    CHUNK = 50
    inserted = 0
    for i in range(0, len(new_rows), CHUNK):
        sb.table('partner_locations').insert(new_rows[i:i + CHUNK]).execute()
        inserted += len(new_rows[i:i + CHUNK])

    if skipped_wh:
        print(f'  [WARN] Pass 0a: {len(skipped_wh)} WH names not in WH_PERF_TO_CODE (DS skipped): '
              f'{sorted(skipped_wh)}')
    return inserted


def update_ds_cities(ds_to_city: dict[str, str], ds_lookup: dict) -> int:
    """
    For every DS with a known city from the performance CSV, update
    partner_locations.city if it is currently NULL or different.
    Returns count of rows updated.
    """
    if not ds_to_city:
        return 0

    # Fetch current city values for all Blinkit DS
    rows = sb.table('partner_locations') \
             .select('location_id, name, city') \
             .eq('location_type', 'DARKSTORE') \
             .eq('channel_id', 4) \
             .execute().data
    current_city: dict[int, str | None] = {r['location_id']: r.get('city') for r in rows}

    updated = 0
    for ds_name, city in ds_to_city.items():
        if not city:
            continue
        loc_id = ds_lookup.get(ds_name.lower()) or ds_lookup.get(_bare_name(ds_name))
        if not loc_id:
            continue
        if current_city.get(loc_id) == city:
            continue  # already correct
        sb.table('partner_locations').update({'city': city}) \
          .eq('location_id', loc_id).execute()
        updated += 1

    return updated


def update_is_active(latest_ds_names: set[str], ds_lookup: dict,
                     all_blinkit_ds_ids: set[int]) -> tuple[int, int]:
    """
    After loading all files, sync is_active for every Blinkit DS:
      DS in latest performance file → is_active=True
      DS not in latest performance file → is_active=False
    Returns (activated, deactivated) counts.
    """
    active_ids: set[int] = set()
    for ds_name in latest_ds_names:
        loc_id = ds_lookup.get(ds_name.lower()) or ds_lookup.get(_bare_name(ds_name))
        if loc_id:
            active_ids.add(loc_id)

    inactive_ids = all_blinkit_ds_ids - active_ids

    # Bulk update active
    if active_ids:
        for i in range(0, len(active_ids), 100):
            chunk = list(active_ids)[i:i + 100]
            sb.table('partner_locations').update({'is_active': True}) \
              .in_('location_id', chunk).execute()

    # Bulk update inactive
    if inactive_ids:
        for i in range(0, len(inactive_ids), 100):
            chunk = list(inactive_ids)[i:i + 100]
            sb.table('partner_locations').update({'is_active': False}) \
              .in_('location_id', chunk).execute()

    return len(active_ids), len(inactive_ids)


# ── Pass 0: refresh WH-DS mapping ────────────────────────────────────────────

def update_wh_ds_mapping(df: pd.DataFrame, ds_lookup: dict,
                         wh_lookup: dict, ds_parent_lookup: dict) -> int:
    """
    For every DS in the file, check if its Serving warehouse matches
    partner_locations.parent_location_id. Update if it has changed.
    The performance file is the source of truth for WH-DS assignments.
    """
    our_whs = set(WH_PERF_TO_CODE.keys())

    # One row per (DS name, Serving warehouse) — take the most recent date
    mapping = (
        df[df['Serving warehouse'].isin(our_whs)]
        [['Darkstore name', 'Serving warehouse', 'data_date']]
        .dropna(subset=['Darkstore name', 'Serving warehouse'])
        .sort_values('data_date', ascending=False)
        .drop_duplicates(subset=['Darkstore name'])   # latest WH per DS
    )

    updated = 0
    unknown_wh  = set()
    unknown_ds  = set()

    for _, row in mapping.iterrows():
        raw_ds  = str(row['Darkstore name']).strip()
        wh_name = str(row['Serving warehouse']).strip()

        ds_id = ds_lookup.get(raw_ds.lower()) or ds_lookup.get(_bare_name(raw_ds))
        if not ds_id:
            unknown_ds.add(raw_ds)
            continue

        wh_code = WH_PERF_TO_CODE.get(wh_name)
        if not wh_code:
            unknown_wh.add(wh_name)
            continue

        new_parent = wh_lookup.get(wh_code)
        if not new_parent:
            continue

        current_parent = ds_parent_lookup.get(ds_id)
        if current_parent == new_parent:
            continue  # already correct

        sb.table('partner_locations').update(
            {'parent_location_id': new_parent}
        ).eq('location_id', ds_id).execute()
        ds_parent_lookup[ds_id] = new_parent   # update local cache
        updated += 1
        print(f'    [REMAP] DS {raw_ds!r} -> {wh_name}')

    if unknown_ds:
        print(f'  [WARN] Pass 0: {len(unknown_ds)} DS not in partner_locations (skipped remap)')
    return updated


# ── Pass 1: update DS-SKU eligibility ─────────────────────────────────────────

def update_eligibility(df: pd.DataFrame, sku_lookup: dict, ds_lookup: dict):
    """
    Determine each DS-SKU's status from its LATEST data_date in this file.

    Y on latest date  → status = 'active'   (resets stale non-active status)
    N on latest date  → status = remark rule (closed / low_sales / launched / etc.)
    N with no remark  → skip (no actionable status)
    """
    item_col   = 'Item ID'
    remark_col = 'Darkstore remark'
    flag_col   = 'Considered for assessment (Y/N)'

    # One row per (item_id, DS_name): the latest data_date row for that pair
    latest_per_pair = (
        df.sort_values('data_date', ascending=False)
        .drop_duplicates(subset=[item_col, 'Darkstore name'])
    )

    records        = []
    unknown_ds      = set()
    unknown_sku     = set()
    unknown_remarks = set()

    for _, row in latest_per_pair.iterrows():
        sku_id = sku_lookup.get(str(row[item_col]))
        if not sku_id:
            unknown_sku.add(row[item_col])
            continue

        raw_ds = str(row['Darkstore name']).strip()
        ds_id  = ds_lookup.get(raw_ds.lower()) or ds_lookup.get(_bare_name(raw_ds))
        if not ds_id:
            unknown_ds.add(raw_ds)
            continue

        flag   = str(row.get(flag_col, '')).strip()
        remark_val = row.get(remark_col, '')
        remark = str(remark_val).strip() if pd.notna(remark_val) else ''

        if flag == 'Y':
            status      = 'active'
            last_remark = None
        elif remark:
            status = match_remark(remark)
            if not status:
                unknown_remarks.add(remark)
                continue
            last_remark = remark
        else:
            # N with blank Darkstore remark — check Col S (Remarks) for FE movement block
            remarks_s = str(row.get('Remarks', '') or '').strip()
            if FE_MOVEMENT_BLOCKED in remarks_s:
                status      = 'ds_choked'
                last_remark = remarks_s
            else:
                if remarks_s:
                    print(f'  [WARN] Unclassified N-row (blank DS remark), Remarks: {remarks_s!r}')
                continue  # no actionable status

        records.append({
            'location_id':  ds_id,
            'sku_id':       sku_id,
            'status':       status,
            'last_remark':  last_remark,
            'updated_date': str(row['data_date']),
        })

    # Batch upsert in small chunks (Supabase HTTP/2 limit)
    CHUNK = 50
    for i in range(0, len(records), CHUNK):
        sb.table('blinkit_ds_sku_eligibility') \
          .upsert(records[i:i + CHUNK], on_conflict='location_id,sku_id') \
          .execute()

    if unknown_sku:
        print(f'  [WARN] Unknown Item IDs (not in sku_channel_ids): {sorted(unknown_sku)}')
    if unknown_ds:
        print(f'  [WARN] Unknown dark stores (not in partner_locations): {len(unknown_ds)} DS')
    if unknown_remarks:
        print(f'  [WARN] {len(unknown_remarks)} remark(s) matched no rule — add to REMARK_RULES if needed:')
        for r in sorted(unknown_remarks):
            print(f'    {r!r}')

    return len(records)


# ── Pass 2b: upsert into blinkit_performance_detail ───────────────────────────

def upsert_detail(df: pd.DataFrame, sku_lookup: dict, ds_lookup: dict):
    """
    Load Y-rows into blinkit_performance_detail.
    Uses inventory_available (Column Q) as the DS-level OOS signal.
    Runs in parallel with upsert_ads() during migration period.
    """
    our_whs = set(WH_PERF_TO_CODE.keys())
    y_rows  = df[
        (df['Considered for assessment (Y/N)'] == 'Y') &
        (df['Serving warehouse'].isin(our_whs))
    ].copy()

    if y_rows.empty:
        return 0, 0

    inserted  = 0
    skipped   = 0
    unknown_ds = set()
    batch     = []

    for _, row in y_rows.iterrows():
        sku_id = sku_lookup.get(str(row['Item ID']))
        if not sku_id:
            skipped += 1
            continue

        raw_ds = str(row['Darkstore name']).strip()
        ds_id  = ds_lookup.get(raw_ds.lower()) or ds_lookup.get(_bare_name(raw_ds))
        if not ds_id:
            unknown_ds.add(raw_ds)
            skipped += 1
            continue

        if not row['data_date']:
            skipped += 1
            continue

        city = str(row.get('city_val', '') or '').strip() or None

        batch.append({
            'data_date':             str(row['data_date']),
            'location_id':           ds_id,
            'sku_id':                sku_id,
            'ds_name':               raw_ds,
            'city':                  city,
            'serving_wh':            str(row.get('Serving warehouse', '') or '').strip() or None,
            'inventory_available':   bool(row.get('inv_available', True)),
            'total_orders':          int(row['orders_n']),
            'orders_with_complaint': int(row.get('complaint_orders', 0)),
            'download_date':         str(row['download_date']),
        })

        if len(batch) >= BATCH_SIZE:
            sb.table('blinkit_performance_detail').upsert(
                batch,
                on_conflict='data_date,location_id,sku_id'
            ).execute()
            inserted += len(batch)
            batch = []

    if batch:
        sb.table('blinkit_performance_detail').upsert(
            batch,
            on_conflict='data_date,location_id,sku_id'
        ).execute()
        inserted += len(batch)

    if unknown_ds:
        print(f'  [WARN] Pass 2b: {len(unknown_ds)} DS not in partner_locations — '
              f'{len(unknown_ds)} unique stores skipped')

    # Trigger 2: Column Q data integrity guard
    # inventory_available=False but total_orders>0 should never happen — orders cannot
    # be placed if Column Q flags inventory as unavailable. Fires if Column Q has bad data.
    t2_check = y_rows[~y_rows['inv_available'] & (y_rows['orders_n'] > 0)]
    if not t2_check.empty:
        print(f'\n[ALERT] Trigger 2: {len(t2_check)} Y-row(s) have inventory_available=False '
              f'but total_orders>0. Orders placed despite Column Q flagging inventory unavailable '
              f'— Column Q may have a data quality issue. Check these rows.')

    return inserted, skipped


# ── Main ───────────────────────────────────────────────────────────────────────

def propagate_darkstore_closed() -> tuple[int, int]:
    """
    Physical store closure is permanent and affects all SKUs.
    Pass A: update existing non-closed rows for closed DS → darkstore_closed.
    Pass B: insert rows for SKUs that were never deployed to a now-closed DS
            (these have no eligibility row at all, so Pass A misses them).
    Only propagates to DS with ZERO active rows — a DS with any active row has
    reopened and must not be overwritten.
    Returns (rows_updated, rows_inserted).
    """
    CHUNK = 100

    # Find all DS that have at least one darkstore_closed row
    rows = sb.table('blinkit_ds_sku_eligibility') \
             .select('location_id') \
             .eq('status', 'darkstore_closed') \
             .execute().data
    closed_ds_ids = {r['location_id'] for r in rows}
    if not closed_ds_ids:
        return 0, 0

    # Exclude DS that have any active row — those DS have reopened
    active_rows = sb.table('blinkit_ds_sku_eligibility') \
                   .select('location_id') \
                   .eq('status', 'active') \
                   .execute().data
    active_ds_ids = {r['location_id'] for r in active_rows}
    closed_ds_ids = list(closed_ds_ids - active_ds_ids)
    if not closed_ds_ids:
        return 0, 0

    # Pass A: update existing rows that are not yet darkstore_closed
    updated = 0
    for i in range(0, len(closed_ds_ids), CHUNK):
        chunk = closed_ds_ids[i:i + CHUNK]
        result = (sb.table('blinkit_ds_sku_eligibility')
                    .update({'status': 'darkstore_closed',
                             'last_remark': 'store has been closed (propagated from sibling SKU)'})
                    .in_('location_id', chunk)
                    .neq('status', 'darkstore_closed')
                    .execute())
        updated += len(result.data) if result.data else 0

    # Pass B: insert rows for SKUs with NO record at all for these closed DS
    all_sku_ids = [r['sku_id'] for r in
                   sb.table('skus').select('sku_id').eq('is_discontinued', False).execute().data]

    # Collect all existing (location_id, sku_id) pairs for closed DS
    existing: set[tuple] = set()
    for i in range(0, len(closed_ds_ids), CHUNK):
        chunk = closed_ds_ids[i:i + CHUNK]
        ex = (sb.table('blinkit_ds_sku_eligibility')
                .select('location_id,sku_id')
                .in_('location_id', chunk)
                .execute().data)
        for r in ex:
            existing.add((r['location_id'], r['sku_id']))

    # Build missing pairs
    today_str = date.today().isoformat()
    to_insert = [
        {'location_id': ds_id, 'sku_id': sku_id,
         'status': 'darkstore_closed',
         'last_remark': 'store has been closed (inserted — SKU never deployed here)',
         'updated_date': today_str}
        for ds_id in closed_ds_ids
        for sku_id in all_sku_ids
        if (ds_id, sku_id) not in existing
    ]

    inserted = 0
    for i in range(0, len(to_insert), CHUNK):
        result = (sb.table('blinkit_ds_sku_eligibility')
                    .upsert(to_insert[i:i + CHUNK],
                            on_conflict='location_id,sku_id')
                    .execute())
        inserted += len(result.data) if result.data else 0

    return updated, inserted


def process_file(filepath: Path, sku_lookup: dict, ds_lookup: dict,
                 wh_lookup: dict, ds_parent_lookup: dict):
    print(f'\n  Loading: {filepath.name}')
    df = load_file(filepath)
    if df is None:
        return
    print(f'    Rows in file: {len(df):,}')

    # Pass 0: refresh WH-DS mapping
    remapped = update_wh_ds_mapping(df, ds_lookup, wh_lookup, ds_parent_lookup)
    print(f'    Pass 0 (WH-DS remap): {remapped} DS parent_location_id updated')

    # Pass 1: eligibility
    elig_count = update_eligibility(df, sku_lookup, ds_lookup)
    print(f'    Pass 1 (eligibility): {elig_count} status rows upserted')

    # Pass 2b: detail table (Column Q as OOS signal)
    ins2, skip2 = upsert_detail(df, sku_lookup, ds_lookup)
    print(f'    Pass 2b (detail):     {ins2} rows upserted, {skip2} skipped')


def main():
    parser = argparse.ArgumentParser(description='Blinkit performance detail loader')
    parser.add_argument('--file', help='Load a single CSV file')
    parser.add_argument('--dry-run', action='store_true', help='Parse only, no DB writes')
    args = parser.parse_args()

    print(f'Environment: {env}')
    if args.dry_run:
        print('DRY RUN — no DB writes')

    print('Building lookup tables...')
    sku_lookup       = build_sku_lookup()
    ds_lookup        = build_ds_location_lookup()
    wh_lookup        = build_wh_location_lookup()
    ds_parent_lookup = build_ds_parent_lookup()
    print(f'  SKUs:        {len(sku_lookup)}')
    print(f'  Dark stores: {len(ds_lookup)}')
    print(f'  Warehouses:  {len(wh_lookup)}')

    if args.file:
        files = [Path(args.file)]
    else:
        # Scan both manual (user-downloaded) and auto (scraper-downloaded) dirs
        manual = sorted(DETAIL_DIR_MAN.glob('*.csv')) if DETAIL_DIR_MAN.exists() else []
        auto   = sorted(DETAIL_DIR_AUTO.glob('*.csv')) if DETAIL_DIR_AUTO.exists() else []
        # Deduplicate by filename — prefer manual copy if same name in both
        seen   = {f.name for f in manual}
        files  = manual + [f for f in auto if f.name not in seen]
        files  = sorted(files, key=lambda f: f.name)

    # Pass 0a: seed missing DS from performance files into partner_locations
    if not args.dry_run:
        print('\nPass 0a: refreshing DS master from performance files...')
        ds_to_wh_name, ds_to_city, latest_ds = scan_ds_from_files(files)
        new_ds_count = refresh_ds_master(ds_to_wh_name, wh_lookup, ds_lookup,
                                         ds_to_city=ds_to_city)
        if new_ds_count:
            print(f'  Inserted {new_ds_count} new DS into partner_locations')
            # Rebuild lookup so subsequent passes see the new DS
            ds_lookup        = build_ds_location_lookup()
            ds_parent_lookup = build_ds_parent_lookup()
            print(f'  Dark stores (updated): {len(ds_lookup)}')
        else:
            print(f'  No new DS found')
        city_updated = update_ds_cities(ds_to_city, ds_lookup)
        print(f'  City backfill: {city_updated} DS city values updated')

    print(f'\nFiles to process: {len(files)}')
    total_ins = 0
    for f in files:
        if not args.dry_run:
            process_file(f, sku_lookup, ds_lookup, wh_lookup, ds_parent_lookup)
        else:
            df = load_file(f)
            if df is None:
                continue
            our_whs = set(WH_PERF_TO_CODE.keys())
            y_rows = df[
                (df['Considered for assessment (Y/N)'] == 'Y') &
                (df['Serving warehouse'].isin(our_whs))
            ]
            print(f'  {f.name}: {len(df):,} rows total, {len(y_rows):,} Y-rows for our WHs')

    # Pass 1b: propagate darkstore_closed to all SKUs for physically closed DS
    if not args.dry_run:
        prop_updated, prop_inserted = propagate_darkstore_closed()
        print(f'\nPass 1b (propagate closed): {prop_updated} rows updated, {prop_inserted} rows inserted to darkstore_closed')

    # Pass 0a post-step: sync is_active for all Blinkit DS based on latest file
    if not args.dry_run and not args.file:
        print('\nPass 0a (post): syncing is_active for all Blinkit DS...')
        # Refresh lookup after all inserts above
        ds_lookup_final = build_ds_location_lookup()
        all_blinkit_ds_ids = set(ds_lookup_final.values())
        activated, deactivated = update_is_active(latest_ds, ds_lookup_final, all_blinkit_ds_ids)
        print(f'  Active: {activated} | Deactivated: {deactivated}')

    # Trigger 1: DS that are active in DB but absent from the latest file entirely
    # (vanished-Y DS — went active then dropped without going through N first)
    if not args.dry_run:
        _check_trigger1_vanished_y(files, sku_lookup, ds_lookup)

    print('\nDone.')


def _check_trigger1_vanished_y(files: list[Path], sku_lookup: dict, ds_lookup: dict):
    """
    Trigger 1: Alert if any DS-SKU pair is status='active' in DB
    but completely absent from the latest performance file.
    These DS were selling (Y) then vanished without going through N — raise with Blinkit.
    """
    if not files:
        return

    latest_file = max(files, key=lambda f: f.stat().st_mtime)

    try:
        hdr = pd.read_csv(latest_file, nrows=0)
        hdr.columns = [c.strip() for c in hdr.columns]
        if not REQUIRED_COLS.issubset(set(hdr.columns)):
            return
        df = pd.read_csv(latest_file,
                         usecols=['Item ID', 'Darkstore name'],
                         low_memory=False)
        df.columns = [c.strip() for c in df.columns]
    except Exception:
        return

    df = df.dropna(subset=['Item ID', 'Darkstore name'])

    # All DS-SKU pairs present in latest file (Y or N)
    latest_pairs: set[tuple] = set()
    for _, row in df.iterrows():
        sku_id = sku_lookup.get(str(row['Item ID']).strip())
        raw_ds = str(row['Darkstore name']).strip()
        ds_id  = ds_lookup.get(raw_ds.lower()) or ds_lookup.get(_bare_name(raw_ds))
        if sku_id and ds_id:
            latest_pairs.add((ds_id, sku_id))

    # Active DS-SKU pairs in DB
    page, offset, page_size = [], 0, 1000
    while True:
        batch = (sb.table('blinkit_ds_sku_eligibility')
                   .select('location_id,sku_id')
                   .eq('status', 'active')
                   .range(offset, offset + page_size - 1)
                   .execute().data)
        page.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    active_db_pairs = {(r['location_id'], r['sku_id']) for r in page}
    vanished = active_db_pairs - latest_pairs

    if vanished:
        print(f'\n[ALERT] Trigger 1: {len(vanished)} DS-SKU pair(s) are active in DB '
              f'but absent from latest file ({latest_file.name}).')
        print('  These DS were selling (Y) but vanished from the assessment file.')
        print('  Raise with Blinkit to understand why they dropped.')
        shown = sorted(vanished)[:20]
        for ds_id, sku_id in shown:
            print(f'    location_id={ds_id}, sku_id={sku_id}')
        if len(vanished) > 20:
            print(f'    ... and {len(vanished) - 20} more')


if __name__ == '__main__':
    main()
