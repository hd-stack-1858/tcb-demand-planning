"""
Blinkit Inventory Snapshot Loader (SOH)
========================================
Loads a Blinkit SOH (Stock on Hand) CSV into blinkit_inventory_snapshots.

SOH is now downloaded automatically by automation/blinkit_soh_scraper.py (daily runner G4).
Auto files land in: data/blinkit/auto/inventory/SOH/
Manual override: drop a file in the same folder and it will be picked up as the latest.

Usage:
    python ingest/blinkit_inventory_loader.py                       # latest file in SOH/
    python ingest/blinkit_inventory_loader.py --file path/to/soh.xlsx

Farukhnagar SR logic:
    SOH rows for "Farukhnagar - SR" are merged into the Faridabad WH row.
    Farukhnagar is closed; its physical stock has been consolidated to Faridabad.

SOH file format (3-row header):
    Row 0: timestamp (merged cell)
    Row 1: column group labels
    Row 2: actual column names  ← parse from here
"""

import os
import sys
import glob
import argparse
from pathlib import Path
from datetime import date
import re

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

# ── Environment ────────────────────────────────────────────────────────────────
env = os.environ.get('TCB_ENV', 'prod')
load_dotenv('.env' if env == 'prod' else '.env.dev')
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

SOH_DIR = Path('data/blinkit/auto/inventory/SOH')

# SOH warehouse name → partner_locations code
# SOH name takes precedence; performance_name alias is for the loader, not stored.
WH_SOH_NAME_TO_CODE = {
    'Bengaluru B3':              'BLK_WH_1873',
    'Bengaluru B5 - Feeder':     'BLK_WH_5397',
    'Hyderabad H3 - Feeder':     'BLK_WH_3201',
    'Kundli Feeder':             'BLK_WH_2010',
    'Kundli - Feeder':           'BLK_WH_2010',
    'Faridabad - Feeder':        'BLK_WH_5096',
    'Mumbai M10 - Feeder':       'BLK_WH_2123',
    'Pune P3 - Feeder Warehouse':'BLK_WH_4572',
    'Chennai C5 - Feeder':       'BLK_WH_3262',
    'Noida N1 - Feeder':         'BLK_WH_2576',
    # Farukhnagar SR: closed — its SOH is merged into Faridabad below
    'Farukhnagar - SR':          'BLK_WH_5096',  # redirect to Faridabad
}

# Columns to extract from SOH (after 3-row header parse)
COL_ITEM_ID    = 'Item ID'
COL_ITEM_NAME  = 'Item Name'
COL_WH_FAC_ID  = 'Warehouse Facility ID'
COL_WH_NAME    = 'Warehouse Facility Name'
COL_INCOMING   = 'Net Incoming Scheduled Inventory'  # "Incoming scheduled inventory"
COL_WH_UNITS   = 'Warehouse'
COL_DS_UNITS   = 'Darkstore'
COL_TRANSIT    = 'In-between'
COL_TOTAL_SELL = 'Total Sellable'
COL_LAST_7D    = 'Last 7 Days'
COL_LAST_15D   = 'Last 15 Days'
COL_LAST_30D   = 'Last 30 Days'


def parse_soh_file(filepath: Path) -> tuple[pd.DataFrame, date]:
    """
    Parse 3-row-header SOH Excel file.
    Returns (DataFrame, snapshot_date).
    """
    raw = pd.read_excel(filepath, header=None)

    # Row 0 has the timestamp in first cell (e.g. "As of 20 May 2026")
    timestamp_cell = str(raw.iloc[0, 0]) if pd.notna(raw.iloc[0, 0]) else ''
    snap_date = date.today()
    m = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})', timestamp_cell)
    if m:
        try:
            snap_date = pd.to_datetime(f"{m.group(1)} {m.group(2)} {m.group(3)}").date()
        except Exception:
            pass

    # Row 2 (index 2) has actual column names
    col_names = raw.iloc[2].tolist()
    df = raw.iloc[3:].copy()
    df.columns = col_names
    df = df.dropna(subset=[COL_ITEM_ID, COL_WH_NAME])
    df = df[df[COL_ITEM_ID].astype(str).str.strip() != '']

    # Numeric columns
    for col in [COL_INCOMING, COL_WH_UNITS, COL_DS_UNITS, COL_TRANSIT,
                COL_TOTAL_SELL, COL_LAST_7D, COL_LAST_15D, COL_LAST_30D]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    df[COL_ITEM_ID] = df[COL_ITEM_ID].astype(str).str.strip()
    df[COL_WH_NAME] = df[COL_WH_NAME].astype(str).str.strip()

    return df, snap_date


def build_sku_lookup():
    rows = sb.table('sku_channel_ids') \
             .select('sku_id, platform_pid_additional') \
             .eq('channel_code', 'BLK') \
             .execute().data
    return {str(r['platform_pid_additional']): r['sku_id']
            for r in rows if r.get('platform_pid_additional')}


def build_wh_lookup():
    """partner_locations code → location_id for WH rows"""
    rows = sb.table('partner_locations') \
             .select('location_id, code') \
             .eq('location_type', 'WH') \
             .eq('channel_id', 4) \
             .execute().data
    return {r['code']: r['location_id'] for r in rows}


def load_file(filepath: Path, dry_run: bool = False):
    print(f'\n  Loading: {filepath.name}')
    df, snap_date = parse_soh_file(filepath)
    print(f'    Snapshot date: {snap_date}')
    print(f'    Rows parsed:   {len(df)}')

    sku_lookup = build_sku_lookup()
    wh_lookup  = build_wh_lookup()

    # Farukhnagar accumulator: merge into Faridabad
    farukhnagar_rows: dict[str, dict] = {}  # sku_id → partial row
    records = []
    skipped_wh  = set()
    skipped_sku = set()

    for _, row in df.iterrows():
        wh_name = str(row[COL_WH_NAME]).strip()
        item_id = str(row[COL_ITEM_ID]).strip()

        wh_code = WH_SOH_NAME_TO_CODE.get(wh_name)
        if not wh_code:
            skipped_wh.add(wh_name)
            continue

        sku_id = sku_lookup.get(item_id)
        if not sku_id:
            skipped_sku.add(item_id)
            continue

        location_id = wh_lookup.get(wh_code)
        if not location_id:
            print(f'    [WARN] WH code {wh_code!r} not in partner_locations — skipping')
            continue

        record = {
            'snapshot_date':  str(snap_date),
            'location_id':    location_id,
            'sku_id':         sku_id,
            'units_wh':       int(row.get(COL_WH_UNITS,   0) or 0),
            'units_incoming': int(row.get(COL_INCOMING,   0) or 0),
            'units_ds':       int(row.get(COL_DS_UNITS,   0) or 0),
            'units_transit':  int(row.get(COL_TRANSIT,    0) or 0),
            'total_sellable': int(row.get(COL_TOTAL_SELL, 0) or 0),
            'last_7d_sales':  int(row.get(COL_LAST_7D,    0) or 0) or None,
            'last_15d_sales': int(row.get(COL_LAST_15D,   0) or 0) or None,
            'last_30d_sales': int(row.get(COL_LAST_30D,   0) or 0) or None,
        }

        if wh_name == 'Farukhnagar - SR':
            # Accumulate into Faridabad (same location_id after redirection)
            key = (location_id, sku_id)
            if key not in farukhnagar_rows:
                farukhnagar_rows[key] = record.copy()
            else:
                # Add inventory units to existing Faridabad row
                for field in ('units_wh', 'units_incoming', 'units_ds',
                              'units_transit', 'total_sellable'):
                    farukhnagar_rows[key][field] += record[field]
            continue

        records.append(record)

    # Merge Farukhnagar additions into records
    for (loc_id, sku_id), far_rec in farukhnagar_rows.items():
        # Find existing Faridabad row for same sku_id
        matched = False
        for rec in records:
            if rec['location_id'] == loc_id and rec['sku_id'] == sku_id:
                for field in ('units_wh', 'units_incoming', 'units_ds',
                              'units_transit', 'total_sellable'):
                    rec[field] += far_rec[field]
                matched = True
                break
        if not matched:
            records.append(far_rec)

    print(f'    Records to upsert: {len(records)}')
    if skipped_wh:
        print(f'    [WARN] Unknown WH names: {sorted(skipped_wh)}')
    if skipped_sku:
        print(f'    [WARN] Unknown Item IDs: {sorted(skipped_sku)}')

    if dry_run:
        print('    DRY RUN — no writes')
        return

    if records:
        sb.table('blinkit_inventory_snapshots').upsert(
            records,
            on_conflict='snapshot_date,location_id,sku_id'
        ).execute()
        print(f'    Upserted {len(records)} rows')

    # Verification
    check = sb.table('blinkit_inventory_snapshots') \
              .select('sku_id, units_wh, units_incoming') \
              .eq('snapshot_date', str(snap_date)) \
              .execute().data
    print(f'    Post-load count in DB: {len(check)} rows for {snap_date}')
    if len(check) != len(records):
        print(f'    [WARN] Count mismatch — expected {len(records)}, got {len(check)}')


def main():
    parser = argparse.ArgumentParser(description='Blinkit SOH inventory loader')
    parser.add_argument('--file', help='Load a specific .xlsx file')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    print(f'Environment: {env}')

    if args.file:
        load_file(Path(args.file), dry_run=args.dry_run)
    else:
        files = list(SOH_DIR.glob('*.xlsx'))
        if not files:
            print(f'No .xlsx files found in {SOH_DIR}')
            sys.exit(1)
        latest = max(files, key=lambda f: f.stat().st_mtime)
        print(f'Loading latest SOH file: {latest.name}')
        load_file(latest, dry_run=args.dry_run)

    print('\nDone.')


if __name__ == '__main__':
    main()
