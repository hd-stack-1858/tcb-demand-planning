"""
Blinkit Replenishment Engine
=============================
Computes how many units to ship to each Blinkit WH per SKU.

Formula per WH × SKU:
    ADS_per_DS   = SUM(total_orders WHERE NOT wh_oos_flag)
                 / COUNT(days WHERE NOT wh_oos_flag)
                 within the latest assessment period for that SKU

    total_demand = SUM(ADS_per_DS across active eligible DS) × coverage_days
    transit_buf  = SUM(ADS_per_DS) × transit_buffer_days
    target_stock = total_demand + transit_buf
    eff_stock    = units_wh + units_incoming  (latest SOH snapshot)
    units_to_ship = max(0, target_stock − eff_stock)

Coverage : 30 days  (monthly shipping cadence)
Buffer   : 7 days   (in-transit safety stock)
Gate     : ₹1,50,000 invoice value per WH before that WH's shipment is triggered

Usage:
    python tcb/replenishment.py                        # run plan with latest data
    python tcb/replenishment.py --snapshot 2026-05-21  # use a specific SOH date
    python tcb/replenishment.py --dry-run              # print, don't write Excel
"""

import os
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path

# Windows terminals often use cp1252 which can't render ₹
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

# ── Environment ────────────────────────────────────────────────────────────────
env = os.environ.get('TCB_ENV', 'prod')
load_dotenv('.env' if env == 'prod' else '.env.dev')
_SB_URL = os.environ['SUPABASE_URL']
_SB_KEY = os.environ['SUPABASE_KEY']
sb = create_client(_SB_URL, _SB_KEY)


def _reconnect():
    """Recreate Supabase client after HTTP/2 connection reset."""
    global sb
    sb = create_client(_SB_URL, _SB_KEY)


def _sb_execute(query, retries: int = 2):
    """Call query() and return result; reconnect and retry on WinError 10054."""
    for attempt in range(retries + 1):
        try:
            return query()
        except Exception as e:
            if attempt < retries and 'WinError 10054' in str(e):
                _reconnect()
            else:
                raise

COVERAGE_DAYS     = 30
TRANSIT_BUFFER    = 7
MIN_AVAILABLE_DAYS = 5   # min Q=Y days to compute reliable raw ADS for a DS
MIN_INVOICE_VALUE = 150_000  # ₹1.5L gate per WH
PERF_LOOKBACK    = 60        # days of performance data to load
OUTPUT_DIR       = Path('data/blinkit/auto/replenishment')
BLINKIT_CHANNEL_ID   = 4
BLINKIT_CHANNEL_CODE = 'BLK'

# Performance file "Serving warehouse" label → partner_locations code.
# Covers all 20 active WHs (some have suffix variations in the CSV).
_PERF_WH_TO_CODE: dict[str, str] = {
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

_PERF_DETAIL_DIRS = [
    Path('data/blinkit/manual/product_performance/detail'),
    Path('data/blinkit/auto/product_performance/detail'),
]

_PERF_REQUIRED_COLS = frozenset({
    'Item ID', 'Darkstore name', 'Considered for assessment (Y/N)',
    'Serving warehouse', 'Date', 'Total orders',
})


# ── Data loading ───────────────────────────────────────────────────────────────

def load_item_to_sku_lookup() -> dict[str, str]:
    """Item ID (Blinkit platform_pid_additional) → sku_id."""
    rows = _sb_execute(lambda: sb.table('sku_channel_ids')
                       .select('sku_id, platform_pid_additional')
                       .eq('channel_code', BLINKIT_CHANNEL_CODE)
                       .execute().data)
    return {str(r['platform_pid_additional']): r['sku_id']
            for r in rows if r.get('platform_pid_additional')}


def load_perf_wh_sku_universe(wh_df: pd.DataFrame,
                               item_to_sku: dict[str, str]) -> set[tuple]:
    """
    Scan performance CSVs for distinct (sku_id, wh_location_id) pairs.
    Reads the 'Item ID' and 'Serving warehouse' columns only — does NOT require
    DS to be seeded in partner_locations, so all WHs in the file appear.
    """
    code_to_id = wh_df.set_index('code')['location_id'].to_dict()
    universe: set[tuple] = set()

    for d in _PERF_DETAIL_DIRS:
        if not d.exists():
            continue
        for fpath in sorted(d.glob('*.csv')):
            try:
                hdr = pd.read_csv(fpath, nrows=0)
                hdr.columns = [c.strip() for c in hdr.columns]
                if not _PERF_REQUIRED_COLS.issubset(set(hdr.columns)):
                    continue
                df = pd.read_csv(fpath, usecols=['Item ID', 'Serving warehouse'],
                                 low_memory=False)
                df.columns = [c.strip() for c in df.columns]
                df = df.dropna()
                for item_id, wh_name in zip(df['Item ID'], df['Serving warehouse']):
                    sku_id = item_to_sku.get(str(item_id).strip())
                    code   = _PERF_WH_TO_CODE.get(str(wh_name).strip())
                    if sku_id and code:
                        wh_id = code_to_id.get(code)
                        if wh_id:
                            universe.add((sku_id, int(wh_id)))
            except Exception:
                continue

    return universe


def _paginate(table: str, select: str, **eq_filters) -> list[dict]:
    page_size = 1000
    offset    = 0
    rows: list[dict] = []
    while True:
        def _fetch():
            q = sb.table(table).select(select)
            for k, v in eq_filters.items():
                q = q.eq(k, v)
            return q.range(offset, offset + page_size - 1).execute().data
        batch = _sb_execute(_fetch)
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def load_wh_locations() -> pd.DataFrame:
    rows = _sb_execute(lambda: sb.table('partner_locations')
                       .select('location_id, code, name')
                       .eq('location_type', 'WH')
                       .eq('channel_id', BLINKIT_CHANNEL_ID)
                       .eq('is_active', True)
                       .execute().data)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=['location_id', 'code', 'name'])


def load_ds_locations() -> pd.DataFrame:
    rows = _sb_execute(lambda: sb.table('partner_locations')
                       .select('location_id, name, code, parent_location_id, city')
                       .eq('location_type', 'DARKSTORE')
                       .eq('channel_id', BLINKIT_CHANNEL_ID)
                       .eq('is_active', True)
                       .execute().data)
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=['location_id', 'name', 'code', 'parent_location_id', 'city'])


def _load_elig_for_plan(ds_to_wh: dict) -> tuple[set, dict]:
    """
    Load eligibility data for the replenishment plan.
    Returns:
      excluded: set of (location_id, sku_id) pairs that are not 'active' (all non-active statuses
                including ds_choked are excluded from ADS computation)
      choked:   dict of (wh_id, sku_id) -> count of ds_choked DS (for Overview reporting)
    """
    rows = _paginate('blinkit_ds_sku_eligibility', 'location_id,sku_id,status')
    excluded = {(r['location_id'], r['sku_id']) for r in rows if r.get('status') != 'active'}
    choked: dict[tuple, int] = {}
    for r in rows:
        if r.get('status') == 'ds_choked':
            wh_id = ds_to_wh.get(r['location_id'])
            if wh_id:
                key = (int(wh_id), r['sku_id'])
                choked[key] = choked.get(key, 0) + 1
    return excluded, choked


def load_perf_ds_active_y(wh_df: pd.DataFrame,
                           item_to_sku: dict[str, str]) -> dict[tuple, int]:
    """
    Scan the latest performance CSV (highest mtime) for Col R = Y rows.
    Returns count of active DS per (wh_location_id, sku_id) from that file.
    This is the independent CSV-based signal for the non-tautological check.
    """
    code_to_id = wh_df.set_index('code')['location_id'].to_dict()

    all_files: list[Path] = []
    for d in _PERF_DETAIL_DIRS:
        if d.exists():
            all_files.extend(d.glob('*.csv'))

    valid: list[Path] = []
    for fpath in all_files:
        try:
            hdr = pd.read_csv(fpath, nrows=0)
            hdr.columns = [c.strip() for c in hdr.columns]
            if _PERF_REQUIRED_COLS.issubset(set(hdr.columns)):
                valid.append(fpath)
        except Exception:
            continue

    if not valid:
        return {}

    latest_file = max(valid, key=lambda f: f.stat().st_mtime)

    try:
        df = pd.read_csv(
            latest_file,
            usecols=['Item ID', 'Darkstore name',
                     'Considered for assessment (Y/N)',
                     'Serving warehouse', 'Date'],
            low_memory=False,
        )
        df.columns = [c.strip() for c in df.columns]
    except Exception:
        return {}

    df['Date'] = pd.to_datetime(
        df['Date'].str.replace(r'\s+\+\d{4}\s+UTC', '', regex=True),
        utc=True, errors='coerce',
    ).dt.date
    df = df.dropna(subset=['Item ID', 'Darkstore name', 'Date'])

    # Latest row per (Item ID, Darkstore name)
    latest_per_pair = (
        df.sort_values('Date', ascending=False)
        .drop_duplicates(subset=['Item ID', 'Darkstore name'])
    )

    result: dict[tuple, int] = {}
    for _, row in latest_per_pair.iterrows():
        if str(row['Considered for assessment (Y/N)']).strip() != 'Y':
            continue
        sku_id  = item_to_sku.get(str(row['Item ID']).strip())
        wh_code = _PERF_WH_TO_CODE.get(str(row['Serving warehouse']).strip())
        if not sku_id or not wh_code:
            continue
        wh_id = code_to_id.get(wh_code)
        if not wh_id:
            continue
        key = (int(wh_id), sku_id)
        result[key] = result.get(key, 0) + 1

    return result


def load_performance_data(days_back: int = PERF_LOOKBACK) -> pd.DataFrame:
    """Load day-level rows from blinkit_performance_detail (rolling window source)."""
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()
    cols   = 'data_date,location_id,sku_id,city,inventory_available,total_orders,download_date'
    rows   = _paginate('blinkit_performance_detail', cols)
    rows   = [r for r in rows if r.get('data_date', '') >= cutoff]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df['data_date']          = pd.to_datetime(df['data_date']).dt.date
    df['total_orders']       = pd.to_numeric(df['total_orders'], errors='coerce').fillna(0).astype(int)
    df['inventory_available'] = df['inventory_available'].fillna(True).astype(bool)
    df['download_date']      = pd.to_datetime(df['download_date']).dt.date
    return df


def load_inventory_snapshot(snapshot_date: str | None = None) -> pd.DataFrame:
    cols = 'snapshot_date,location_id,sku_id,units_wh,units_incoming,units_transit,units_ds'
    if snapshot_date:
        rows = _sb_execute(lambda: sb.table('blinkit_inventory_snapshots')
                           .select(cols).eq('snapshot_date', snapshot_date).execute().data)
    else:
        latest = _sb_execute(lambda: sb.table('blinkit_inventory_snapshots')
                             .select('snapshot_date')
                             .order('snapshot_date', desc=True)
                             .limit(1).execute().data)
        if not latest:
            return pd.DataFrame()
        snap_date = latest[0]['snapshot_date']
        rows = _sb_execute(lambda: sb.table('blinkit_inventory_snapshots')
                           .select(cols).eq('snapshot_date', snap_date).execute().data)

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ('units_wh', 'units_incoming', 'units_transit', 'units_ds'):
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    # Full pipeline: WH stock + dispatched (incoming) + WH->DS transit + at DS shelf
    df['effective_stock'] = df['units_wh'] + df['units_incoming'] + df['units_transit'] + df['units_ds']
    return df


def load_sku_names() -> dict:
    rows = _sb_execute(lambda: sb.table('skus').select('sku_id, name').execute().data)
    return {r['sku_id']: r['name'] for r in rows}


def load_all_eligibility() -> pd.DataFrame:
    """Load all eligibility rows (all statuses) for DS count breakdown in overview tab."""
    rows = _paginate('blinkit_ds_sku_eligibility', 'location_id,sku_id,status')
    if not rows:
        return pd.DataFrame(columns=['location_id', 'sku_id', 'status'])
    return pd.DataFrame(rows)


def load_sp_lookup() -> dict:
    """
    sku_id → median selling_price from recent Blinkit orders.
    Falls back to ₹0 if no orders (engine still outputs units_to_ship).
    """
    rows = _paginate('orders', 'sku_id,selling_price', channel_id=BLINKIT_CHANNEL_ID)
    by_sku: dict[str, list[float]] = {}
    for r in rows:
        sp = r.get('selling_price')
        if sp and float(sp) > 0:
            by_sku.setdefault(r['sku_id'], []).append(float(sp))
    # Median
    return {
        sku_id: sorted(prices)[len(prices) // 2]
        for sku_id, prices in by_sku.items()
    }


# ── ADS computation ────────────────────────────────────────────────────────────

def compute_ads(perf_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute ADS per (sku_id, location_id) using a rolling 30-day window.

    raw_ADS     = SUM(total_orders WHERE inventory_available) / COUNT(inventory_available days)
    imputed_ADS = (orders on available days + city_P75_ADS × oos_days) / 30

    ads column = imputed_ADS (used for target stock in replenishment plan).

    Returns DataFrame with columns:
        sku_id, location_id, ads, had_oos_days, period_days,
        non_oos_days, raw_ads, imputed_ads, city, assessment_start, assessment_end
    """
    if perf_df.empty:
        return pd.DataFrame()

    # Rolling 30-day window per SKU
    max_date_per_sku = perf_df.groupby('sku_id')['data_date'].max().to_dict()
    perf_df = perf_df.copy()
    perf_df['_cutoff'] = perf_df['sku_id'].map(
        lambda s: max_date_per_sku[s] - timedelta(days=29)
    )
    perf = perf_df[perf_df['data_date'] >= perf_df['_cutoff']].copy()

    # DS-level raw ADS
    results = []
    for (sku_id, loc_id), grp in perf.groupby(['sku_id', 'location_id']):
        avail      = grp[grp['inventory_available']]
        avail_days = len(avail)
        oos_days   = len(grp) - avail_days
        raw_ads    = float(avail['total_orders'].sum()) / avail_days if avail_days > 0 else 0.0
        city_vals  = grp['city'].dropna()
        city       = str(city_vals.iloc[0]).strip() if len(city_vals) > 0 else None
        results.append({
            'sku_id':      sku_id,
            'location_id': loc_id,
            'raw_ads':     round(raw_ads, 4),
            'avail_days':  avail_days,
            'oos_days':    oos_days,
            'total_days':  len(grp),
            'city':        city,
        })

    if not results:
        return pd.DataFrame()

    ads_df = pd.DataFrame(results)

    # City-level P75 ADS (imputation value for Q=0 days)
    # Only include DSes with enough available days for a reliable signal
    reliable = ads_df[ads_df['avail_days'] >= MIN_AVAILABLE_DAYS]
    city_p75: dict[tuple, float] = {}
    if not reliable.empty:
        for (s_id, city), grp in reliable[reliable['city'].notna()].groupby(['sku_id', 'city']):
            city_p75[(s_id, city)] = float(np.percentile(grp['raw_ads'].values, 75))

    sku_p75_fallback: dict[str, float] = {}
    if not reliable.empty:
        for s_id, grp in reliable.groupby('sku_id'):
            sku_p75_fallback[s_id] = float(np.percentile(grp['raw_ads'].values, 75))

    def _imputed_ads(row) -> float:
        ds_city = row['city']
        p75 = city_p75.get((row['sku_id'], ds_city), 0.0) if ds_city else 0.0
        if p75 == 0.0:
            p75 = sku_p75_fallback.get(row['sku_id'], 0.0)
        return round((row['raw_ads'] * row['avail_days'] + p75 * row['oos_days']) / 30, 4)

    ads_df['imputed_ads'] = ads_df.apply(_imputed_ads, axis=1)
    ads_df['ads']         = ads_df['imputed_ads']
    ads_df['had_oos_days'] = ads_df['oos_days'] > 0
    ads_df['period_days']  = ads_df['total_days']
    ads_df['non_oos_days'] = ads_df['avail_days']

    max_dt_map = perf.groupby('sku_id')['data_date'].max().to_dict()
    ads_df['assessment_start'] = ads_df['sku_id'].apply(
        lambda s: str(max_dt_map.get(s, date.today()) - timedelta(days=29))
    )
    ads_df['assessment_end'] = ads_df['sku_id'].apply(
        lambda s: str(max_dt_map.get(s, date.today()))
    )

    return ads_df


# ── Replenishment plan computation ─────────────────────────────────────────────

def compute_replenishment_plan(
    snapshot_date: str | None = None,
    coverage_days: int = COVERAGE_DAYS,
    transit_buffer_days: int = TRANSIT_BUFFER,
) -> pd.DataFrame:
    """
    Returns a DataFrame with one row per WH × SKU that needs replenishment.
    Rows with units_to_ship == 0 are included (for visibility) but should not be shipped.
    """
    print('Loading master data...')
    wh_df     = load_wh_locations()
    ds_df     = load_ds_locations()
    sku_names = load_sku_names()
    sp_lookup = load_sp_lookup()

    # ds_to_wh needed before eligibility load (for choked count bucketing)
    ds_to_wh_pre = ds_df.set_index('location_id')['parent_location_id'].to_dict()
    excluded, choked_per_wh_sku = _load_elig_for_plan(ds_to_wh_pre)

    print(f'  WHs: {len(wh_df)} | DS: {len(ds_df)} | Excluded DS-SKUs: {len(excluded)} '
          f'| Choked WH-SKU buckets: {len(choked_per_wh_sku)}')

    print('Loading performance data...')
    perf_df = load_performance_data(days_back=PERF_LOOKBACK)
    print(f'  Performance rows: {len(perf_df):,}')

    print('Loading inventory snapshot...')
    inv_df = load_inventory_snapshot(snapshot_date)
    if inv_df.empty:
        print('  [WARN] No inventory snapshot found — effective_stock will be 0 for all rows')
    else:
        snap_date = inv_df['snapshot_date'].iloc[0]
        print(f'  Snapshot date: {snap_date} | Rows: {len(inv_df)}')

    # Compute ADS per DS-SKU
    ads_df = compute_ads(perf_df)
    print(f'  ADS rows computed: {len(ads_df)}')

    # DS → WH mapping
    ds_to_wh  = ds_df.set_index('location_id')['parent_location_id'].to_dict()
    active_ds = set(ds_df['location_id'])

    # Build working set from ADS data — DS-SKUs with performance data are eligible by default.
    # Explicitly excluded pairs (non-active eligibility status) are removed.
    if ads_df.empty:
        print('[WARN] No ADS data found — load performance CSVs first.')
        return pd.DataFrame()

    elig_with_ads = ads_df.copy()
    # Keep only DS rows that are active in partner_locations
    elig_with_ads = elig_with_ads[elig_with_ads['location_id'].isin(active_ds)]
    # Remove explicitly excluded DS-SKU pairs
    if excluded:
        mask = elig_with_ads.apply(
            lambda r: (r['location_id'], r['sku_id']) not in excluded, axis=1
        )
        elig_with_ads = elig_with_ads[mask]
        print(f'  Excluded DS-SKUs filtered out: {(~mask).sum()}')

    elig_with_ads['wh_location_id'] = elig_with_ads['location_id'].map(ds_to_wh)
    elig_with_ads = elig_with_ads.dropna(subset=['wh_location_id'])
    elig_with_ads['wh_location_id'] = elig_with_ads['wh_location_id'].astype(int)

    # Aggregate per WH × SKU
    plan_rows = []
    for (wh_id, sku_id), grp in elig_with_ads.groupby(['wh_location_id', 'sku_id']):
        wh_info  = wh_df[wh_df['location_id'] == wh_id]
        if wh_info.empty:
            continue
        wh_row = wh_info.iloc[0]

        active_ds_count = len(grp)
        ds_with_data    = int(grp['period_days'].notna().sum())
        ds_with_oos     = int(grp['had_oos_days'].sum())
        total_ads       = float(grp['ads'].sum())
        avg_ads_per_ds  = total_ads / active_ds_count if active_ds_count > 0 else 0

        total_demand    = total_ads * coverage_days
        transit_stock   = total_ads * transit_buffer_days
        target_stock    = total_demand + transit_stock

        # Floor: newly launched or long-OOS SKUs may have near-zero ADS → target=0.
        # Guarantee at least 1 unit per active DS so we don't starve live stores.
        ads_floor_applied = target_stock < active_ds_count
        target_stock      = max(target_stock, active_ds_count)

        # Effective stock from latest inventory snapshot
        inv_row = inv_df[
            (inv_df['location_id'] == wh_id) & (inv_df['sku_id'] == sku_id)
        ] if not inv_df.empty else pd.DataFrame()

        if inv_row.empty:
            eff_stock     = 0
            units_wh      = 0
            units_inc     = 0
            units_transit = 0
            units_ds      = 0
        else:
            r = inv_row.iloc[0]
            units_wh      = int(r['units_wh'])
            units_inc     = int(r['units_incoming'])
            units_transit = int(r.get('units_transit', 0))
            units_ds      = int(r.get('units_ds', 0))
            eff_stock     = int(r['effective_stock'])

        units_to_ship = max(0, round(target_stock - eff_stock))

        sp            = sp_lookup.get(sku_id)
        invoice_value = round(units_to_ship * sp) if sp else None

        # Assessment period (use first DS with data, or None)
        first_data = grp[grp['period_days'].notna()]
        a_start = first_data['assessment_start'].iloc[0] if not first_data.empty else None
        a_end   = first_data['assessment_end'].iloc[0]   if not first_data.empty else None

        notes = []
        if ads_floor_applied:
            notes.append(f'ADS floor applied — target raised to {active_ds_count} (1 per active DS)')
        if ds_with_data < active_ds_count:
            notes.append(f'{active_ds_count - ds_with_data} DS missing performance data')
        if ds_with_oos > 0:
            notes.append(f'{ds_with_oos} DS had stock-out days (inventory_available=False)')

        plan_rows.append({
            'wh_name':           wh_row['name'],
            'wh_code':           wh_row['code'],
            'wh_location_id':    int(wh_id),
            'sku_id':            sku_id,
            'sku_name':          sku_names.get(sku_id, sku_id),
            'active_ds_count':   active_ds_count,
            'ds_choked_count':   choked_per_wh_sku.get((int(wh_id), sku_id), 0),
            'ds_with_data':      ds_with_data,
            'ds_with_oos':       ds_with_oos,
            'avg_ads_per_ds':    round(avg_ads_per_ds, 4),
            'total_ads':         round(total_ads, 2),
            'total_demand_30d':  round(total_demand),
            'transit_buffer_7d': round(transit_stock),
            'target_stock':      round(target_stock),
            'units_wh':          units_wh,
            'units_incoming':    units_inc,
            'units_transit':     units_transit,
            'units_ds':          units_ds,
            'effective_stock':   eff_stock,
            'units_to_ship':     int(units_to_ship),
            'selling_price':     sp,
            'invoice_value':     invoice_value,
            'priority':          ds_with_oos > 0,
            'assessment_start':  a_start,
            'assessment_end':    a_end,
            'notes':             '; '.join(notes) if notes else '',
        })

    plan_df = pd.DataFrame(plan_rows)
    if plan_df.empty:
        return plan_df

    plan_df = plan_df.sort_values(
        ['priority', 'wh_name', 'sku_id'],
        ascending=[False, True, True]
    )
    return plan_df


# ── Overview computation ───────────────────────────────────────────────────────

_STATUS_COLS = {
    'darkstore_closed':        'ds_closed',
    'launch_awaited':          'ds_not_launched',
    'sku_city_exited':         'ds_exited',
    'sku_recalled':            'ds_recalled',
    'sku_moved_out_low_sales': 'ds_low_sales',
    'ds_choked':               'ds_choked',
}


def compute_overview(
    plan_df: pd.DataFrame,
    ds_df: pd.DataFrame,
    eligibility_df: pd.DataFrame,
    wh_df: pd.DataFrame,
    sku_names: dict,
    perf_universe: set[tuple] | None = None,
    active_y_counts: dict | None = None,
) -> pd.DataFrame:
    """
    Build the overview table: one row per WH x SKU.
    Universe = ALL (sku_id, wh_id) pairs from perf_universe (read directly from
    performance CSVs — covers all WHs even if their DS aren't seeded).
    Falls back to eligibility_df + plan_df if perf_universe not supplied.
    """
    ds_to_wh    = ds_df.set_index('location_id')['parent_location_id'].to_dict()
    wh_name_map = wh_df.set_index('location_id')['name'].to_dict()

    # --- Count excluded DS per (wh_id, sku_id) × status bucket ---
    elig_by_wh_sku: dict[tuple, dict] = {}
    active_elig: dict[tuple, int] = {}
    if not eligibility_df.empty:
        for _, er in eligibility_df.iterrows():
            wh_id = ds_to_wh.get(er['location_id'])
            if wh_id is None or int(wh_id) not in wh_name_map:
                continue
            key = (int(wh_id), er['sku_id'])
            col = _STATUS_COLS.get(er['status'])
            if col is None:
                active_elig[key] = active_elig.get(key, 0) + 1
            else:
                entry = elig_by_wh_sku.setdefault(key, {c: 0 for c in _STATUS_COLS.values()})
                entry[col] += 1

    # --- Build full universe ---
    # Primary source: performance CSVs (all WHs, even unseeded DS)
    # Supplement with eligibility + plan to catch anything the CSV scan missed
    universe: set[tuple] = set()
    if perf_universe:
        universe.update(perf_universe)
    for key in elig_by_wh_sku:
        universe.add((key[1], key[0]))
    for key in active_elig:
        universe.add((key[1], key[0]))
    for _, r in plan_df.iterrows():
        universe.add((r['sku_id'], int(r['wh_location_id'])))

    # --- Plan lookup for inventory + ADS numbers ---
    plan_lookup: dict[tuple, pd.Series] = {}
    for _, r in plan_df.iterrows():
        plan_lookup[(r['sku_id'], int(r['wh_location_id']))] = r

    rows = []
    for (sku_id, wh_id) in sorted(universe, key=lambda x: (x[0], wh_name_map.get(x[1], ''))):
        if wh_id not in wh_name_map:
            continue
        wh_name = wh_name_map[wh_id]
        key     = (wh_id, sku_id)
        counts  = elig_by_wh_sku.get(key, {})

        ds_closed       = counts.get('ds_closed', 0)
        ds_not_launched = counts.get('ds_not_launched', 0)
        ds_exited       = counts.get('ds_exited', 0)
        ds_recalled     = counts.get('ds_recalled', 0)
        ds_low_sales    = counts.get('ds_low_sales', 0)
        ds_choked       = counts.get('ds_choked', 0)
        ds_active_db    = active_elig.get(key, 0)   # DB status='active' count

        # ds_active_y_flag: CSV-based Y-count (independent signal for non-tautological check).
        # Falls back to DB active count if CSV scan not available.
        ds_active_y_flag = (active_y_counts or {}).get(key, ds_active_db)

        total_ds        = (ds_active_db + ds_choked + ds_closed +
                           ds_not_launched + ds_exited + ds_recalled + ds_low_sales)
        # ds_active_check is derived independently from total_ds — should equal ds_active_y_flag.
        # Discrepancy signals vanished-Y DS (Trigger 1) or unclassified N-rows.
        ds_active_check = (total_ds - ds_closed - ds_not_launched -
                           ds_choked - ds_exited - ds_recalled - ds_low_sales)

        plan_r = plan_lookup.get((sku_id, wh_id))
        if plan_r is not None:
            avg_ads_per_ds   = round(float(plan_r.get('avg_ads_per_ds', 0)), 3)
            total_ads        = round(float(plan_r.get('total_ads', 0)), 3)
            total_demand_30d = int(plan_r.get('total_demand_30d', 0))
            transit_buf_7d   = int(plan_r.get('transit_buffer_7d', 0))
            wh_soh           = int(plan_r.get('units_wh', 0))
            incoming         = int(plan_r.get('units_incoming', 0))
            in_transit       = int(plan_r.get('units_transit', 0))
            ds_inv           = int(plan_r.get('units_ds', 0))
            target_stock     = int(plan_r['target_stock'])
            to_ship          = int(plan_r['units_to_ship'])
        else:
            avg_ads_per_ds = total_ads = 0.0
            total_demand_30d = transit_buf_7d = 0
            wh_soh = incoming = in_transit = ds_inv = target_stock = to_ship = 0

        rows.append({
            'sku_id':            sku_id,
            'sku_name':          sku_names.get(sku_id, sku_id),
            'wh':                wh_name,
            'ds_active_y_flag':  ds_active_y_flag,
            'total_ds':          total_ds,
            'ds_closed':         ds_closed,
            'ds_not_launched':   ds_not_launched,
            'ds_choked':         ds_choked,
            'ds_exited':         ds_exited,
            'ds_recalled':       ds_recalled,
            'ds_low_sales':      ds_low_sales,
            'ds_active_check':   ds_active_check,
            'avg_ads_per_ds':    avg_ads_per_ds,
            'total_ads':         total_ads,
            'total_demand_30d':  total_demand_30d,
            'transit_buffer_7d': transit_buf_7d,
            'wh_soh':            wh_soh,
            'incoming':          incoming,
            'in_transit':        in_transit,
            'ds_inventory':      ds_inv,
            'total_inventory':   wh_soh + incoming + in_transit + ds_inv,
            'target_stock':      target_stock,
            'to_ship':           to_ship,
        })

    return pd.DataFrame(rows)


# ── Geo Summary ────────────────────────────────────────────────────────────────

def compute_geo_summary(wh_df: pd.DataFrame, eligibility_df: pd.DataFrame) -> pd.DataFrame:
    """
    One row per WH. Columns:
        wh_name, total_ds, ds_closed,
        cities_served, cities_live_1plus (≥1 SKU active), cities_live_6plus (≥6 SKUs active)
    Loads ALL DS (active + inactive) so closed/not-launched stores are counted.
    """
    # Load all DS regardless of is_active
    all_ds_rows = _paginate(
        'partner_locations',
        'location_id,name,city,parent_location_id',
        location_type='DARKSTORE',
        channel_id=BLINKIT_CHANNEL_ID,
    )
    if not all_ds_rows:
        return pd.DataFrame()
    all_ds = pd.DataFrame(all_ds_rows)
    all_ds['parent_location_id'] = all_ds['parent_location_id'].astype('Int64')
    # Use city stored in DB (populated from performance CSV "Delivery City" column).
    # Fall back to first word of DS name for any rows where city is still NULL.
    all_ds['city'] = all_ds.apply(
        lambda r: r['city'] if r['city'] else r['name'].strip().split()[0],
        axis=1,
    )

    # DS sets from eligibility
    closed_ds  = set(eligibility_df.loc[eligibility_df['status'] == 'darkstore_closed', 'location_id'])
    active_elig = eligibility_df[eligibility_df['status'] == 'active']
    active_skus_per_ds = active_elig.groupby('location_id')['sku_id'].nunique().to_dict()

    rows = []
    for _, wh in wh_df.iterrows():
        wh_id  = int(wh['location_id'])
        wh_ds  = all_ds[all_ds['parent_location_id'] == wh_id]

        total_ds   = len(wh_ds)
        ds_closed  = int(wh_ds['location_id'].isin(closed_ds).sum())

        # Non-closed DS count per city (for the "(N)" annotation)
        non_closed_ds = wh_ds[~wh_ds['location_id'].isin(closed_ds)]
        city_open_count = non_closed_ds.groupby('city')['location_id'].nunique().to_dict()

        def _city_label(city: str) -> str:
            n = city_open_count.get(city, 0)
            return f"{city} ({n})" if n else f"{city} (closed)"

        # Cities from all DS under this WH (with non-closed DS count)
        all_cities  = [_city_label(c) for c in sorted(wh_ds['city'].unique())]

        # DS with ≥1 active SKU → live cities
        live_mask   = wh_ds['location_id'].map(lambda x: active_skus_per_ds.get(x, 0) >= 1)
        live_cities = [_city_label(c) for c in sorted(wh_ds.loc[live_mask, 'city'].unique())]

        # DS with ≥6 active SKUs → major-presence cities
        big_mask    = wh_ds['location_id'].map(lambda x: active_skus_per_ds.get(x, 0) >= 6)
        big_cities  = [_city_label(c) for c in sorted(wh_ds.loc[big_mask, 'city'].unique())]

        rows.append({
            'wh_name':           wh['name'],
            'total_ds':          total_ds,
            'ds_closed':         ds_closed,
            'cities_served':     ', '.join(all_cities),
            'cities_live_1plus': ', '.join(live_cities),
            'cities_live_6plus': ', '.join(big_cities),
        })

    return pd.DataFrame(rows)


# ── Output ─────────────────────────────────────────────────────────────────────

def write_excel(plan_df: pd.DataFrame, overview_df: pd.DataFrame,
                geo_df: pd.DataFrame,
                output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    fname  = f'replenishment_plan_{date.today().strftime("%Y%m%d")}.xlsx'
    fpath  = output_dir / fname

    # Per-WH gate: sum invoice_value for to-ship rows grouped by WH
    ship_only = plan_df[plan_df['units_to_ship'] > 0].copy()
    wh_invoice = (
        ship_only.groupby('wh_name')['invoice_value']
        .sum()
        .rename('wh_invoice_total')
    )
    plan_df = plan_df.join(wh_invoice, on='wh_name')
    plan_df['wh_gate'] = plan_df['wh_invoice_total'].apply(
        lambda v: ('SHIP ✓' if v >= MIN_INVOICE_VALUE else f'DEFER — below ₹{MIN_INVOICE_VALUE/1000:.0f}K')
        if pd.notna(v) else ''
    )

    total_invoice = plan_df['invoice_value'].sum(min_count=1)

    # Per-WH summary rows + TOTAL
    summary_rows = []
    for wh_name, grp in plan_df.groupby('wh_name'):
        wh_inv = grp['invoice_value'].sum(min_count=1)
        wh_gate_val = grp['wh_invoice_total'].iloc[0] if pd.notna(grp['wh_invoice_total'].iloc[0]) else None
        summary_rows.append({
            'wh_name':         wh_name,
            'units_to_ship':   grp['units_to_ship'].sum(),
            'invoice_value':   wh_inv,
            'wh_gate':         ('SHIP ✓' if wh_gate_val and wh_gate_val >= MIN_INVOICE_VALUE
                                else f'DEFER — below ₹{MIN_INVOICE_VALUE/1000:.0f}K')
                               if wh_gate_val is not None else '',
        })
    summary_rows.append({
        'wh_name':       'TOTAL',
        'units_to_ship': plan_df['units_to_ship'].sum(),
        'invoice_value': total_invoice,
        'wh_gate':       '',
    })

    with pd.ExcelWriter(fpath, engine='openpyxl') as writer:
        # Overview-SKU: one table per SKU, rows = WHs
        if not overview_df.empty:
            current_row = 0
            for _, group in overview_df.groupby('sku_id', sort=True):
                group.to_excel(writer, sheet_name='Overview-SKU',
                               startrow=current_row, index=False, header=True)
                current_row += 1 + len(group) + 1

        # Overview-WH: one table per WH, rows = SKUs
        if not overview_df.empty:
            ov_wh = overview_df[['wh', 'sku_id', 'sku_name',
                                  'ds_active_y_flag', 'total_ds', 'ds_closed',
                                  'ds_not_launched', 'ds_choked', 'ds_exited',
                                  'ds_recalled', 'ds_low_sales', 'ds_active_check',
                                  'avg_ads_per_ds', 'total_ads',
                                  'total_demand_30d', 'transit_buffer_7d',
                                  'wh_soh', 'incoming', 'in_transit',
                                  'ds_inventory', 'total_inventory',
                                  'target_stock', 'to_ship']].copy()
            current_row = 0
            for _, group in ov_wh.groupby('wh', sort=True):
                group.to_excel(writer, sheet_name='Overview-WH',
                               startrow=current_row, index=False, header=True)
                current_row += 1 + len(group) + 1

        # Plan sheets
        ship_df = plan_df[plan_df['units_to_ship'] > 0].copy()
        all_df  = plan_df.copy()

        ship_df.to_excel(writer, sheet_name='Ship Now', index=False)
        all_df.to_excel(writer,  sheet_name='Full Plan', index=False)

        # Gate summary on a final sheet — per WH + TOTAL
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name='Summary', index=False)

        # Geo summary sheet
        if not geo_df.empty:
            geo_df.to_excel(writer, sheet_name='Geo', index=False)

    return fpath


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Blinkit replenishment engine')
    parser.add_argument('--snapshot', help='SOH snapshot date to use (YYYY-MM-DD)')
    parser.add_argument('--coverage', type=int, default=COVERAGE_DAYS,
                        help=f'Coverage days (default {COVERAGE_DAYS})')
    parser.add_argument('--buffer',   type=int, default=TRANSIT_BUFFER,
                        help=f'Transit buffer days (default {TRANSIT_BUFFER})')
    parser.add_argument('--dry-run',  action='store_true', help='Print plan, skip Excel write')
    args = parser.parse_args()

    print(f'Environment: {env}')
    print(f'Coverage: {args.coverage}d | Buffer: {args.buffer}d | Gate: ₹{MIN_INVOICE_VALUE:,}')
    print()

    plan_df = compute_replenishment_plan(
        snapshot_date=args.snapshot,
        coverage_days=args.coverage,
        transit_buffer_days=args.buffer,
    )

    if plan_df.empty:
        print('\nNo replenishment plan generated — check eligibility and performance data.')
        sys.exit(0)

    print('\nBuilding overview...')
    wh_df          = load_wh_locations()
    ds_df          = load_ds_locations()
    eligibility_df = load_all_eligibility()
    sku_names      = load_sku_names()
    item_to_sku    = load_item_to_sku_lookup()
    perf_universe  = load_perf_wh_sku_universe(wh_df, item_to_sku)
    active_y_counts = load_perf_ds_active_y(wh_df, item_to_sku)
    print(f'  Perf universe: {len(perf_universe)} WH-SKU pairs from CSVs')
    print(f'  Active-Y DS counts from latest CSV: {sum(active_y_counts.values())} DS across {len(active_y_counts)} WH-SKU pairs')
    overview_df    = compute_overview(plan_df, ds_df, eligibility_df, wh_df, sku_names,
                                      perf_universe, active_y_counts)
    print(f'  Overview rows: {len(overview_df)}')
    geo_df         = compute_geo_summary(wh_df, eligibility_df)
    print(f'  Geo rows: {len(geo_df)}')

    ship_df = plan_df[plan_df['units_to_ship'] > 0]
    total_invoice = plan_df['invoice_value'].sum(min_count=1)

    # Per-WH gate for dry-run summary
    wh_invoice = ship_df.groupby('wh_name')['invoice_value'].sum()

    print(f'\n── Plan Summary ─────────────────────────────────────────')
    print(f'  WH-SKU rows:      {len(plan_df)}')
    print(f'  Rows to ship:     {len(ship_df)}')
    print(f'  Total units:      {ship_df["units_to_ship"].sum():,}')
    if pd.notna(total_invoice):
        print(f'  Invoice value:    Rs.{total_invoice:,.0f}')
    else:
        print('  Invoice value:    N/A (no SP data for some SKUs)')

    print(f'\n── WH Gate (₹{MIN_INVOICE_VALUE/1000:.0f}K per WH) ────────────────────────')
    for wh, inv in wh_invoice.items():
        gate = 'PASS' if inv >= MIN_INVOICE_VALUE else 'DEFER'
        print(f'  {wh:<30} Rs.{inv:>8,.0f}  {gate}')

    if not ship_df.empty:
        print(f'\n── Ship Now ─────────────────────────────────────────────')
        cols = ['wh_name', 'sku_id', 'sku_name', 'active_ds_count',
                'avg_ads_per_ds', 'effective_stock', 'units_to_ship',
                'invoice_value', 'priority', 'notes']
        print(ship_df[cols].to_string(index=False))

    if not overview_df.empty:
        print(f'\n── Overview ─────────────────────────────────────────────')
        ov_cols = ['sku_id', 'wh', 'ds_active_y_flag', 'total_ds',
                   'ds_closed', 'ds_not_launched', 'ds_choked', 'ds_exited',
                   'ds_recalled', 'ds_low_sales', 'ds_active_check',
                   'avg_ads_per_ds', 'total_ads', 'total_demand_30d', 'transit_buffer_7d',
                   'wh_soh', 'incoming', 'in_transit', 'ds_inventory',
                   'total_inventory', 'target_stock', 'to_ship']
        print(overview_df[ov_cols].to_string(index=False))

    if args.dry_run:
        print('\nDRY RUN — no Excel written.')
        return

    fpath = write_excel(plan_df, overview_df, geo_df)
    print(f'\nPlan written: {fpath}')

    parquet_path = OUTPUT_DIR / 'replenishment_plan_latest.parquet'
    plan_df.to_parquet(parquet_path, index=False)
    print(f'Parquet cache written: {parquet_path}')

    _write_plan_to_db(plan_df, date.today())


def _write_plan_to_db(plan_df: pd.DataFrame, plan_date: date) -> None:
    """Upsert the replenishment plan to blinkit_replen_plan for dashboard access."""
    rows = []
    for _, r in plan_df.iterrows():
        a_start = r.get('assessment_start')
        a_end   = r.get('assessment_end')
        sp      = r.get('selling_price')
        iv      = r.get('invoice_value')
        rows.append({
            'plan_date':         plan_date.isoformat(),
            'wh_code':           r['wh_code'],
            'wh_name':           r['wh_name'],
            'wh_location_id':    int(r['wh_location_id']),
            'sku_id':            r['sku_id'],
            'sku_name':          r.get('sku_name', ''),
            'active_ds_count':   int(r['active_ds_count']),
            'ds_choked_count':   int(r.get('ds_choked_count', 0)),
            'ds_with_data':      int(r['ds_with_data']),
            'ds_with_oos':       int(r['ds_with_oos']),
            'avg_ads_per_ds':    float(r['avg_ads_per_ds']),
            'total_ads':         float(r['total_ads']),
            'total_demand_30d':  float(r['total_demand_30d']),
            'transit_buffer_7d': float(r['transit_buffer_7d']),
            'target_stock':      float(r['target_stock']),
            'units_wh':          int(r['units_wh']),
            'units_incoming':    int(r['units_incoming']),
            'units_transit':     int(r['units_transit']),
            'units_ds':          int(r['units_ds']),
            'effective_stock':   int(r['effective_stock']),
            'units_to_ship':     int(r['units_to_ship']),
            'selling_price':     float(sp) if pd.notna(sp) else None,
            'invoice_value':     float(iv) if pd.notna(iv) else None,
            'priority':          bool(r['priority']),
            'assessment_start':  str(a_start) if pd.notna(a_start) else None,
            'assessment_end':    str(a_end)   if pd.notna(a_end)   else None,
            'notes':             str(r.get('notes', '')),
        })

    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        _sb_execute(lambda b=batch: sb.table('blinkit_replen_plan')
                    .upsert(b, on_conflict='plan_date,wh_code,sku_id')
                    .execute())
    print(f'DB write: {len(rows)} rows upserted to blinkit_replen_plan (plan_date={plan_date})')


if __name__ == '__main__':
    main()
