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

sys.path.insert(0, str(Path(__file__).parent.parent))
from ingest.blinkit_wh_resolver import build_wh_name_lookup, resolve_wh_code

# ── Environment ────────────────────────────────────────────────────────────────
env = os.environ.get('TCB_ENV', 'prod')
load_dotenv('.env' if env == 'prod' else '.env.dev')
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

SOH_DIR = Path('data/blinkit/auto/inventory/SOH')

# WH name → code resolution now goes through ingest/blinkit_wh_resolver.py
# (shared with the performance loader and replenishment engine). This loader
# does NOT auto-create new WH rows itself — the performance detail report is
# the "mother file" for that; a WH name this loader doesn't recognize means
# it hasn't shown up in performance data yet either, and gets alerted below
# rather than silently dropped.

# Columns to extract from SOH (after 3-row header parse)
# Names are exact matches to row-2 sub-headers in the Blinkit SOH Excel.
COL_ITEM_ID    = 'Item ID'
COL_ITEM_NAME  = 'Item Name'
COL_WH_FAC_ID  = 'Warehouse Facility ID'
COL_WH_NAME    = 'Warehouse Facility Name'
COL_INCOMING   = 'Incoming scheduled inventory'  # col 8: raw inbound stock (not yet received at WH)
COL_RECALLED   = 'Recalled inventory'            # col 9: being returned to us (still in our lots)
COL_TOTAL_SELL = 'Total sellable'                # col 10: WH + In-between + Darkstore
COL_WH_UNITS   = 'Warehouse'                     # col 11
COL_TRANSIT    = 'In-between'                    # col 12
COL_DS_UNITS   = 'Darkstore'                     # col 13
COL_UNSELLABLE = 'Total unsellable'              # col 14: damaged + lost + expired + near expiry
COL_LAST_7D    = 'Last 7 days'
COL_LAST_15D   = 'Last 15 days'
COL_LAST_30D   = 'Last 30 days'


def parse_soh_file(filepath: Path) -> tuple[pd.DataFrame, date]:
    """
    Parse 3-row-header SOH Excel file.
    Returns (DataFrame, snapshot_date).
    """
    raw = pd.read_excel(filepath, header=None)

    # Row 0 has the timestamp. Two known formats:
    #   Auto-downloaded: "This sheet was generated at 2026-06-05 12:03:55"
    #   Manual export:   "As of 20 May 2026"
    timestamp_cell = str(raw.iloc[0, 0]) if pd.notna(raw.iloc[0, 0]) else ''
    snap_date = date.today()
    # Try ISO format first (auto-downloaded files)
    m_iso = re.search(r'(\d{4})-(\d{2})-(\d{2})', timestamp_cell)
    if m_iso:
        try:
            snap_date = date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except Exception:
            pass
    else:
        # Fallback: "DD Mon YYYY" (manual export)
        m_dmy = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})', timestamp_cell)
        if m_dmy:
            try:
                snap_date = pd.to_datetime(f"{m_dmy.group(1)} {m_dmy.group(2)} {m_dmy.group(3)}").date()
            except Exception:
                pass

    # Row 2 (index 2) has actual column names
    col_names = raw.iloc[2].tolist()
    df = raw.iloc[3:].copy()
    df.columns = col_names
    df = df.dropna(subset=[COL_ITEM_ID, COL_WH_NAME])
    df = df[df[COL_ITEM_ID].astype(str).str.strip() != '']

    # Numeric columns
    for col in [COL_INCOMING, COL_RECALLED, COL_TOTAL_SELL,
                COL_WH_UNITS, COL_TRANSIT, COL_DS_UNITS, COL_UNSELLABLE,
                COL_LAST_7D, COL_LAST_15D, COL_LAST_30D]:
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

    sku_lookup  = build_sku_lookup()
    wh_lookup   = build_wh_lookup()
    name_lookup = build_wh_name_lookup(sb)

    # Farukhnagar accumulator: merge into Faridabad
    farukhnagar_rows: dict[str, dict] = {}  # sku_id → partial row
    records = []
    skipped_wh  = set()
    skipped_sku = set()

    for _, row in df.iterrows():
        wh_name = str(row[COL_WH_NAME]).strip()
        item_id = str(row[COL_ITEM_ID]).strip()

        # Do NOT auto-create WH rows here — the performance detail report is
        # the "mother file" for that (ensure_whs_exist there). A name absent
        # from name_lookup means no WH row exists yet anywhere; skip + alert
        # rather than silently drop it.
        if wh_name not in name_lookup:
            skipped_wh.add(wh_name)
            continue
        wh_code = resolve_wh_code(wh_name, name_lookup)

        sku_id = sku_lookup.get(item_id)
        if not sku_id:
            skipped_sku.add(item_id)
            continue

        location_id = wh_lookup.get(wh_code)
        if not location_id:
            print(f'    [WARN] WH code {wh_code!r} not in partner_locations — skipping')
            continue

        record = {
            'snapshot_date':   str(snap_date),
            'location_id':     location_id,
            'sku_id':          sku_id,
            'units_wh':        int(row.get(COL_WH_UNITS,   0) or 0),
            'units_incoming':  int(row.get(COL_INCOMING,   0) or 0),
            'units_ds':        int(row.get(COL_DS_UNITS,   0) or 0),
            'units_transit':   int(row.get(COL_TRANSIT,    0) or 0),
            'total_sellable':  int(row.get(COL_TOTAL_SELL, 0) or 0),
            'units_unsellable':int(row.get(COL_UNSELLABLE, 0) or 0),
            'units_recalled':  int(row.get(COL_RECALLED,   0) or 0),
            'last_7d_sales':   int(row.get(COL_LAST_7D,    0) or 0) or None,
            'last_15d_sales':  int(row.get(COL_LAST_15D,   0) or 0) or None,
            'last_30d_sales':  int(row.get(COL_LAST_30D,   0) or 0) or None,
        }

        if wh_name == 'Farukhnagar - SR':
            # Accumulate into Faridabad (same location_id after redirection)
            key = (location_id, sku_id)
            if key not in farukhnagar_rows:
                farukhnagar_rows[key] = record.copy()
            else:
                # Add inventory units to existing Faridabad row
                for field in ('units_wh', 'units_incoming', 'units_ds', 'units_transit',
                              'total_sellable', 'units_unsellable', 'units_recalled'):
                    farukhnagar_rows[key][field] += record[field]
            continue

        records.append(record)

    # Merge Farukhnagar additions into records
    for (loc_id, sku_id), far_rec in farukhnagar_rows.items():
        # Find existing Faridabad row for same sku_id
        matched = False
        for rec in records:
            if rec['location_id'] == loc_id and rec['sku_id'] == sku_id:
                for field in ('units_wh', 'units_incoming', 'units_ds', 'units_transit',
                              'total_sellable', 'units_unsellable', 'units_recalled'):
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

    if (skipped_wh or skipped_sku) and not dry_run:
        try:
            from automation.email_sender import send_alert
            lines = [f'Blinkit SOH loader ({snap_date}): unmapped rows were skipped — stock for these is silently missing from blinkit_inventory_snapshots until mapped.', '']
            if skipped_wh:
                lines.append(f'Unknown WH names ({len(skipped_wh)}): {sorted(skipped_wh)}')
                lines.append('  -> not yet in partner_locations. If this is a genuinely new WH, run '
                             'the performance loader on a recent file first (it auto-creates WH rows); '
                             'if the name is just a variant/alias, add it to WH_MANUAL_OVERRIDES in '
                             'ingest/blinkit_wh_resolver.py')
            if skipped_sku:
                lines.append(f'Unknown Item IDs ({len(skipped_sku)}): {sorted(skipped_sku)}')
                lines.append('  -> add to sku_channel_ids (platform_pid_additional) for the BLK channel')
            send_alert(
                subject=f'⚠️ Blinkit SOH loader — unmapped WH/SKU rows ({snap_date})',
                body='\n'.join(lines),
            )
        except Exception as exc:
            print(f'    [WARN] Could not send unmapped-rows alert: {exc}')

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
