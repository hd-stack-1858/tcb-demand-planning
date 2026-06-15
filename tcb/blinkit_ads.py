"""
Canonical Blinkit ADS computation — shared by replenishment.py and forecasting.py.

compute_blinkit_ads(daily_df) takes a DataFrame of daily Blinkit performance rows
(may span more than 30 days) and returns one row per (sku_id, location_id) with:

  filled_in_stock_ads  — velocity when in stock; low-avail DSes filled with SKU median.
                          Used by forecasting.py (forward-looking: assumes adequate stock).

  imputed_ads          — expected orders over a 30-day period accounting for OOS days.
                          Used by replenishment.py (reflects what actually happened).

Imputation rules:
  Never-stocked DS (avail_days == 0 for entire window):
      imputed_ads        = city P50  (conservative — DS is untested for this SKU)
      filled_in_stock_ads = SKU median

  Mid-period OOS DS (0 < avail_days < 30):
      imputed_ads        = (actual_orders + city_P75 × oos_days) / 30
      filled_in_stock_ads = raw in_stock_ads (if avail_days >= min_avail_days) else SKU median
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

MIN_AVAIL_DAYS = 5  # minimum available days for a DS to count as "reliable"

_EMPTY_COLS = [
    'sku_id', 'location_id', 'city',
    'avail_days', 'oos_days', 'total_days',
    'raw_in_stock_ads', 'filled_in_stock_ads', 'imputed_ads',
    'never_stocked',
    'city_p50_ads', 'city_p75_ads',
    'sku_p25_ads', 'sku_p75_ads', 'sku_p90_ads',
    'assessment_start', 'assessment_end',
]


def compute_blinkit_ads(daily_df: pd.DataFrame, min_avail_days: int = MIN_AVAIL_DAYS) -> pd.DataFrame:
    """
    Compute ADS per (sku_id, location_id) from daily Blinkit performance data.

    Applies a rolling 30-day window per SKU (from each SKU's latest data_date).
    daily_df may contain more history — the window is applied internally.

    Required columns:
        data_date (date), location_id, sku_id, city,
        inventory_available (bool), total_orders (int)

    Returns one row per (sku_id, location_id) with columns:
        sku_id, location_id, city
        avail_days, oos_days, total_days
        raw_in_stock_ads      orders/avail_day; 0.0 if never stocked
        filled_in_stock_ads   raw for reliable DSes; SKU-median fill for low-avail
        imputed_ads           (actual_orders + P_imputation × oos_days) / 30
        never_stocked         True if avail_days == 0 for entire window
        city_p50_ads          city P50 from reliable DSes
        city_p75_ads          city P75 from reliable DSes
        sku_p25_ads, sku_p75_ads, sku_p90_ads
        assessment_start, assessment_end
    """
    if daily_df.empty:
        return pd.DataFrame(columns=_EMPTY_COLS)

    # ── Rolling 30-day window per SKU ─────────────────────────────────────────
    max_date_per_sku = daily_df.groupby('sku_id')['data_date'].max().to_dict()
    cutoff = daily_df['sku_id'].map(lambda s: max_date_per_sku[s] - timedelta(days=29))
    df = daily_df[daily_df['data_date'] >= cutoff].copy()

    min_date_per_sku = df.groupby('sku_id')['data_date'].min().to_dict()

    # ── Step 1: DS-level raw stats ────────────────────────────────────────────
    records = []
    for (sku_id, loc_id), grp in df.groupby(['sku_id', 'location_id']):
        avail           = grp[grp['inventory_available']]
        avail_days      = len(avail)
        oos_days        = len(grp) - avail_days
        orders_on_avail = int(avail['total_orders'].sum())
        raw_ads         = float(orders_on_avail) / avail_days if avail_days > 0 else 0.0
        city_vals       = grp['city'].dropna()
        city            = str(city_vals.iloc[0]).strip() if len(city_vals) > 0 else None
        records.append({
            'sku_id':           sku_id,
            'location_id':      loc_id,
            'city':             city,
            'avail_days':       avail_days,
            'oos_days':         oos_days,
            'total_days':       len(grp),
            'orders_on_avail':  orders_on_avail,
            'raw_in_stock_ads': round(raw_ads, 4),
            'never_stocked':    avail_days == 0,
        })

    if not records:
        return pd.DataFrame(columns=_EMPTY_COLS)

    ads_df = pd.DataFrame(records)

    # ── Step 2: City and SKU percentiles from reliable DSes ───────────────────
    reliable     = ads_df[(ads_df['avail_days'] >= min_avail_days) & ads_df['city'].notna()]
    sku_reliable = ads_df[ads_df['avail_days'] >= min_avail_days]

    city_p50: dict[tuple, float] = {}
    city_p75: dict[tuple, float] = {}
    if not reliable.empty:
        for (sku_id, city), grp in reliable.groupby(['sku_id', 'city']):
            vals = grp['raw_in_stock_ads'].values
            city_p50[(sku_id, city)] = float(np.percentile(vals, 50))
            city_p75[(sku_id, city)] = float(np.percentile(vals, 75))

    sku_p25: dict[str, float] = {}
    sku_p50: dict[str, float] = {}
    sku_p75: dict[str, float] = {}
    sku_p90: dict[str, float] = {}
    if not sku_reliable.empty:
        for sku_id, grp in sku_reliable.groupby('sku_id'):
            vals = grp['raw_in_stock_ads'].values
            sku_p25[sku_id] = float(np.percentile(vals, 25))
            sku_p50[sku_id] = float(np.percentile(vals, 50))
            sku_p75[sku_id] = float(np.percentile(vals, 75))
            sku_p90[sku_id] = float(np.percentile(vals, 90))

    # ── Step 3: filled_in_stock_ads (forecast uses this) ─────────────────────
    # Reliable DSes: use raw velocity. Low-avail DSes: fill with SKU median.
    def _filled(row) -> float:
        if row['avail_days'] >= min_avail_days:
            return row['raw_in_stock_ads']
        return sku_p50.get(row['sku_id'], 0.0)

    ads_df['filled_in_stock_ads'] = ads_df.apply(_filled, axis=1).round(4)

    # ── Step 4: imputed_ads (replenishment uses this) ─────────────────────────
    # Never-stocked: city P50 — conservative; DS is untested for this SKU.
    # Mid-period OOS: blend actual sales + city_P75 imputation for each OOS day.
    def _imputed(row) -> float:
        sku_id = row['sku_id']
        city   = row['city']
        if row['never_stocked']:
            p = city_p50.get((sku_id, city), 0.0) if city else 0.0
            if p == 0.0:
                p = sku_p50.get(sku_id, 0.0)
            return round(p, 4)
        p75 = city_p75.get((sku_id, city), 0.0) if city else 0.0
        if p75 == 0.0:
            p75 = sku_p75.get(sku_id, 0.0)
        return round((row['orders_on_avail'] + p75 * row['oos_days']) / 30, 4)

    ads_df['imputed_ads'] = ads_df.apply(_imputed, axis=1)

    # ── Step 5: Percentile reference columns ──────────────────────────────────
    pct_vals = [
        (round(city_p50.get((s, c), sku_p50.get(s, 0.0)), 4),
         round(city_p75.get((s, c), sku_p75.get(s, 0.0)), 4))
        for s, c in zip(ads_df['sku_id'], ads_df['city'])
    ]
    ads_df['city_p50_ads'], ads_df['city_p75_ads'] = zip(*pct_vals)
    ads_df['sku_p25_ads'] = ads_df['sku_id'].map(sku_p25).fillna(0.0)
    ads_df['sku_p75_ads'] = ads_df['sku_id'].map(sku_p75).fillna(0.0)
    ads_df['sku_p90_ads'] = ads_df['sku_id'].map(sku_p90).fillna(0.0)

    # ── Step 6: Window date metadata ──────────────────────────────────────────
    ads_df['assessment_start'] = ads_df['sku_id'].map(
        lambda s: str(min_date_per_sku.get(s, date.today()))
    )
    ads_df['assessment_end'] = ads_df['sku_id'].map(
        lambda s: str(max_date_per_sku.get(s, date.today()))
    )

    return ads_df.drop(columns=['orders_on_avail'])
