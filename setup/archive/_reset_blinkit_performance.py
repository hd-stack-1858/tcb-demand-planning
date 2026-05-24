"""
One-time reset: clear blinkit_ds_sku_eligibility and blinkit_performance_ads,
then reload from the latest performance CSV file (by file modification time).

Run WITHOUT --go to see a dry-run preview first.

Usage:
    python setup/archive/_reset_blinkit_performance.py        # dry run
    python setup/archive/_reset_blinkit_performance.py --go   # actually execute
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from supabase import create_client
import pandas as pd

env = os.environ.get('TCB_ENV', 'prod')
load_dotenv('.env' if env == 'prod' else '.env.dev')
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

DETAIL_DIRS = [
    Path('data/blinkit/manual/product_performance/detail'),
    Path('data/blinkit/auto/product_performance/detail'),
]
REQUIRED_COLS = frozenset({'Item ID', 'Darkstore name', 'Considered for assessment (Y/N)',
                            'Serving warehouse', 'Date', 'Total orders'})


def find_latest_csv() -> Path | None:
    """Return the latest valid performance detail CSV by file modification time."""
    candidates = []
    for d in DETAIL_DIRS:
        if not d.exists():
            continue
        for fpath in d.glob('*.csv'):
            try:
                hdr = pd.read_csv(fpath, nrows=0)
                hdr.columns = [c.strip() for c in hdr.columns]
                if REQUIRED_COLS.issubset(set(hdr.columns)):
                    candidates.append(fpath)
            except Exception:
                continue
    return max(candidates, key=lambda f: f.stat().st_mtime) if candidates else None


def count_rows(table: str) -> int:
    # Supabase REST: fetch with count
    resp = sb.table(table).select('*', count='exact').limit(1).execute()
    return resp.count if resp.count is not None else len(resp.data)


def clear_table(table: str, filter_col: str, sentinel: str):
    """Delete all rows via a filter that matches everything."""
    sb.table(table).delete().neq(filter_col, sentinel).execute()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--go', action='store_true',
                        help='Actually truncate and reload (default: dry run)')
    args = parser.parse_args()
    dry_run = not args.go

    print(f'Environment: {env}')
    if dry_run:
        print('DRY RUN — pass --go to actually execute\n')

    latest = find_latest_csv()
    if not latest:
        print('ERROR: No valid performance CSV found in:')
        for d in DETAIL_DIRS:
            print(f'  {d}')
        sys.exit(1)

    mtime = datetime.fromtimestamp(latest.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    print(f'Latest file: {latest.name}')
    print(f'Modified:    {mtime}')

    df_full = pd.read_csv(latest, low_memory=False)
    print(f'Rows in file: {len(df_full):,}')

    elig_count = count_rows('blinkit_ds_sku_eligibility')
    ads_count  = count_rows('blinkit_performance_ads')
    print(f'\nCurrent DB rows:')
    print(f'  blinkit_ds_sku_eligibility : {elig_count:,}')
    print(f'  blinkit_performance_ads    : {ads_count:,}')

    if dry_run:
        print('\nWould:')
        print('  1. Delete all rows in blinkit_performance_ads')
        print('  2. Delete all rows in blinkit_ds_sku_eligibility')
        print(f'  3. Run loader (Pass 0 + 1 + 2) on: {latest.name}')
        print('\nRe-run with --go to proceed.')
        return

    print('\nClearing blinkit_performance_ads...')
    clear_table('blinkit_performance_ads', 'data_date', '1800-01-01')
    print('  Done.')

    print('Clearing blinkit_ds_sku_eligibility...')
    clear_table('blinkit_ds_sku_eligibility', 'updated_date', '1800-01-01')
    print('  Done.')

    print(f'\nRunning loader on {latest.name}...')
    from ingest.blinkit_performance_loader import (
        build_sku_lookup, build_ds_location_lookup, build_wh_location_lookup,
        build_ds_parent_lookup, process_file,
    )

    sku_lookup       = build_sku_lookup()
    ds_lookup        = build_ds_location_lookup()
    wh_lookup        = build_wh_location_lookup()
    ds_parent_lookup = build_ds_parent_lookup()

    process_file(latest, sku_lookup, ds_lookup, wh_lookup, ds_parent_lookup)

    print('\nVerifying...')
    new_elig = count_rows('blinkit_ds_sku_eligibility')
    new_ads  = count_rows('blinkit_performance_ads')
    print(f'  blinkit_ds_sku_eligibility : {new_elig:,} rows')
    print(f'  blinkit_performance_ads    : {new_ads:,} rows')
    print('\nDone.')


if __name__ == '__main__':
    main()
