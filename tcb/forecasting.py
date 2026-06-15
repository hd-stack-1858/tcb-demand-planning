"""
Demand Forecasting Engine — Phase D

Generates 6-month SKU-level demand projections across all channels.
Three models:
  VELOCITY_BASE  — auto-generated (Blinkit: P75 ADS×DS; others: P75 MoM growth)
  USER_FINAL     — manual override entered via Streamlit; never overwritten by engine

Usage:
    python tcb/forecasting.py            # generate + upsert VELOCITY_BASE
    python tcb/forecasting.py --dry-run  # print summary without DB writes
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from tcb.db import get_client
from tcb.blinkit_ads import compute_blinkit_ads

# ── Constants ─────────────────────────────────────────────────────────────────
BLINKIT_CHANNEL_ID  = 4
D2C_CHANNEL_ID      = 10
BLK_EXCLUDE_SKUS    = {"TCB007", "TCB010"}   # inactive / not planned for Blinkit
# Maps expansion-plan SKU ID → ADS-table SKU ID (Blinkit platform variant suffix)
BLK_SKU_ALIAS: dict[str, str] = {"TCB009": "TCB009_1"}
FORECAST_MONTHS     = 6
DEFAULT_GROWTH_RATE  = 0.15    # 15%/month fallback when <2 MoM observations
MAX_MONTHLY_GROWTH   = 0.35    # cap on P75 growth rate — prevents explosive projections from small-data noise
MIN_RELIABLE_VOLUME  = 10      # total units over lookback period; below this, use DEFAULT_GROWTH_RATE
VELOCITY_BASE       = "VELOCITY_BASE"
USER_FINAL          = "USER_FINAL"
LOOKBACK_MONTHS     = 4       # months of history for growth-rate computation
GROSS_STATUSES      = ("FULFILLED", "PENDING", "RTO", "SALE_RETURN", "REPLACEMENT")

LAUNCH_PLAN_PATH = Path("data/blinkit/manual/City Launch Plan_Blinkit.xlsx")

_MONTH_HEADER_MAP = {
    "jun": "2026-06", "jul": "2026-07", "aug": "2026-08",
    "sep": "2026-09", "oct": "2026-10", "nov": "2026-11",
}

# Known city name aliases (plan → lowercase canonical form used in partner_locations.city)
_CITY_ALIASES: dict[str, str] = {
    "delhi": "new delhi", "gurugram": "gurgaon", "bangalore": "bengaluru",
    "bombay": "mumbai", "madras": "chennai", "calcutta": "kolkata",
    "mangalore": "mangaluru", "mysore": "mysuru",
    "trivandrum": "thiruvananthapuram",
    "bhubaneshwar": "bhubaneswar",
}

_ALL_CITIES_SENTINEL = "__ALL__"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _city(name: str) -> str:
    n = name.strip().lower()
    return _CITY_ALIASES.get(n, n)


def _next_n_month_starts(n: int, from_date: date | None = None) -> list[date]:
    """Return the first day of the next N calendar months after from_date."""
    d = from_date or date.today()
    result = []
    y, m = d.year, d.month
    for _ in range(n):
        m += 1
        if m > 12:
            m = 1
            y += 1
        result.append(date(y, m, 1))
    return result


def _paginate(table: str, cols: str, **filters) -> list[dict]:
    db = get_client()
    rows, offset = [], 0
    while True:
        q = db.table(table).select(cols)
        for k, v in filters.items():
            q = q.eq(k, v)
        batch = q.range(offset, offset + 999).execute().data
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


# ── City launch plan ──────────────────────────────────────────────────────────
def parse_city_launch_plan(path: Path | None = None) -> dict[str, dict[str, list[str]]]:
    """
    Parse the Blinkit city launch plan Excel.
    Returns {sku_id: {"2026-06": ["bengaluru", ...], ...}}
    "__ALL__" sentinel means all Blinkit cities for that month.
    """
    p = path or LAUNCH_PLAN_PATH
    if not p.exists():
        print(f"[WARN] City launch plan not found at {p} — Blinkit forecast uses current active DSes only")
        return {}

    df = pd.read_excel(p, header=0)
    df.columns = [str(c).strip() for c in df.columns]

    # Map column header → YYYY-MM month string
    month_cols: dict[str, str] = {}
    for col in df.columns:
        key = col.strip().lower()[:3]
        if key == "cur":   # "Current Cities" — skip
            continue
        for prefix, month_str in _MONTH_HEADER_MAP.items():
            if prefix.startswith(key) or key.startswith(prefix[:3]):
                month_cols[col] = month_str
                break

    result: dict[str, dict[str, list[str]]] = {}
    sku_col = df.columns[0]

    for _, row in df.iterrows():
        sku_id = str(row[sku_col]).strip().upper()
        if not sku_id or sku_id.lower() in ("nan", ""):
            continue
        if sku_id in BLK_EXCLUDE_SKUS:
            continue

        per_month: dict[str, list[str]] = {}
        for col, month_str in month_cols.items():
            cell = str(row.get(col, "")).strip()
            if not cell or cell.lower() in ("nan", ""):
                continue
            if "all cities" in cell.lower():
                per_month[month_str] = [_ALL_CITIES_SENTINEL]
            else:
                per_month[month_str] = [_city(c) for c in cell.split(",") if c.strip()]

        if per_month:
            result[sku_id] = per_month

    return result


# ── Blinkit ADS model ─────────────────────────────────────────────────────────
def forecast_blinkit(forecast_dates: list[date]) -> pd.DataFrame:
    """
    Blinkit demand forecast using ADS × DS count × 30.

    DS count per (SKU, month):
      floor cities  — actual active DS count from eligibility (what's live now)
      new plan cities — non-closed DS count in city × (1 - SKU churn rate)

    churn_rate = sku_moved_out_low_sales / (active + moved_out) across all live cities.

    Returns: sku_id, channel_id, forecast_month (ISO str), units, lo, hi
    """
    print("  [Blinkit] Parsing city launch plan...")
    launch_plan = parse_city_launch_plan()

    print("  [Blinkit] Fetching performance ADS data...")
    perf_rows = _paginate(
        "blinkit_performance_detail",
        "location_id,sku_id,city,total_orders,inventory_available,data_date",
    )
    if not perf_rows:
        print("  [Blinkit] No ADS data found — skipping Blinkit model")
        return pd.DataFrame()
    daily_df = pd.DataFrame(perf_rows)
    daily_df["total_orders"]        = pd.to_numeric(daily_df["total_orders"], errors="coerce").fillna(0).astype(int)
    daily_df["inventory_available"] = daily_df["inventory_available"].fillna(True).astype(bool)
    daily_df["data_date"]           = pd.to_datetime(daily_df["data_date"]).dt.date

    ads_df = compute_blinkit_ads(daily_df)
    # Forecast uses in-stock velocity (assumes adequate stock going forward)
    ads_df = ads_df.rename(columns={"filled_in_stock_ads": "mean_ads"})
    print(f"  [Blinkit] ADS computed for {len(ads_df)} DS-SKU pairs")

    db = get_client()

    # Load all active Blinkit DSes with city
    ds_rows = (
        db.table("partner_locations")
        .select("location_id, city")
        .eq("channel_id", BLINKIT_CHANNEL_ID)
        .eq("location_type", "DARKSTORE")
        .eq("is_active", True)
        .execute().data
    )
    ds_df = pd.DataFrame(ds_rows) if ds_rows else pd.DataFrame(columns=["location_id", "city"])
    ds_df["city_norm"] = ds_df["city"].fillna("").apply(_city)
    all_db_cities = set(ds_df["city_norm"].unique()) - {""}

    # city_norm → set of active (non-closed) location_ids
    city_to_locs: dict[str, set[int]] = {}
    for _, r in ds_df.iterrows():
        if r["city_norm"]:
            city_to_locs.setdefault(r["city_norm"], set()).add(int(r["location_id"]))

    # location_id → city_norm
    loc_to_city = ds_df.set_index("location_id")["city_norm"].to_dict()

    # Load eligibility to compute:
    #   1. active_cities_per_sku  — floor: cities already live for each SKU
    #   2. active_ds_per_sku_city — count of active DSes per (sku_id, city) for floor
    #   3. churn_rates            — sku_moved_out / (active + moved_out) per SKU
    elig_rows = _paginate("blinkit_ds_sku_eligibility", "location_id,sku_id,status")

    active_cities_per_sku:  dict[str, set[str]] = {}
    active_ds_per_sku_city: dict[tuple, int]    = {}
    churn_data:             dict[str, dict]     = {}

    for r in elig_rows:
        sku_e  = r["sku_id"]
        status = r.get("status", "")
        churn_data.setdefault(sku_e, {})
        churn_data[sku_e][status] = churn_data[sku_e].get(status, 0) + 1
        if status == "active":
            c = loc_to_city.get(int(r["location_id"]), "")
            if c:
                active_cities_per_sku.setdefault(sku_e, set()).add(c)
                key = (sku_e, c)
                active_ds_per_sku_city[key] = active_ds_per_sku_city.get(key, 0) + 1

    churn_rates: dict[str, float] = {}
    for sku_e, counts in churn_data.items():
        active_n    = counts.get("active", 0)
        low_sales_n = counts.get("sku_moved_out_low_sales", 0)
        denom = active_n + low_sales_n
        churn_rates[sku_e] = low_sales_n / denom if denom > 0 else 0.0

    # All SKUs to forecast
    all_sku_ids = (set(launch_plan.keys()) | set(active_cities_per_sku.keys())) - BLK_EXCLUDE_SKUS

    # Per-SKU signals: mean_all (central) + p90 (hi bound)
    # mean_all = average ADS across ALL DSes including zero-sellers
    #            = penetration_rate × ADS_of_selling_DSes — the expected value per new DS
    sku_mean_map = ads_df.groupby("sku_id")["mean_ads"].mean().to_dict()
    sku_p90_map  = ads_df.groupby("sku_id")["sku_p90_ads"].first().to_dict()

    sku_signals_all: dict[str, dict] = {}
    for sku_id_k in sku_mean_map:
        sku_signals_all[sku_id_k] = {
            "sku_mean_ads": sku_mean_map[sku_id_k],
            "sku_p90_ads":  sku_p90_map.get(sku_id_k, 0.0),
        }

    # Apply alias mapping (e.g. "TCB009" plan SKU → look up "TCB009_1" ADS signal)
    for plan_sku, ads_sku in BLK_SKU_ALIAS.items():
        if plan_sku not in sku_signals_all and ads_sku in sku_signals_all:
            sku_signals_all[plan_sku] = sku_signals_all[ads_sku]

    # Global fallback: median mean_all across SKUs — only used when a SKU has NO data at all
    all_means = [v["sku_mean_ads"] for v in sku_signals_all.values() if v.get("sku_mean_ads", 0) > 0]
    global_fallback_ads = float(np.median(all_means)) if all_means else 0.01

    rows_out = []
    for sku_id in sorted(all_sku_ids):
        sku_alias_id = BLK_SKU_ALIAS.get(sku_id, sku_id)
        sku_plan  = launch_plan.get(sku_id, {})

        # Floor = cities where SKU is currently active in DB (use alias for TCB009 etc.)
        sku_floor = (
            active_cities_per_sku.get(sku_id, set()) |
            active_cities_per_sku.get(sku_alias_id, set())
        )

        sig = sku_signals_all.get(sku_id, {})
        _mean = sig.get("sku_mean_ads") if sig else None
        _p90  = (sig.get("sku_p90_ads") or 0.0) if sig else 0.0

        # Central estimate: mean_all (expected orders/DS/day including zero-sellers)
        # Fallback only when SKU has NO data at all in blinkit_performance_detail
        p_central = _mean if (_mean is not None and _mean > 0) else global_fallback_ads
        p_hi  = _p90 if _p90 > 0 else p_central * 1.3   # hi = P90 (top-10% DS performance)
        p_lo  = p_central * 0.5                           # lo = half of central (downside)

        # Churn rate: use alias SKU if direct lookup not found
        churn_rate = churn_rates.get(sku_alias_id, churn_rates.get(sku_id, 0.0))

        if not sig:
            print(f"  [Blinkit] INFO: No ADS signal for {sku_id} — fallback {global_fallback_ads:.4f}")

        for fm in forecast_dates:
            month_str = fm.strftime("%Y-%m")

            plan_entry = sku_plan.get(month_str, [])
            if plan_entry == [_ALL_CITIES_SENTINEL]:
                plan_cities = all_db_cities.copy()
            else:
                plan_cities = set(plan_entry)

            # Floor cities: use actual active DS count from eligibility
            floor_ds_count = sum(
                active_ds_per_sku_city.get((sku_id, c), 0) +
                active_ds_per_sku_city.get((sku_alias_id, c), 0)
                for c in sku_floor
            )

            # New plan cities: non-closed DS count × (1 - churn_rate)
            new_cities = plan_cities - sku_floor
            raw_new_ds = sum(len(city_to_locs.get(c, set())) for c in new_cities)
            new_ds_count = round(raw_new_ds * (1 - churn_rate))

            ds_count = floor_ds_count + new_ds_count
            if not ds_count:
                continue

            rows_out.append({
                "sku_id":         sku_id,
                "channel_id":     BLINKIT_CHANNEL_ID,
                "forecast_month": fm.isoformat(),
                "units":          max(0, round(p_central * ds_count * 30)),
                "lo":             max(0, round(p_lo * ds_count * 30)),
                "hi":             max(0, round(p_hi * ds_count * 30)),
            })

    print(f"  [Blinkit] Generated {len(rows_out)} SKU-month rows")
    return pd.DataFrame(rows_out) if rows_out else pd.DataFrame()


# ── Historical growth model (Amazon, FnP, FC, Peeko, Ozi, etc.) ───────────────
def fetch_historical_monthly_units(lookback_months: int = LOOKBACK_MONTHS) -> pd.DataFrame:
    """
    Fetch monthly units sold per (sku_id, channel_id) for the last N months.
    Includes FULFILLED and PENDING orders only.
    Returns: sku_id, channel_id, month_start (date), units
    """
    today = date.today()
    cutoff_m = today.month - lookback_months
    cutoff_y = today.year
    while cutoff_m <= 0:
        cutoff_m += 12
        cutoff_y -= 1
    cutoff = date(cutoff_y, cutoff_m, 1).isoformat()

    db = get_client()
    rows_all: list[dict] = []
    offset = 0
    while True:
        batch = (
            db.table("orders")
            .select("sku_id, channel_id, order_date, quantity, status")
            .gte("order_date", cutoff)
            .in_("status", list(GROSS_STATUSES))
            .range(offset, offset + 999)
            .execute().data
        )
        rows_all.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    if not rows_all:
        return pd.DataFrame(columns=["sku_id", "channel_id", "month_start", "units"])

    df = pd.DataFrame(rows_all)
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["month_start"] = df["order_date"].dt.to_period("M").dt.to_timestamp().dt.date
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)

    # Amazon FBM (channel_id=3) rolled into Amazon (channel_id=2)
    df.loc[df["channel_id"] == 3, "channel_id"] = 2

    monthly = (
        df.groupby(["sku_id", "channel_id", "month_start"], as_index=False)["quantity"]
        .sum()
        .rename(columns={"quantity": "units"})
    )
    return monthly


def compute_bullish_growth_rates(
    monthly_df: pd.DataFrame,
    default_rate: float = DEFAULT_GROWTH_RATE,
    max_rate: float = MAX_MONTHLY_GROWTH,
    min_volume: int = MIN_RELIABLE_VOLUME,
) -> pd.DataFrame:
    """
    For each (sku_id, channel_id): compute P25/P75/P90 of month-over-month growth rates.

    Falls back to default_rate if:
      - fewer than 2 valid MoM growth observations, OR
      - total units over the lookback period < min_volume (unreliable small-number data)

    P75 and P90 are capped at max_rate to prevent explosive projections from noisy
    small-data growth rates (e.g., 1 → 5 = 400% is not a reliable trend signal).

    Returns: sku_id, channel_id, p25_rate, p75_rate, p90_rate, _used_default
    """
    records = []
    for (sku_id, ch_id), grp in monthly_df.groupby(["sku_id", "channel_id"]):
        total_units = int(grp["units"].sum())
        units_by_month = grp.sort_values("month_start")["units"].tolist()
        rates = []
        for prev, curr in zip(units_by_month[:-1], units_by_month[1:]):
            if prev > 0:
                rates.append((curr - prev) / prev)

        use_default = len(rates) < 2 or total_units < min_volume
        if use_default:
            records.append({
                "sku_id": sku_id, "channel_id": ch_id,
                "p25_rate": default_rate * 0.5,  # lo = half of default
                "p75_rate": default_rate,
                "p90_rate": default_rate * 1.5,
                "_used_default": True,
            })
        else:
            p25 = float(np.percentile(rates, 25))
            p75 = min(float(np.percentile(rates, 75)), max_rate)
            p90 = min(float(np.percentile(rates, 90)), max_rate * 1.15)
            records.append({
                "sku_id": sku_id, "channel_id": ch_id,
                "p25_rate": p25, "p75_rate": p75, "p90_rate": p90,
                "_used_default": False,
            })
    return pd.DataFrame(records) if records else pd.DataFrame()


def forecast_other_channels(forecast_dates: list[date]) -> pd.DataFrame:
    """
    Demand forecast for all non-Blinkit, non-D2C channels using historical growth.
    Returns: sku_id, channel_id, forecast_month (ISO str), units, lo, hi
    """
    print("  [Growth model] Fetching historical monthly units...")
    monthly_df = fetch_historical_monthly_units()
    if monthly_df.empty:
        print("  [Growth model] No historical data found")
        return pd.DataFrame()

    # Exclude Blinkit and D2C from growth model
    monthly_df = monthly_df[
        ~monthly_df["channel_id"].isin([BLINKIT_CHANNEL_ID, D2C_CHANNEL_ID])
    ]
    if monthly_df.empty:
        return pd.DataFrame()

    growth_df = compute_bullish_growth_rates(monthly_df)
    if growth_df.empty:
        return pd.DataFrame()

    # Last observed month's units per (sku, channel)
    last_units = (
        monthly_df.sort_values("month_start")
        .groupby(["sku_id", "channel_id"])
        .last()["units"]
        .reset_index()
    )
    growth_df = growth_df.merge(last_units, on=["sku_id", "channel_id"], how="left")

    n_used_default = int(growth_df["_used_default"].sum())
    n_total = len(growth_df)
    print(f"  [Growth model] Growth rates computed for {n_total} SKU-channel pairs "
          f"({n_used_default} using {DEFAULT_GROWTH_RATE*100:.0f}% default)")

    rows_out = []
    for _, r in growth_df.iterrows():
        base_units  = float(r.get("units", 0) or 0)
        p75_rate    = float(r["p75_rate"])
        p25_rate    = float(r["p25_rate"])
        p90_rate    = float(r["p90_rate"])

        u = base_units
        l = base_units
        h = base_units
        for fm in forecast_dates:
            u = u * (1 + p75_rate)
            l = l * (1 + p25_rate)
            h = h * (1 + p90_rate)
            rows_out.append({
                "sku_id":         r["sku_id"],
                "channel_id":     int(r["channel_id"]),
                "forecast_month": fm.isoformat(),
                "units":          max(0, round(u)),
                "lo":             max(0, round(l)),
                "hi":             max(0, round(h)),
            })

    print(f"  [Growth model] Generated {len(rows_out)} SKU-channel-month rows")
    return pd.DataFrame(rows_out) if rows_out else pd.DataFrame()


# ── Master generate function ──────────────────────────────────────────────────
def generate_base_forecast(months: int = FORECAST_MONTHS, dry_run: bool = False) -> pd.DataFrame:
    """
    Compute VELOCITY_BASE forecast for all channels and upsert to demand_forecasts.
    USER_FINAL rows are never touched.
    Returns the combined forecast DataFrame for inspection.
    """
    forecast_dates = _next_n_month_starts(months)
    print(f"Generating VELOCITY_BASE forecast for {months} months: "
          f"{forecast_dates[0]} to {forecast_dates[-1]}")

    blk_df    = forecast_blinkit(forecast_dates)
    others_df = forecast_other_channels(forecast_dates)

    parts = [df for df in [blk_df, others_df] if not df.empty]
    if not parts:
        print("No forecast data generated.")
        return pd.DataFrame()

    combined = pd.concat(parts, ignore_index=True)
    combined["model"] = VELOCITY_BASE
    # Rename for DB columns
    combined = combined.rename(columns={"units": "forecast_units", "lo": "confidence_lo", "hi": "confidence_hi"})

    print(f"\nTotal rows to upsert: {len(combined)}")

    if dry_run:
        print("\n[DRY RUN] Sample output:")
        print(combined.groupby(["channel_id", "sku_id"]).agg(
            months=("forecast_month", "count"),
            total_units=("forecast_units", "sum")
        ).to_string())
        return combined

    # Upsert VELOCITY_BASE rows — conflict target includes model so USER_FINAL is untouched
    db = get_client()
    records = combined.to_dict("records")
    batch_size = 200
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        db.table("demand_forecasts").upsert(
            batch,
            on_conflict="sku_id,channel_id,forecast_month,model",
        ).execute()

    # Record last run time in company_config
    now_str = date.today().isoformat()
    db.table("company_config").upsert(
        {"key": "forecast_velocity_base_last_run", "value": now_str,
         "notes": "Set by forecasting.py generate_base_forecast()"},
        on_conflict="key",
    ).execute()

    print(f"Upserted {len(records)} VELOCITY_BASE rows.")
    return combined


# ── Streamlit helpers ─────────────────────────────────────────────────────────
def get_forecast_display(months: int = FORECAST_MONTHS) -> pd.DataFrame:
    """
    Return a display DataFrame for the Forecast tab.
    Columns: sku_id, forecast_month, base_units, forecast_units, is_user_locked
    Rows are summed across channels.
    forecast_units = USER_FINAL if set, else VELOCITY_BASE.
    """
    db = get_client()
    forecast_dates = _next_n_month_starts(months)
    date_strs = [fm.isoformat() for fm in forecast_dates]

    rows = (
        db.table("demand_forecasts")
        .select("sku_id,channel_id,forecast_month,forecast_units,model")
        .in_("forecast_month", date_strs)
        .in_("model", [VELOCITY_BASE, USER_FINAL])
        .execute().data
    )
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["forecast_month"] = pd.to_datetime(df["forecast_month"]).dt.date
    df["forecast_units"] = pd.to_numeric(df["forecast_units"], errors="coerce").fillna(0)

    # Separate BASE and USER
    base = df[df["model"] == VELOCITY_BASE].groupby(["sku_id", "forecast_month"])["forecast_units"].sum().reset_index()
    base.columns = ["sku_id", "forecast_month", "base_units"]

    user = df[df["model"] == USER_FINAL].groupby(["sku_id", "forecast_month"])["forecast_units"].sum().reset_index()
    user.columns = ["sku_id", "forecast_month", "user_units"]
    user["is_user_locked"] = True

    merged = base.merge(user, on=["sku_id", "forecast_month"], how="left")
    merged["is_user_locked"] = merged["is_user_locked"].fillna(False)
    merged["forecast_units"] = merged.apply(
        lambda r: r["user_units"] if r["is_user_locked"] else r["base_units"], axis=1
    ).fillna(0).astype(int)
    merged["base_units"] = merged["base_units"].fillna(0).astype(int)

    return merged[["sku_id", "forecast_month", "base_units", "forecast_units", "is_user_locked"]]


def get_forecast_channel_breakdown(sku_id: str, months: int = FORECAST_MONTHS) -> pd.DataFrame:
    """
    Per-channel forecast breakdown for a single SKU.
    Returns: channel_id, forecast_month, base_units, forecast_units, is_user_locked
    """
    db = get_client()
    forecast_dates = _next_n_month_starts(months)
    date_strs = [fm.isoformat() for fm in forecast_dates]

    rows = (
        db.table("demand_forecasts")
        .select("channel_id,forecast_month,forecast_units,model")
        .eq("sku_id", sku_id)
        .in_("forecast_month", date_strs)
        .in_("model", [VELOCITY_BASE, USER_FINAL])
        .execute().data
    )
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["forecast_month"] = pd.to_datetime(df["forecast_month"]).dt.date
    df["forecast_units"] = pd.to_numeric(df["forecast_units"], errors="coerce").fillna(0)

    base = df[df["model"] == VELOCITY_BASE][["channel_id", "forecast_month", "forecast_units"]].copy()
    base.columns = ["channel_id", "forecast_month", "base_units"]
    user = df[df["model"] == USER_FINAL][["channel_id", "forecast_month", "forecast_units"]].copy()
    user.columns = ["channel_id", "forecast_month", "user_units"]
    user["is_user_locked"] = True

    merged = base.merge(user, on=["channel_id", "forecast_month"], how="left")
    merged["is_user_locked"] = merged["is_user_locked"].fillna(False)
    merged["forecast_units"] = merged.apply(
        lambda r: r["user_units"] if r["is_user_locked"] else r["base_units"], axis=1
    ).fillna(0).astype(int)
    merged["base_units"] = merged["base_units"].fillna(0).astype(int)
    return merged


def lock_sku_month(sku_id: str, month_date: date, total_units: int) -> None:
    """
    Lock a total forecast for a SKU × Month by distributing across channels
    proportionally to the VELOCITY_BASE channel mix.
    Upserts USER_FINAL rows (overwrites any previous USER_FINAL for this sku+month).
    """
    db = get_client()
    month_str = month_date.isoformat()

    # Get VELOCITY_BASE channel proportions for this sku+month
    base_rows = (
        db.table("demand_forecasts")
        .select("channel_id,forecast_units")
        .eq("sku_id", sku_id)
        .eq("forecast_month", month_str)
        .eq("model", VELOCITY_BASE)
        .execute().data
    )
    if not base_rows:
        print(f"[WARN] No VELOCITY_BASE data for {sku_id} {month_str} — cannot lock")
        return

    base_total = sum(float(r.get("forecast_units") or 0) for r in base_rows)
    records = []
    if base_total > 0:
        for r in base_rows:
            ch_share = float(r.get("forecast_units") or 0) / base_total
            records.append({
                "sku_id": sku_id, "channel_id": r["channel_id"],
                "forecast_month": month_str,
                "forecast_units": max(0, round(total_units * ch_share)),
                "model": USER_FINAL,
            })
    else:
        # Base is all zeros — distribute evenly
        n = len(base_rows)
        for r in base_rows:
            records.append({
                "sku_id": sku_id, "channel_id": r["channel_id"],
                "forecast_month": month_str,
                "forecast_units": max(0, round(total_units / n)),
                "model": USER_FINAL,
            })

    db.table("demand_forecasts").upsert(
        records,
        on_conflict="sku_id,channel_id,forecast_month,model",
    ).execute()


def reset_sku_month(sku_id: str, month_date: date) -> None:
    """Delete all USER_FINAL rows for a SKU × Month. VELOCITY_BASE shows through."""
    db = get_client()
    (
        db.table("demand_forecasts")
        .delete()
        .eq("sku_id", sku_id)
        .eq("forecast_month", month_date.isoformat())
        .eq("model", USER_FINAL)
        .execute()
    )


def get_last_run_date() -> str | None:
    """Return the date string of the last VELOCITY_BASE forecast run, or None."""
    db = get_client()
    rows = (
        db.table("company_config")
        .select("value")
        .eq("key", "forecast_velocity_base_last_run")
        .execute().data
    )
    return rows[0]["value"] if rows else None


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate demand forecast")
    parser.add_argument("--dry-run", action="store_true", help="Print without DB writes")
    parser.add_argument("--months", type=int, default=FORECAST_MONTHS)
    args = parser.parse_args()

    result = generate_base_forecast(months=args.months, dry_run=args.dry_run)
    if not result.empty:
        print("\nSummary by channel:")
        print(
            result.groupby("channel_id")
            .agg(rows=("sku_id", "count"), total_units=("forecast_units", "sum"))
            .to_string()
        )
