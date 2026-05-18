"""
The Cradle Box — Sales MIS Dashboard (Phase C)
Read-only analytics. Auth via Streamlit Cloud viewer allowlist (no code needed).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Bridge Streamlit Cloud secrets → env vars so that tcb/db.py can read them.
# On Streamlit Cloud there is no .env file; credentials live in app secrets.
# Locally, .env is loaded by db.py directly — this block is a no-op locally.
try:
    import streamlit as _st
    for _k in ("SUPABASE_URL", "SUPABASE_KEY"):
        if _k in _st.secrets and not os.environ.get(_k):
            os.environ[_k] = _st.secrets[_k]
except Exception:
    pass

import calendar
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from tcb.db import get_orders_raw

st.set_page_config(
    page_title="TCB Sales MIS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

GROSS_STATUSES  = {"FULFILLED", "PENDING", "RTO", "SALE_RETURN", "REPLACEMENT"}
NET_STATUSES    = {"FULFILLED", "PENDING"}
RETURN_STATUSES = {"RTO", "SALE_RETURN", "REPLACEMENT"}
ALL_STATUSES    = {"FULFILLED", "PENDING", "CANCELLED", "RTO", "SALE_RETURN", "REPLACEMENT"}
STATUS_ORDER    = ["FULFILLED", "REPLACEMENT", "PENDING", "RTO", "SALE_RETURN", "CANCELLED"]

# Canonical display names; DB has alternate spellings mapped below
BLINKIT_CITIES      = ["Bengaluru", "Chennai", "Ghaziabad", "Gurgaon", "Hyderabad", "New Delhi"]
BLINKIT_CITY_DB_MAP = {c: [c] for c in BLINKIT_CITIES}
BLINKIT_CITY_DB_MAP["Gurgaon"]   = ["Gurgaon", "Gurugram"]   # same city, two spellings
BLINKIT_CITY_DB_MAP["New Delhi"]  = ["New Delhi", "Delhi"]    # same city, two spellings
# All DB city values that belong to a Blinkit city (used for "Others" exclusion)
_ALL_BLINKIT_DB_CITIES = {v for vals in BLINKIT_CITY_DB_MAP.values() for v in vals}

CHANNEL_COLOR_MAP = {
    "Amazon":         "#FF9900",
    "Blinkit":        "#FFED29",
    "First Cry":      "#A12134",
    "Ferns & Petals": "#7D8035",
    "Peeko":          "#CBF2B8",
    "Ozi":            "#F1DFEC",
    "Kiddo":          "#F46060",
    "D2C":            "#222222",
}


# ── Data loading ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    rows = get_orders_raw()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["month"]      = df["order_date"].dt.to_period("M")
    df["month_dt"]   = df["month"].dt.to_timestamp()
    df["year"]       = df["order_date"].dt.year
    df["quarter"]    = df["order_date"].dt.quarter
    for col in ("gross_value", "selling_price", "mrp", "quantity"):
        df[col] = pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0)
    df["status"] = df["status"].fillna("FULFILLED")
    df["channel_name"] = df["channel_name"].replace({"Amazon FBM": "Amazon", "Own Website": "D2C"})
    return df


# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt_inr(val: float) -> str:
    if val >= 1_00_000:
        return f"₹{val/1_00_000:.1f}L"
    if val >= 1_000:
        return f"₹{val/1_000:.1f}K"
    return f"₹{val:.0f}"


def pct(num, denom) -> float:
    return round(100 * num / denom, 1) if denom else 0.0


def return_rate_pct(grp: pd.DataFrame) -> float:
    base = grp[grp["status"].isin({"FULFILLED", "RTO", "SALE_RETURN", "REPLACEMENT"})]
    return pct(
        base[base["status"].isin(RETURN_STATUSES)]["quantity"].sum(),
        base["quantity"].sum(),
    )


def fmt_delta(val) -> str:
    if val is None:
        return "—"
    return f"{'+'if val>0 else ''}{val:.1f}%"


def colour_delta(val) -> str:
    if not isinstance(val, str) or val == "—":
        return ""
    try:
        v = float(val.replace("%", "").replace("+", ""))
        if v > 0:
            return "color: green"
        if v < 0:
            return "color: red"
    except ValueError:
        pass
    return ""


def blue_gradient(col: pd.Series) -> pd.Series:
    """Column-wise blue gradient — each month column normalised independently."""
    max_val = col.max() if col.max() else 1
    return col.map(
        lambda v: f"background-color: rgba(30, 100, 255, {min(v / max_val, 1) * 0.6:.2f})"
    )


def red_gradient(col: pd.Series) -> pd.Series:
    """Column-wise red gradient — each column normalised independently."""
    max_val = col.max() if col.max() else 1
    return col.map(
        lambda v: f"background-color: rgba(255, 80, 0, {min(v / max_val, 1) * 0.6:.2f})"
    )


def colour_rr(val) -> str:
    if not isinstance(val, str):
        return ""
    try:
        v = float(val.replace("%", ""))
        if v < 5:
            return "color: green"
        if v < 15:
            return "color: orange"
        return "color: red"
    except ValueError:
        return ""


def _cur_mult() -> float:
    """Multiplier to project current month-to-date to full month-end.
    Data is available through yesterday, so use today.day - 1 as elapsed days."""
    today = date.today()
    data_days = max(today.day - 1, 1)
    return calendar.monthrange(today.year, today.month)[1] / data_days


def _project_col(df: pd.DataFrame, value_col: str, mult: float) -> pd.DataFrame:
    """Scale current-month rows by mult, rounded to nearest whole number."""
    today  = date.today()
    cur_ts = pd.Timestamp(date(today.year, today.month, 1))
    out    = df.copy()
    mask   = out["month_dt"] == cur_ts
    out.loc[mask, value_col] = (out.loc[mask, value_col] * mult).round(0)
    return out


# ── Sidebar ────────────────────────────────────────────────────────────────────
def sidebar(df: pd.DataFrame) -> dict:
    st.sidebar.markdown("## Filters")

    all_channels = sorted(df["channel_name"].dropna().unique().tolist())
    sel_ch = st.sidebar.multiselect("Channel", ["All Channels"] + all_channels, default=["All Channels"])
    if "All Channels" in sel_ch or not sel_ch:
        sel_ch = all_channels

    all_skus = sorted(df["sku_id"].dropna().unique().tolist())
    sel_sku = st.sidebar.multiselect("SKU", ["All SKUs"] + all_skus, default=["All SKUs"])
    if "All SKUs" in sel_sku or not sel_sku:
        sel_sku = all_skus

    months_avail = sorted(df["month_dt"].dt.to_period("M").unique().astype(str).tolist())
    if months_avail:
        sel_range = st.sidebar.select_slider(
            "Month range", options=months_avail,
            value=(months_avail[0], months_avail[-1]),
        )
    else:
        sel_range = (None, None)

    city_options = BLINKIT_CITIES + ["Others"]
    sel_city = st.sidebar.multiselect("City", ["All Cities"] + city_options, default=["All Cities"])
    if "All Cities" in sel_city or not sel_city:
        sel_city = ["__all__"]

    mode = st.sidebar.radio(
        "Revenue mode",
        ["Gross (excl. Cancelled)", "Net (Fulfilled only)"],
        index=0,
    )
    st.sidebar.markdown("---")
    st.sidebar.caption("Gross = all statuses except Cancelled  \nNet = Fulfilled + Pending only")

    return {"channels": sel_ch, "skus": sel_sku, "range": sel_range, "net_mode": "Net" in mode, "cities": sel_city}


def _apply_city_filter(df: pd.DataFrame, cities: list) -> pd.DataFrame:
    if "__all__" in cities:
        return df
    specific  = [c for c in cities if c != "Others"]
    db_values = {v for c in specific for v in BLINKIT_CITY_DB_MAP.get(c, [c])}
    if "Others" in cities:
        return df[df["city"].isin(db_values) | ~df["city"].isin(_ALL_BLINKIT_DB_CITIES)]
    return df[df["city"].isin(db_values)]


def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    out = df[df["channel_name"].isin(f["channels"]) & df["sku_id"].isin(f["skus"])]
    if f["range"][0]:
        out = out[out["month_dt"].dt.to_period("M").astype(str) >= f["range"][0]]
    if f["range"][1]:
        out = out[out["month_dt"].dt.to_period("M").astype(str) <= f["range"][1]]
    out = _apply_city_filter(out, f.get("cities", ["__all__"]))
    return out[out["status"] != "CANCELLED"]


def active_df(df: pd.DataFrame, net_mode: bool) -> pd.DataFrame:
    return df[df["status"].isin(NET_STATUSES if net_mode else GROSS_STATUSES)]


# ── Velocity snapshot ──────────────────────────────────────────────────────────
def velocity_snapshot(raw_df: pd.DataFrame) -> None:
    """SKU velocity: one column per day (7 days, most recent first), curr/last month avg."""
    today      = date.today()
    yesterday  = today - timedelta(days=1)
    days       = [yesterday - timedelta(days=i) for i in range(7)]

    cur_period      = pd.Period(today, "M")
    last_period     = cur_period - 1
    last_month_days = calendar.monthrange(last_period.year, last_period.month)[1]

    gross = raw_df[raw_df["status"].isin(GROSS_STATUSES)].copy()
    gross["order_day"] = gross["order_date"].dt.date

    l7_data = gross[(gross["order_day"] >= days[-1]) & (gross["order_day"] <= yesterday)]
    daily_u = l7_data.groupby(["sku_id", "order_day"])["quantity"].sum()

    cm_u = gross[gross["month"] == cur_period].groupby("sku_id")["quantity"].sum()
    lm_u = gross[gross["month"] == last_period].groupby("sku_id")["quantity"].sum()

    sku_name_map = (
        raw_df.dropna(subset=["sku_id"])
        .drop_duplicates("sku_id")
        .set_index("sku_id")["sku_name"]
        .to_dict()
    )
    all_sku_ids = sorted(raw_df["sku_id"].dropna().unique())

    day_cols   = [f"{d.day} {d.strftime('%b')}" for d in days]
    avg_col_cm = f"{today.strftime('%b')} Avg"
    avg_col_lm = f"{last_period.strftime('%b')} Avg"

    vs_lm_col = "vs. LM"

    def _vs_lm_pct(cm_avg, lm_avg):
        return (cm_avg - lm_avg) / lm_avg * 100 if lm_avg else float("nan")

    def _fmt_vs_lm(v):
        return "—" if (v != v) else f"{'+'if v > 0 else ''}{v:.1f}%"

    def _color_vs_lm(v):
        if v != v:
            return ""
        return "color: green" if v > 5 else ("color: red" if v < -5 else "")

    rows = []
    for sku_id in all_sku_ids:
        row = {"SKU Code": sku_id, "SKU Name": sku_name_map.get(sku_id, sku_id)}
        for d, col in zip(days, day_cols):
            row[col] = int(daily_u.get((sku_id, d), 0))
        row[avg_col_cm] = round(cm_u.get(sku_id, 0) / max(today.day - 1, 1), 1)
        row[avg_col_lm] = round(lm_u.get(sku_id, 0) / last_month_days, 1)
        row[vs_lm_col]  = _vs_lm_pct(row[avg_col_cm], row[avg_col_lm])
        rows.append(row)

    vel_df = pd.DataFrame(rows).sort_values("SKU Code").reset_index(drop=True)

    # Drop SKUs with zero units across all columns
    numeric_cols = day_cols + [avg_col_cm, avg_col_lm]
    vel_df = vel_df[vel_df[numeric_cols].sum(axis=1) > 0].reset_index(drop=True)

    total_row = {"SKU Code": "TOTAL", "SKU Name": ""}
    for col in numeric_cols:
        total_row[col] = round(vel_df[col].sum(), 1)
    total_row[vs_lm_col] = _vs_lm_pct(total_row[avg_col_cm], total_row[avg_col_lm])
    total_df = pd.DataFrame([total_row])

    def _style_vel(df):
        return (
            df.style
            .format({avg_col_cm: "{:.1f}", avg_col_lm: "{:.1f}", vs_lm_col: _fmt_vs_lm})
            .map(_color_vs_lm, subset=[vs_lm_col])
        )

    st.subheader("Gross Units Sold")
    st.dataframe(_style_vel(total_df), use_container_width=True, hide_index=True)
    st.dataframe(_style_vel(vel_df),   use_container_width=True, hide_index=True)


# ── Tab 1 — Overview ───────────────────────────────────────────────────────────
def tab_overview(raw_df: pd.DataFrame, fdf: pd.DataFrame, net_mode: bool, filters: dict = None):
    st.caption("Cancelled orders are excluded from all metrics on this tab.")
    adf = active_df(fdf, net_mode)

    # Velocity snapshot + MTD projection use raw_df (no date filter) but should respect
    # channel / SKU / city filters from the sidebar
    filtered_raw = raw_df.copy()
    if filters:
        filtered_raw = filtered_raw[
            filtered_raw["channel_name"].isin(filters["channels"]) &
            filtered_raw["sku_id"].isin(filters["skus"])
        ]
        filtered_raw = _apply_city_filter(filtered_raw, filters.get("cities", ["__all__"]))

    total_orders = adf[["order_id", "channel_id"]].drop_duplicates().shape[0]
    total_units  = int(adf["quantity"].sum())
    gross_rev    = fdf[fdf["status"].isin(GROSS_STATUSES)]["gross_value"].sum()
    net_rev      = fdf[fdf["status"].isin(NET_STATUSES)]["gross_value"].sum()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Orders", f"{total_orders:,}")
    c2.metric("Units", f"{total_units:,}")
    c3.metric("Gross Revenue", fmt_inr(gross_rev))
    c4.metric("Net Revenue", fmt_inr(net_rev))
    c5.metric("Return Rate", f"{return_rate_pct(fdf):.1f}%")

    today = date.today()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    cur = filtered_raw[
        (filtered_raw["order_date"].dt.year  == today.year) &
        (filtered_raw["order_date"].dt.month == today.month) &
        (filtered_raw["status"].isin(NET_STATUSES))
    ]
    mtd_units = int(cur["quantity"].sum())
    mtd_rev   = cur["gross_value"].sum()
    data_days = max(today.day - 1, 1)
    mult = days_in_month / data_days
    st.info(
        f"**{today.strftime('%b %Y')} projection:** "
        f"{mtd_units:,} units so far ({data_days} of {days_in_month} days) "
        f"→ **~{round(mtd_units * mult):,} units** projected | "
        f"{fmt_inr(mtd_rev)} revenue so far → **~{fmt_inr(mtd_rev * mult)}** projected"
    )

    velocity_snapshot(filtered_raw)

    st.markdown("---")

    all_channels = sorted(fdf["channel_name"].dropna().unique().tolist())
    monthly = (
        fdf[fdf["status"].isin(GROSS_STATUSES)]
        .groupby(["month_dt", "channel_name"], as_index=False)["gross_value"].sum()
    )
    monthly["Month"] = monthly["month_dt"].dt.strftime("%b %Y")

    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.subheader("Revenue by Channel")
        if not monthly.empty:
            monthly = monthly.sort_values("month_dt")
            monthly["gross_value_L"] = monthly["gross_value"] / 100_000
            fig = px.bar(
                monthly,
                x="Month", y="gross_value_L", color="channel_name",
                labels={"gross_value_L": "Gross Revenue (₹ Lacs)", "channel_name": "Channel"},
                color_discrete_map=CHANNEL_COLOR_MAP,
                category_orders={
                    "Month":        monthly["Month"].unique().tolist(),
                    "channel_name": all_channels,
                },
            )
            # Total labels on top of each bar
            totals = (
                monthly.groupby(["Month", "month_dt"], sort=False)[["gross_value", "gross_value_L"]]
                .sum().reset_index().sort_values("month_dt")
            )
            for _, row in totals.iterrows():
                fig.add_annotation(
                    x=row["Month"], y=row["gross_value_L"],
                    text=fmt_inr(row["gross_value"]),
                    showarrow=False, yshift=10,
                    font=dict(size=10, color="#333"),
                )
            fig.update_traces(
                hovertemplate="<b>%{fullData.name}</b><br>Month: %{x}<br>Revenue: %{y:.1f}L<extra></extra>"
            )
            fig.update_layout(
                legend_title="Channel", xaxis_title=None, margin=dict(t=35),
                yaxis=dict(ticksuffix="L", tickformat=".0f"),
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("Revenue Share")
        ch_share = (
            fdf[fdf["status"].isin(GROSS_STATUSES)]
            .groupby("channel_name", as_index=False)["gross_value"].sum()
            .sort_values("channel_name")
        )
        if not ch_share.empty:
            fig2 = px.pie(
                ch_share, values="gross_value", names="channel_name",
                hole=0.4, color="channel_name",
                color_discrete_map=CHANNEL_COLOR_MAP,
            )
            fig2.update_traces(texttemplate="%{percent:.1%}")
            fig2.update_layout(legend_title="Channel", margin=dict(t=20))
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Units by Channel")
    pivot_statuses = NET_STATUSES if net_mode else GROSS_STATUSES
    pivot_df = (
        fdf[fdf["status"].isin(pivot_statuses)]
        .groupby(["channel_name", "month_dt"])["quantity"].sum()
        .unstack("month_dt").fillna(0).astype(int)
    )
    if not pivot_df.empty:
        pivot_df.columns = [pd.Timestamp(c).strftime("%b %Y") for c in pivot_df.columns]
        pivot_df["Total"] = pivot_df.sum(axis=1)
        total_row = pivot_df.sum(axis=0).rename("TOTAL")
        pivot_df = pd.concat([pivot_df, total_row.to_frame().T])
        pivot_df.index.name = "Channels"  # set after concat so reset_index names it correctly
        pivot_df = pivot_df.reset_index()

        num_cols      = [c for c in pivot_df.columns if c != "Channels"]
        is_total_mask = [ch == "TOTAL" for ch in pivot_df["Channels"]]

        def _gradient_excl_total(col):
            # normalise against channel rows only — TOTAL would always dominate otherwise
            max_val = max((v for flag, v in zip(is_total_mask, col) if not flag), default=1) or 1
            return pd.Series(
                [
                    "" if flag
                    else f"background-color: rgba(30, 100, 255, {min(v / max_val, 1) * 0.6:.2f})"
                    for flag, v in zip(is_total_mask, col)
                ],
                index=col.index,
            )

        st.dataframe(
            pivot_df.style
            .apply(_gradient_excl_total, axis=0, subset=num_cols)
            .apply(
                lambda row: ["font-weight: bold"] * len(row) if is_total_mask[row.name] else [""] * len(row),
                axis=1,
            ),
            use_container_width=True,
            hide_index=True,
        )


# ── Tab 2 — Trends ─────────────────────────────────────────────────────────────
def tab_trends(fdf: pd.DataFrame, net_mode: bool):
    st.caption("Cancelled orders are excluded from all metrics on this tab.")
    adf = active_df(fdf, net_mode)

    today        = date.today()
    mult         = _cur_mult()
    all_channels = sorted(fdf["channel_name"].dropna().unique().tolist())

    # ── Monthly units trend ───────────────────────────────────────────────────
    st.subheader("Units by Channel")
    monthly_ch = adf.groupby(["month_dt", "channel_name"])["quantity"].sum().reset_index()
    monthly_ch = _project_col(monthly_ch, "quantity", mult)
    monthly_ch["Month"] = monthly_ch["month_dt"].dt.strftime("%b %Y")

    if not monthly_ch.empty:
        monthly_ch = monthly_ch.sort_values("month_dt")
        fig = px.line(
            monthly_ch,
            x="Month", y="quantity", color="channel_name", markers=True,
            labels={"quantity": "Units Sold", "channel_name": "Channel"},
            color_discrete_map=CHANNEL_COLOR_MAP,
            category_orders={
                "Month":        monthly_ch["Month"].unique().tolist(),
                "channel_name": all_channels,
            },
        )
        fig.update_layout(xaxis_title=None, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"⚠️ {today.strftime('%b %Y')} shows projected month-end "
        f"({max(today.day - 1, 1)} days elapsed, {mult:.1f}× multiplier)."
    )

    # ── MoM comparison — 3 tables, channels as rows ───────────────────────────
    st.subheader("Month-on-Month Comparison")

    cur_period = pd.Period(today, "M")
    periods    = [cur_period - i for i in range(4)]  # M, M-1, M-2, M-3
    col_m      = f"{cur_period} (proj)"
    col_m1     = str(cur_period - 1)
    col_m2     = str(cur_period - 2)
    col_avg    = "L3M"
    vs_m1  = f"vs. {col_m1}"   # M(proj) vs M-1
    vs_m2  = f"vs. {col_m2}"   # M-1 vs M-2
    vs_avg = "vs. L3M"          # M(proj) vs 3-month avg
    all_vs = [vs_m1, vs_m2, vs_avg]

    def _grp(ch, period):
        sub = fdf[(fdf["channel_name"] == ch) & (fdf["month"] == period)]
        return sub[sub["status"].isin(GROSS_STATUSES)]

    def _grp_all(period):
        sub = fdf[fdf["month"] == period]
        return sub[sub["status"].isin(GROSS_STATUSES)]

    def _ch_val(ch, period, metric):
        g = _grp(ch, period)
        if metric == "units":   return float(g["quantity"].sum())
        if metric == "orders":  return float(g[["order_id", "channel_id"]].drop_duplicates().shape[0])
        if metric == "revenue": return float(g["gross_value"].sum())
        if metric == "asp":
            u = float(g["quantity"].sum())
            return float(g["gross_value"].sum()) / u if u else float("nan")
        if metric == "cart_size":
            o = float(g[["order_id", "channel_id"]].drop_duplicates().shape[0])
            return float(g["gross_value"].sum()) / o if o else float("nan")
        return 0.0

    def _total_val(period, metric):
        g = _grp_all(period)
        if metric == "units":   return float(g["quantity"].sum())
        if metric == "orders":  return float(g[["order_id", "channel_id"]].drop_duplicates().shape[0])
        if metric == "revenue": return float(g["gross_value"].sum())
        if metric == "asp":
            u = float(g["quantity"].sum())
            return float(g["gross_value"].sum()) / u if u else float("nan")
        if metric == "cart_size":
            o = float(g[["order_id", "channel_id"]].drop_duplicates().shape[0])
            return float(g["gross_value"].sum()) / o if o else float("nan")
        return 0.0

    def _nanavg(values):
        valid = [v for v in values if v == v]
        return sum(valid) / len(valid) if valid else float("nan")

    def _vs_pct(a, b):
        if a != a or b != b: return float("nan")
        return (a - b) / b * 100 if b else float("nan")

    def _fmt_vs(v):
        return "—" if (v != v) else f"{'+'if v > 0 else ''}{v:.1f}%"

    def _color_vs(v):
        if v != v:
            return ""
        return "color: red" if v < -5 else ("color: green" if v > 5 else "")

    def _mom_table(metric, fmt_fn, project=True):
        channels = sorted(fdf["channel_name"].dropna().unique())
        rows = []
        for ch in channels:
            vals   = [_ch_val(ch, p, metric) for p in periods]
            avg    = _nanavg(vals[1:])
            m_proj = vals[0] * mult if project else vals[0]
            rows.append({
                "Channel": ch,
                col_m:   fmt_fn(m_proj),
                col_m1:  fmt_fn(vals[1]),
                vs_m1:   _vs_pct(m_proj, vals[1]),
                col_m2:  fmt_fn(vals[2]),
                vs_m2:   _vs_pct(vals[1], vals[2]),
                col_avg: fmt_fn(avg),
                vs_avg:  _vs_pct(m_proj, avg),
            })
        totals = [_total_val(p, metric) for p in periods]
        t_avg  = _nanavg(totals[1:])
        t_proj = totals[0] * mult if project else totals[0]
        rows.append({
            "Channel": "TOTAL",
            col_m:   fmt_fn(t_proj),
            col_m1:  fmt_fn(totals[1]),
            vs_m1:   _vs_pct(t_proj, totals[1]),
            col_m2:  fmt_fn(totals[2]),
            vs_m2:   _vs_pct(totals[1], totals[2]),
            col_avg: fmt_fn(t_avg),
            vs_avg:  _vs_pct(t_proj, t_avg),
        })
        df = pd.DataFrame(rows).set_index("Channel")
        return (
            df.style
            .format({c: _fmt_vs for c in all_vs})
            .map(_color_vs, subset=all_vs)
            .apply(
                lambda row: ["font-weight: bold"] * len(row) if row.name == "TOTAL" else [""] * len(row),
                axis=1,
            )
        )

    _fmt_inr_safe = lambda v: "—" if (v != v) else f"₹{v:.0f}"

    st.markdown("**MoM Units**")
    st.dataframe(_mom_table("units",  lambda v: round(v)), use_container_width=True)

    st.markdown("**MoM Orders**")
    st.dataframe(_mom_table("orders", lambda v: round(v)), use_container_width=True)

    st.markdown("**MoM Revenue**")
    st.dataframe(_mom_table("revenue", lambda v: f"₹{round(v):,}"), use_container_width=True)

    st.markdown("**MoM ASP**")
    st.dataframe(_mom_table("asp", _fmt_inr_safe, project=False), use_container_width=True)

    st.markdown("**MoM AOV**")
    st.dataframe(_mom_table("cart_size", _fmt_inr_safe, project=False), use_container_width=True)

    st.caption(
        f"⚠️ {today.strftime('%b %Y')} (proj) = month-to-date × {mult:.1f} "
        f"({max(today.day - 1, 1)} of {calendar.monthrange(today.year, today.month)[1]} days elapsed)."
    )


# ── Tab 3 — By Channel ─────────────────────────────────────────────────────────
def tab_channel(fdf: pd.DataFrame, net_mode: bool):
    st.caption("Cancelled orders are excluded from all metrics on this tab.")

    channels_avail = sorted(fdf["channel_name"].dropna().unique().tolist())
    ch_sel = st.radio("View", ["All Channels"] + channels_avail, horizontal=True)
    cdf    = fdf if ch_sel == "All Channels" else fdf[fdf["channel_name"] == ch_sel]

    # ── Performance summary ───────────────────────────────────────────────────
    st.subheader("Channel Performance")
    today      = date.today()
    cur_period = pd.Period(today, "M")

    def _period_metrics(df_sub: pd.DataFrame, p: pd.Period) -> dict:
        sub = df_sub[df_sub["month"] == p]
        g   = sub[sub["status"].isin(GROSS_STATUSES)]
        n   = sub[sub["status"].isin(NET_STATUSES)]
        return {
            "orders":    g[["order_id", "channel_id"]].drop_duplicates().shape[0],
            "units":     int(g["quantity"].sum()),
            "gross_rev": g["gross_value"].sum(),
            "net_rev":   n["gross_value"].sum(),
            "rr":        return_rate_pct(sub),
        }

    pm  = [_period_metrics(cdf, cur_period - i) for i in range(4)]
    M, M1, M2, M3 = pm
    avg = {k: (M1[k] + M2[k] + M3[k]) / 3 for k in M}

    def _fmt(key, val) -> str:
        if key == "rr":
            return f"{val:.1f}%"
        if key in ("gross_rev", "net_rev"):
            return f"₹{round(val):,}"
        return f"{round(val):,}"

    def _vs_pct_ch(m_val, prev_val):
        return (m_val - prev_val) / prev_val * 100 if prev_val else float("nan")

    def _fmt_vs_ch(v):
        return "—" if (v != v) else f"{'+'if v > 0 else ''}{v:.1f}%"

    def _fmt_bps(v):
        return "—" if (v != v) else f"{'+'if v > 0 else ''}{v:.0f} bps"

    def _color_vs_ch(v):
        if v != v:
            return ""
        return "color: green" if v > 5 else ("color: red" if v < -5 else "")

    def _color_vs_rr(v):
        # Return rate: down = good (green), up = bad (red)
        if v != v:
            return ""
        return "color: green" if v < -5 else ("color: red" if v > 5 else "")

    vs_cols_ch  = ["vs. M-1", "vs. M-2", "vs. L3M"]
    rr_label    = "Return Rate %"
    non_rr_labels = ["Orders", "Units", "Gross Revenue", "Net Revenue"]

    metric_labels = [
        ("orders",    "Orders"),
        ("units",     "Units"),
        ("gross_rev", "Gross Revenue"),
        ("net_rev",   "Net Revenue"),
        ("rr",        rr_label),
    ]
    summary_rows = []
    for key, label in metric_labels:
        if key == "rr":
            # bps = absolute difference in percentage points × 100
            vs_vals = {
                "vs. M-1": (M[key] - M1[key]) * 100,
                "vs. M-2": (M[key] - M2[key]) * 100,
                "vs. L3M": (M[key] - avg[key]) * 100,
            }
        else:
            vs_vals = {
                "vs. M-1": _vs_pct_ch(M[key], M1[key]),
                "vs. M-2": _vs_pct_ch(M[key], M2[key]),
                "vs. L3M": _vs_pct_ch(M[key], avg[key]),
            }
        summary_rows.append({
            "Metric":                label,
            f"{cur_period} (M)":     _fmt(key, M[key]),
            f"{cur_period-1} (M-1)": _fmt(key, M1[key]),
            "vs. M-1":               vs_vals["vs. M-1"],
            f"{cur_period-2} (M-2)": _fmt(key, M2[key]),
            "vs. M-2":               vs_vals["vs. M-2"],
            "L3M":                   _fmt(key, avg[key]),
            "vs. L3M":               vs_vals["vs. L3M"],
        })

    summary_df = pd.DataFrame(summary_rows).set_index("Metric")
    st.dataframe(
        summary_df.style
        .format({c: _fmt_vs_ch for c in vs_cols_ch}, subset=pd.IndexSlice[non_rr_labels, vs_cols_ch])
        .format({c: _fmt_bps   for c in vs_cols_ch}, subset=pd.IndexSlice[[rr_label],     vs_cols_ch])
        .map(_color_vs_ch, subset=pd.IndexSlice[non_rr_labels, vs_cols_ch])
        .map(_color_vs_rr, subset=pd.IndexSlice[[rr_label],     vs_cols_ch]),
        use_container_width=True,
    )

    # ── Trend — Units or Revenue, stacked, alphabetical, projected ────────────
    st.subheader("Monthly Trend")
    metric_sel = st.radio("Metric", ["Units", "Revenue"], horizontal=True, key="ch_metric")
    is_revenue = metric_sel == "Revenue"
    value_col  = "gross_value" if is_revenue else "quantity"
    y_label    = "Gross Revenue (₹ Lacs)" if is_revenue else "Units Sold"

    mult     = _cur_mult()
    cdf_plot = cdf[cdf["status"].isin(NET_STATUSES if net_mode else GROSS_STATUSES)]
    trend    = cdf_plot.groupby(["month_dt", "channel_name"])[value_col].sum().reset_index()
    trend    = _project_col(trend, value_col, mult)
    trend["Month"] = trend["month_dt"].dt.strftime("%b %Y")

    # Scale revenue to Lacs for the chart
    if is_revenue:
        trend["plot_val"] = trend[value_col] / 100_000
    else:
        trend["plot_val"] = trend[value_col]

    all_channels_in_view = sorted(cdf_plot["channel_name"].dropna().unique())

    if not trend.empty:
        trend = trend.sort_values("month_dt")
        fig = px.bar(
            trend, x="Month", y="plot_val", color="channel_name",
            barmode="stack",
            labels={"plot_val": y_label, "channel_name": "Channel"},
            color_discrete_map=CHANNEL_COLOR_MAP,
            category_orders={
                "Month":        trend["Month"].unique().tolist(),
                "channel_name": all_channels_in_view,
            },
        )
        # Totals on top of each bar
        totals = trend.groupby(["Month", "month_dt"], sort=False)["plot_val"].sum().reset_index()
        totals = totals.sort_values("month_dt")
        for _, row in totals.iterrows():
            val = row["plot_val"]
            label_text = f"₹{val:.1f}L" if is_revenue else f"{int(val):,}"
            fig.add_annotation(
                x=row["Month"], y=val,
                text=label_text,
                showarrow=False, yshift=10,
                font=dict(size=10, color="#333"),
            )
        layout_kwargs = dict(xaxis_title=None, margin=dict(t=35))
        if is_revenue:
            layout_kwargs["yaxis"] = dict(ticksuffix="L", tickformat=".0f")
        fig.update_layout(**layout_kwargs)
        if is_revenue:
            fig.update_traces(
                hovertemplate="<b>%{fullData.name}</b><br>Month: %{x}<br>Revenue: %{y:.1f}L<extra></extra>"
            )
        st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"⚠️ {today.strftime('%b %Y')} shows projected month-end "
        f"({max(today.day - 1, 1)} days elapsed, {mult:.1f}× multiplier)."
    )

    # ── Fulfillment type split ────────────────────────────────────────────────
    st.subheader("Fulfillment Type Split")
    if "fulfillment_type" in cdf_plot.columns:
        ft = cdf_plot.groupby("fulfillment_type")[["order_id"]].count().reset_index()
        ft.columns = ["Fulfillment Type", "Orders"]
        n_slices = len(ft)
        blues = [f"hsl(220, 70%, {int(30 + i * 40 / max(n_slices - 1, 1))}%)" for i in range(n_slices)]
        fig_ft = px.pie(
            ft, values="Orders", names="Fulfillment Type",
            hole=0.4, color_discrete_sequence=blues,
        )
        fig_ft.update_traces(texttemplate="%{percent:.1%}")
        fig_ft.update_layout(margin=dict(t=20))
        st.plotly_chart(fig_ft, use_container_width=True)
    else:
        st.info("Fulfillment type data not available.")


# ── Tab 4 — By SKU ─────────────────────────────────────────────────────────────
def tab_sku(fdf: pd.DataFrame, net_mode: bool):
    st.caption("Cancelled orders are excluded from all metrics on this tab.")
    adf = active_df(fdf, net_mode)

    st.subheader("SKU Performance")
    g_all = fdf[fdf["status"].isin(GROSS_STATUSES)]
    n_all = fdf[fdf["status"].isin(NET_STATUSES)]
    total_units     = int(g_all["quantity"].sum()) or 1
    total_gross_rev = g_all["gross_value"].sum() or 1
    sku_rows = []
    for sku_id, grp in fdf.groupby("sku_id"):
        g   = grp[grp["status"].isin(GROSS_STATUSES)]
        n   = grp[grp["status"].isin(NET_STATUSES)]
        asp = (n["gross_value"].sum() / n["quantity"].sum()) if n["quantity"].sum() else 0
        sku_rows.append({
            "SKU":           sku_id,
            "SKU Name":      grp["sku_name"].iloc[0],
            "Orders":        g[["order_id", "channel_id"]].drop_duplicates().shape[0],
            "Units":         int(g["quantity"].sum()),
            "Gross Revenue": f"₹{round(g['gross_value'].sum()):,}",
            "Net Revenue":   f"₹{round(n['gross_value'].sum()):,}",
            "ASP (₹)":       f"₹{asp:.0f}",
            "Return Rate %": f"{return_rate_pct(grp):.1f}%",
            "% of Units":    f"{pct(g['quantity'].sum(), total_units):.1f}%",
            "% of Revenue":  f"{pct(g['gross_value'].sum(), total_gross_rev):.1f}%",
        })

    if sku_rows:
        sku_df = pd.DataFrame(sku_rows).sort_values("Units", ascending=False).reset_index(drop=True)

        # TOTAL row computed from raw data to avoid double-counting orders
        t_asp = total_gross_rev / total_units if total_units else 0
        total_row_sku = {
            "SKU":           "TOTAL",
            "SKU Name":      "",
            "Orders":        g_all[["order_id", "channel_id"]].drop_duplicates().shape[0],
            "Units":         total_units,
            "Gross Revenue": f"₹{round(total_gross_rev):,}",
            "Net Revenue":   f"₹{round(n_all['gross_value'].sum()):,}",
            "ASP (₹)":       f"₹{t_asp:.0f}",
            "Return Rate %": f"{return_rate_pct(fdf):.1f}%",
            "% of Units":    "100.0%",
            "% of Revenue":  "100.0%",
        }
        sku_df = pd.concat([sku_df, pd.DataFrame([total_row_sku])], ignore_index=True)
        is_total = [False] * (len(sku_df) - 1) + [True]

        def _units_heatmap(col):
            max_val = max((v for flag, v in zip(is_total, col) if not flag), default=1) or 1
            return pd.Series(
                [
                    "" if flag
                    else f"background-color: rgba(30, 100, 255, {min(v / max_val, 1) * 0.6:.2f})"
                    for flag, v in zip(is_total, col)
                ],
                index=col.index,
            )

        st.dataframe(
            sku_df.style
            .apply(_units_heatmap, subset=["Units"])
            .apply(
                lambda row: ["font-weight: bold"] * len(row) if is_total[row.name] else [""] * len(row),
                axis=1,
            )
            .map(colour_rr, subset=["Return Rate %"]),
            use_container_width=True, hide_index=True,
        )

    st.subheader("SKU Comparison")
    today = date.today()
    mult  = _cur_mult()
    sku_monthly = adf.groupby(["month_dt", "sku_id", "sku_name"])["quantity"].sum().reset_index()
    if not sku_monthly.empty:
        all_sku_ids  = sorted(adf["sku_id"].dropna().unique().tolist())
        defaults     = [s for s in ["TCB004", "TCB005", "TCB006"] if s in all_sku_ids]
        # Fall back to first 3 available if defaults aren't in the data
        if len(defaults) < 3:
            defaults = all_sku_ids[:3]
        sel_skus = st.multiselect(
            "Select up to 3 SKUs to compare",
            options=all_sku_ids,
            default=defaults,
            max_selections=3,
            key="sku_compare_sel",
        )
        if sel_skus:
            sku_id_name  = dict(zip(sku_monthly["sku_id"], sku_monthly["sku_name"]))
            trend_data   = sku_monthly[sku_monthly["sku_id"].isin(sel_skus)].copy()
            trend_data   = _project_col(trend_data, "quantity", mult)
            trend_data["Series"] = trend_data["sku_id"].map(
                lambda x: f"{x} — {sku_id_name.get(x, x)}"
            )
            trend_data["Month"] = trend_data["month_dt"].dt.strftime("%b %Y")
            trend_data = trend_data.sort_values("month_dt")
            fig = px.line(
                trend_data, x="Month", y="quantity",
                color="Series", markers=True,
                labels={"quantity": "Units", "Series": "SKU"},
                category_orders={"Month": trend_data["Month"].unique().tolist()},
            )
            fig.update_layout(xaxis_title=None, margin=dict(t=20), legend_title="SKU")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Select at least one SKU above to plot the comparison.")
    st.caption(
        f"⚠️ {today.strftime('%b %Y')} shows projected month-end "
        f"({max(today.day - 1, 1)} days elapsed, {mult:.1f}× multiplier)."
    )

    # ── Theme Comparison ──────────────────────────────────────────────────────
    st.subheader("Theme Comparison")
    THEMES = {
        "Milestone Gifts":   ["TCB005", "TCB006", "TCB010"],
        "Parent Gifts":      ["TCB007", "TCB009", "TCB009_1", "TCB009_2"],
        "Premium Gifts":     ["TCB003", "TCB004", "TCB001", "TCB002"],
        "Entry Price Gifts": ["TCB008", "TCB011", "TCB012"],
    }
    theme_metric = st.radio("Metric", ["Units", "Revenue"], horizontal=True, key="theme_metric")
    theme_val_col = "quantity" if theme_metric == "Units" else "gross_value"
    theme_y_label = "Units Sold" if theme_metric == "Units" else "Gross Revenue (₹)"

    # Use full gross-status data for revenue; adf (net) for units
    theme_base = fdf[fdf["status"].isin(GROSS_STATUSES)].copy() if theme_metric == "Revenue" else adf.copy()

    theme_rows = []
    for theme_name, sku_ids in THEMES.items():
        grp = (
            theme_base[theme_base["sku_id"].isin(sku_ids)]
            .groupby("month_dt")[theme_val_col].sum()
            .reset_index()
        )
        grp["Theme"] = theme_name
        theme_rows.append(grp)

    if theme_rows:
        theme_df = pd.concat(theme_rows, ignore_index=True)
        theme_df = _project_col(theme_df, theme_val_col, mult)
        theme_df["Month"] = theme_df["month_dt"].dt.strftime("%b %Y")
        theme_df = theme_df.sort_values("month_dt")
        fig_th = px.line(
            theme_df, x="Month", y=theme_val_col,
            color="Theme", markers=True,
            labels={theme_val_col: theme_y_label, "Theme": "Theme"},
            category_orders={"Month": theme_df["Month"].unique().tolist()},
        )
        fig_th.update_layout(xaxis_title=None, margin=dict(t=20), legend_title="Theme")
        st.plotly_chart(fig_th, use_container_width=True)
    st.caption(
        f"⚠️ {today.strftime('%b %Y')} shows projected month-end "
        f"({max(today.day - 1, 1)} days elapsed, {mult:.1f}× multiplier)."
    )

    st.subheader("SKU × Channel Heatmap (Units)")
    heat = (
        adf.groupby(["sku_name", "channel_name"])["quantity"]
        .sum().unstack("channel_name").fillna(0).astype(int)
    )
    if not heat.empty:
        # Global max across all SKU/channel cells (excluding Total) for consistent shading
        global_max = int(heat.values.max()) or 1

        total_heat = heat.sum(axis=0).rename("TOTAL")
        heat = pd.concat([heat, total_heat.to_frame().T])
        heat.index.name = "SKUs"  # set after concat so name is preserved

        is_total_heat = [False] * (len(heat) - 1) + [True]

        def _global_red_excl_total(col):
            return pd.Series(
                [
                    "" if flag
                    else f"background-color: rgba(255, 100, 0, {min(v / global_max, 1) * 0.6:.2f})"
                    for flag, v in zip(is_total_heat, col)
                ],
                index=col.index,
            )

        st.dataframe(
            heat.style
            .apply(_global_red_excl_total, axis=0)
            .apply(
                lambda row: ["font-weight: bold"] * len(row) if row.name == "TOTAL" else [""] * len(row),
                axis=1,
            ),
            use_container_width=True,
        )


# ── Tab 5 — Returns ────────────────────────────────────────────────────────────
def tab_returns(raw_df: pd.DataFrame, fdf: pd.DataFrame, filters: dict = None):
    st.warning("**This tab shows ALL order statuses including Cancelled. All other tabs exclude Cancelled orders.**")

    if not raw_df.empty and not fdf.empty:
        _min_month = fdf["month_dt"].min()
        _max_month = fdf["month_dt"].max()
        all_fdf = raw_df[
            raw_df["channel_name"].isin(fdf["channel_name"].unique()) &
            raw_df["sku_id"].isin(fdf["sku_id"].unique()) &
            (raw_df["month_dt"] >= _min_month) &
            (raw_df["month_dt"] <= _max_month)
        ]
        all_fdf = _apply_city_filter(all_fdf, (filters or {}).get("cities", ["__all__"]))
    else:
        all_fdf = fdf

    # ── Status breakdown — pie + table ────────────────────────────────────────
    st.subheader("Order Status Breakdown")
    # For CANCELLED orders Amazon often sends qty=0; treat each such row as 1 unit
    _counts_df = all_fdf.copy()
    _cancelled_zero = (_counts_df["status"] == "CANCELLED") & (_counts_df["quantity"].fillna(0) <= 0)
    _counts_df.loc[_cancelled_zero, "quantity"] = 1

    status_counts = _counts_df.groupby("status").agg(
        Orders=("order_id", "count"),
        Units=("quantity", "sum"),
    ).reindex(STATUS_ORDER).dropna(how="all").fillna(0).astype(int)
    status_counts["% of Orders"] = (status_counts["Orders"] / status_counts["Orders"].sum() * 100).round(1)

    col_pie, col_tbl = st.columns([1, 1])
    with col_pie:
        fig_pie = px.pie(
            status_counts.reset_index(),
            values="Orders", names="status",
            color_discrete_sequence=px.colors.qualitative.Set2,
            hole=0.35,
        )
        fig_pie.update_traces(
            texttemplate="%{label}<br>%{percent:.1%}",
            hovertemplate="<b>%{label}</b><br>Orders: %{value:,}<br>Share: %{percent:.1%}<extra></extra>",
            textposition="inside",
            insidetextorientation="horizontal",
            pull=[0.03] * len(status_counts),
        )
        fig_pie.update_layout(
            showlegend=True,
            uniformtext_minsize=11,
            uniformtext_mode="hide",   # hide labels that are too small to fit inside — legend covers them
            margin=dict(t=20, b=20, l=20, r=20),
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_tbl:
        total_sc = pd.DataFrame(
            [{"Orders": status_counts["Orders"].sum(),
              "Units":  status_counts["Units"].sum(),
              "% of Orders": 100.0}],
            index=["TOTAL"],
        )
        sc_with_total = pd.concat([status_counts, total_sc])
        st.dataframe(
            sc_with_total.style
            .format({"% of Orders": "{:.1f}%"})
            .apply(
                lambda row: ["font-weight: bold"] * len(row) if row.name == "TOTAL" else [""] * len(row),
                axis=1,
            ),
            use_container_width=True,
        )

    def _bold_total_row(df):
        last = len(df) - 1
        return df.style.apply(
            lambda row: ["font-weight: bold"] * len(row) if row.name == last else [""] * len(row),
            axis=1,
        )

    # ── Cancellation by channel ───────────────────────────────────────────────
    st.subheader("Cancellation by Channel")
    canc_rows = []
    for ch, g in all_fdf.groupby("channel_name"):
        total     = len(g)
        cancelled = int((g["status"] == "CANCELLED").sum())
        canc_rows.append({
            "Channel":       ch,
            "Total Orders":  total,
            "Cancelled":     cancelled,
            "_sort":         pct(cancelled, total),
        })
    canc = pd.DataFrame(canc_rows).sort_values("_sort", ascending=False)
    canc["Cancel Rate %"] = canc["_sort"]  # keep numeric for heatmap
    canc = canc.drop(columns=["_sort"])
    t_orders = canc["Total Orders"].sum()
    t_canc   = canc["Cancelled"].sum()
    canc = pd.concat([canc, pd.DataFrame([{
        "Channel": "TOTAL", "Total Orders": t_orders,
        "Cancelled": t_canc, "Cancel Rate %": pct(t_canc, t_orders),
    }])], ignore_index=True)
    _is_total_canc = [False] * (len(canc) - 1) + [True]

    def _cancel_rate_bg(col):
        max_val = max((v for flag, v in zip(_is_total_canc, col) if not flag), default=1) or 1
        return pd.Series(
            ["" if flag else f"background-color: rgba(165, 55, 55, {min(v / max_val, 1) * 0.55:.2f})"
             for flag, v in zip(_is_total_canc, col)],
            index=col.index,
        )

    st.dataframe(
        _bold_total_row(canc)
        .apply(_cancel_rate_bg, subset=["Cancel Rate %"])
        .format({"Cancel Rate %": "{:.1f}%"}),
        use_container_width=True, hide_index=True,
    )

    # ── Shared return base + filters ─────────────────────────────────────────
    ret_base = all_fdf[all_fdf["status"].isin(RETURN_STATUSES)].copy()
    for _col in ("return_reason", "return_responsible", "return_customer_verbatim"):
        if _col not in ret_base.columns:
            ret_base[_col] = "Unknown"
        ret_base[_col] = ret_base[_col].fillna("Unknown")

    st.subheader("Return Rate by Channel")
    f1, f2 = st.columns(2)
    with f1:
        sel_reason = st.multiselect(
            "Filter by Reason",
            sorted(ret_base["return_reason"].unique()),
            default=[],
            key="ret_reason_filter",
        )
    with f2:
        sel_resp = st.multiselect(
            "Filter by Responsible",
            sorted(ret_base["return_responsible"].unique()),
            default=[],
            key="ret_resp_filter",
        )

    ret_filtered = ret_base.copy()
    if sel_reason:
        ret_filtered = ret_filtered[ret_filtered["return_reason"].isin(sel_reason)]
    if sel_resp:
        ret_filtered = ret_filtered[ret_filtered["return_responsible"].isin(sel_resp)]

    ret_tcb = ret_base[ret_base["return_responsible"] == "TCB"]

    if sel_reason or sel_resp:
        st.caption(
            f"Filters active — showing {len(ret_filtered):,} of {len(ret_base):,} return orders. "
            "Return Rate % uses all dispatched orders as denominator."
        )

    def _filt_rate(ch_filt, ch_ret_base, grp):
        denom = int((grp["status"] == "FULFILLED").sum()) + len(ch_ret_base)
        return pct(len(ch_filt), denom)

    def _tcb_rate(ch_tcb, ch_ret_base, grp):
        denom = int((grp["status"] == "FULFILLED").sum()) + len(ch_ret_base)
        return pct(len(ch_tcb), denom)

    # ── Return rate by channel ────────────────────────────────────────────────
    ret_rows = []
    for ch, grp in all_fdf.groupby("channel_name"):
        ch_ret  = ret_base[ret_base["channel_name"] == ch]
        ch_filt = ret_filtered[ret_filtered["channel_name"] == ch]
        ch_tcb  = ret_tcb[ret_tcb["channel_name"] == ch]
        ret_rows.append({
            "Channel":           ch,
            "Fulfilled":         int((grp["status"] == "FULFILLED").sum()),
            "RTO":               int((ch_filt["status"] == "RTO").sum()),
            "Sale Return":       int((ch_filt["status"] == "SALE_RETURN").sum()),
            "Replacement":       int((ch_filt["status"] == "REPLACEMENT").sum()),
            "Return Rate %":     _filt_rate(ch_filt, ch_ret, grp),
            "TCB Responsible Return Rate %": _tcb_rate(ch_tcb, ch_ret, grp),
        })
    ret_df = pd.DataFrame(ret_rows)
    ret_df = pd.concat([ret_df, pd.DataFrame([{
        "Channel":           "TOTAL",
        "Fulfilled":         int(ret_df["Fulfilled"].sum()),
        "RTO":               int(ret_df["RTO"].sum()),
        "Sale Return":       int(ret_df["Sale Return"].sum()),
        "Replacement":       int(ret_df["Replacement"].sum()),
        "Return Rate %":     _filt_rate(ret_filtered, ret_base, all_fdf),
        "TCB Responsible Return Rate %": _tcb_rate(ret_tcb, ret_base, all_fdf),
    }])], ignore_index=True)
    _is_total_ret = [False] * (len(ret_df) - 1) + [True]

    def _rr_bg(col, is_total_flags):
        max_val = max((v for flag, v in zip(is_total_flags, col) if not flag), default=1) or 1
        return pd.Series(
            ["" if flag else f"background-color: rgba(165, 55, 55, {min(v / max_val, 1) * 0.55:.2f})"
             for flag, v in zip(is_total_flags, col)],
            index=col.index,
        )

    st.dataframe(
        _bold_total_row(ret_df)
        .apply(_rr_bg, is_total_flags=_is_total_ret, subset=["Return Rate %", "TCB Responsible Return Rate %"])
        .format({"Return Rate %": "{:.1f}%", "TCB Responsible Return Rate %": "{:.1f}%"}),
        use_container_width=True, hide_index=True,
    )

    # ── Return rate by SKU ────────────────────────────────────────────────────
    st.subheader("Return Rate by SKU")
    ret_sku_rows = []
    for sku, grp in all_fdf.groupby("sku_id"):
        sku_ret  = ret_base[ret_base["sku_id"] == sku]
        sku_filt = ret_filtered[ret_filtered["sku_id"] == sku]
        sku_tcb  = ret_tcb[ret_tcb["sku_id"] == sku]
        ret_sku_rows.append({
            "SKU":               sku,
            "SKU Name":          grp["sku_name"].iloc[0],
            "Fulfilled":         int((grp["status"] == "FULFILLED").sum()),
            "RTO":               int((sku_filt["status"] == "RTO").sum()),
            "Sale Return":       int((sku_filt["status"] == "SALE_RETURN").sum()),
            "Replacement":       int((sku_filt["status"] == "REPLACEMENT").sum()),
            "Return Rate %":     _filt_rate(sku_filt, sku_ret, grp),
            "TCB Responsible Return Rate %": _tcb_rate(sku_tcb, sku_ret, grp),
        })
    ret_sku_df = pd.DataFrame(ret_sku_rows)
    ret_sku_df = pd.concat([ret_sku_df, pd.DataFrame([{
        "SKU":               "TOTAL",
        "SKU Name":          "",
        "Fulfilled":         int(ret_sku_df["Fulfilled"].sum()),
        "RTO":               int(ret_sku_df["RTO"].sum()),
        "Sale Return":       int(ret_sku_df["Sale Return"].sum()),
        "Replacement":       int(ret_sku_df["Replacement"].sum()),
        "Return Rate %":     _filt_rate(ret_filtered, ret_base, all_fdf),
        "TCB Responsible Return Rate %": _tcb_rate(ret_tcb, ret_base, all_fdf),
    }])], ignore_index=True)
    _is_total_ret_sku = [False] * (len(ret_sku_df) - 1) + [True]

    st.dataframe(
        _bold_total_row(ret_sku_df)
        .apply(_rr_bg, is_total_flags=_is_total_ret_sku, subset=["Return Rate %", "TCB Responsible Return Rate %"])
        .format({"Return Rate %": "{:.1f}%", "TCB Responsible Return Rate %": "{:.1f}%"}),
        use_container_width=True, hide_index=True,
    )

    # ── Return reasons ────────────────────────────────────────────────────────
    st.subheader("Return Reasons")
    rdf = ret_base.copy()
    reasons_grp = (
        rdf.groupby(["return_reason", "return_responsible"])
        .agg(Orders=("order_id", "count"), Units=("quantity", "sum"))
        .reset_index()
        .sort_values("Orders", ascending=False)
    )
    if not reasons_grp.empty:
        reasons_grp["% of Returns"] = (reasons_grp["Orders"] / reasons_grp["Orders"].sum() * 100).round(1)
        reasons_grp.columns = ["Reason", "Responsible", "Orders", "Units", "% of Returns"]
        total_reason = pd.DataFrame([{
            "Reason":         "TOTAL",
            "Responsible":    "",
            "Orders":         int(reasons_grp["Orders"].sum()),
            "Units":          int(reasons_grp["Units"].sum()),
            "% of Returns":   100.0,
        }])
        reasons_display = pd.concat([reasons_grp, total_reason], ignore_index=True)
        st.dataframe(
            _bold_total_row(reasons_display)
            .format({"% of Returns": "{:.1f}%"}),
            use_container_width=True, hide_index=True,
        )

        # Raw data download
        pid_col = "platform_order_id" if "platform_order_id" in rdf.columns else None
        raw_dl = rdf[[
            "channel_name",
            *(["platform_order_id"] if pid_col else []),
            "order_date",
            "return_reason",
            "return_responsible",
            "return_customer_verbatim",
        ]].copy()
        raw_dl.columns = [
            "Channel Name",
            *(["Order Number"] if pid_col else []),
            "Order Date",
            "Return Reason",
            "Responsible",
            "Customer Verbatim",
        ]
        st.download_button(
            "⬇ Download raw return data",
            raw_dl.to_csv(index=False),
            file_name="returns_raw.csv",
            mime="text/csv",
        )
    else:
        st.info("No return data in selected filters.")

    # ── Monthly return rate trend ─────────────────────────────────────────────
    st.subheader("Monthly Return Rate Trend")
    monthly_status = all_fdf.groupby(["month_dt", "status"])["quantity"].sum().unstack("status").fillna(0)
    for s in ALL_STATUSES:
        if s not in monthly_status.columns:
            monthly_status[s] = 0

    denom = (
        monthly_status["FULFILLED"] + monthly_status["RTO"]
        + monthly_status["SALE_RETURN"] + monthly_status["REPLACEMENT"]
    ).replace(0, pd.NA)

    monthly_status["return_rate"] = (
        (monthly_status["RTO"] + monthly_status["SALE_RETURN"] + monthly_status["REPLACEMENT"])
        / denom * 100
    ).fillna(0).round(1)
    monthly_status["rto_rate"] = (monthly_status["RTO"] / denom * 100).fillna(0).round(1)
    monthly_status["sr_rate"]  = (monthly_status["SALE_RETURN"] / denom * 100).fillna(0).round(1)

    trend_plot = monthly_status[["return_rate", "rto_rate", "sr_rate"]].reset_index()
    trend_plot = trend_plot.sort_values("month_dt")
    trend_plot["Month"] = trend_plot["month_dt"].dt.strftime("%b %Y")
    fig_rt = go.Figure()
    fig_rt.add_trace(go.Scatter(x=trend_plot["Month"], y=trend_plot["return_rate"],
                                name="Overall Return Rate %", mode="lines+markers"))
    fig_rt.add_trace(go.Scatter(x=trend_plot["Month"], y=trend_plot["rto_rate"],
                                name="RTO Rate %", mode="lines+markers", line=dict(dash="dash")))
    fig_rt.add_trace(go.Scatter(x=trend_plot["Month"], y=trend_plot["sr_rate"],
                                name="Sale Return Rate %", mode="lines+markers", line=dict(dash="dot")))
    fig_rt.update_layout(yaxis_title="Rate %", xaxis_title=None, margin=dict(t=20))
    st.plotly_chart(fig_rt, use_container_width=True)


# ── Geography tab ──────────────────────────────────────────────────────────────
def tab_geography(fdf: pd.DataFrame, net_mode: bool) -> None:
    """6th tab: city/state breakdown across channels."""

    # All non-cancelled filtered orders (apply_filters already drops CANCELLED)
    gdf = active_df(fdf, net_mode).copy()

    # In-memory normalisation (mirrors ingest/utils.py — catches any stragglers)
    _CITY_NORM  = {
        "Delhi": "New Delhi", "Bangalore": "Bengaluru",
        "Gurugram": "Gurgaon", "Bengalore": "Bengaluru", "Bangaluru": "Bengaluru",
        "Benagluru": "Bengaluru", "Bangalure": "Bengaluru", "Bengalure": "Bengaluru",
        "Vishakhapatnam": "Visakhapatnam", "Vishakhapatanam": "Visakhapatnam",
    }
    _STATE_NORM = {
        "Tamilnadu": "Tamil Nadu", "Asom": "Assam", "Asom (Assam)": "Assam",
        "Orissa": "Odisha", "Pondicherry": "Puducherry", "Uttaranchal": "Uttarakhand",
    }
    gdf["city"]  = gdf["city"].str.strip().str.title().replace(_CITY_NORM)
    gdf["state"] = gdf["state"].str.strip().str.title().replace(_STATE_NORM)

    geo = gdf[gdf["city"].notna() & gdf["state"].notna()]

    # ── Coverage callout ──────────────────────────────────────────────────────
    total_rows = len(gdf)
    geo_rows   = len(geo)
    coverage   = pct(geo_rows, total_rows)
    st.info(
        f"**{coverage:.0f}% of filtered orders ({geo_rows:,} of {total_rows:,}) "
        f"have city/state data** and are included in the charts below.  "
        f"Cancelled orders are excluded from this tab."
    )

    # ── KPI strip ─────────────────────────────────────────────────────────────
    n_cities  = geo["city"].nunique()
    n_states  = geo["state"].nunique()
    top_city  = geo.groupby("city")["quantity"].sum().idxmax()  if n_cities else "—"
    top_state = geo.groupby("state")["quantity"].sum().idxmax() if n_states else "—"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cities Reached", n_cities)
    c2.metric("States Reached", n_states)
    c3.metric("Top City",       top_city)
    c4.metric("Top State",      top_state)

    if geo.empty:
        st.info("No orders with city/state data for the selected filters.")
        return

    st.markdown("---")

    # ── Metric selector ───────────────────────────────────────────────────────
    metric = st.radio(
        "Metric", ["Units", "Orders", "Revenue"], horizontal=True, key="geo_metric"
    )
    if metric == "Units":
        value_col = "quantity"
        y_label   = "Units"
    elif metric == "Orders":
        geo = geo.copy()
        geo["_orders"] = 1
        value_col = "_orders"
        y_label   = "Orders"
    else:
        value_col = "gross_value"
        y_label   = "Revenue (₹)"

    def _bar_totals(fig, grouped_df, x_col):
        """Add totals as a text-mode scatter trace above each stacked bar."""
        totals = grouped_df.groupby(x_col)[value_col].sum().reset_index()
        totals.columns = [x_col, "_tot"]
        text_vals = [
            fmt_inr(v) if metric == "Revenue" else f"{int(v):,}"
            for v in totals["_tot"]
        ]
        fig.add_trace(go.Scatter(
            x=totals[x_col], y=totals["_tot"],
            mode="text", text=text_vals,
            textposition="top center", showlegend=False,
            textfont=dict(size=9, color="#333"),
        ))
        max_v = totals["_tot"].max() or 1
        fig.update_layout(yaxis_range=[0, max_v * 1.18])

    # ── Top Cities chart ──────────────────────────────────────────────────────
    city_ch = (
        geo.groupby(["city", "channel_name"])[value_col].sum()
        .reset_index()
    )
    top15_cities = city_ch.groupby("city")[value_col].sum().nlargest(15).index
    city_ch = city_ch[city_ch["city"].isin(top15_cities)]
    city_order = (
        city_ch.groupby("city")[value_col].sum()
        .sort_values(ascending=False).index.tolist()
    )

    st.subheader("Top Cities")
    if not city_ch.empty:
        fig_city = px.bar(
            city_ch,
            x="city", y=value_col, color="channel_name",
            barmode="stack",
            labels={value_col: y_label, "channel_name": "Channel", "city": "City"},
            color_discrete_map=CHANNEL_COLOR_MAP,
            category_orders={"city": city_order},
        )
        fig_city.update_layout(
            xaxis_title=None, margin=dict(t=30),
            xaxis=dict(tickangle=-30),
        )
        if metric == "Revenue":
            fig_city.update_layout(yaxis=dict(tickformat=",.0f", tickprefix="₹"))
        _bar_totals(fig_city, city_ch, "city")
        st.plotly_chart(fig_city, use_container_width=True)

    # ── City trend table ──────────────────────────────────────────────────────
    today = date.today()
    cur_p = pd.Period(today, "M")
    m1_p  = cur_p - 1
    m2_p  = cur_p - 2
    m3_p  = cur_p - 3
    mult  = _cur_mult()

    city_monthly = (
        geo.groupby(["city", "month"])["quantity"].sum()
        .reset_index()
        .rename(columns={"quantity": "units"})
    )

    def _period_units(period):
        sub = city_monthly[city_monthly["month"] == period]
        return sub.set_index("city")["units"]

    cm_raw = _period_units(cur_p)
    m1_u   = _period_units(m1_p)
    m2_u   = _period_units(m2_p)
    m3_u   = _period_units(m3_p)
    cm_proj = (cm_raw * mult).round(0)

    def _vs_pct(cur, ref):
        if ref and ref > 0:
            return round((cur - ref) / ref * 100, 1)
        return None

    def _fmt_vs(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "—"
        return f"+{v:.1f}%" if v >= 0 else f"{v:.1f}%"

    def _color_vs(val):
        if not isinstance(val, str) or val == "—":
            return ""
        try:
            v = float(val.replace("%", "").replace("+", ""))
            if v > 5:
                return "color: green; font-weight: bold"
            if v < -5:
                return "color: red; font-weight: bold"
        except ValueError:
            pass
        return ""

    cm_col = f"CM ({today.strftime('%b')})"
    tbl_rows = []
    for city in sorted(geo["city"].unique()):
        cm_v  = float(cm_proj.get(city, 0) or 0)
        m1_v  = float(m1_u.get(city, 0) or 0)
        m2_v  = float(m2_u.get(city, 0) or 0)
        m3_v  = float(m3_u.get(city, 0) or 0)
        l3m_v = (m1_v + m2_v + m3_v) / 3
        tbl_rows.append({
            "City":      city,
            cm_col:      int(cm_v),
            "M-1":       int(m1_v),
            "vs. M-1":   _fmt_vs(_vs_pct(cm_v, m1_v)),
            "M-2":       int(m2_v),
            "vs. M-2":   _fmt_vs(_vs_pct(cm_v, m2_v)),
            "L3M Avg":   round(l3m_v, 1),
            "vs. L3M":   _fmt_vs(_vs_pct(cm_v, l3m_v)),
        })

    city_tbl = pd.DataFrame(tbl_rows).sort_values(cm_col, ascending=False)
    vs_cols  = ["vs. M-1", "vs. M-2", "vs. L3M"]
    st.caption(f"Units only. {cm_col} projected to full month.")
    st.dataframe(
        city_tbl.style.map(_color_vs, subset=vs_cols),
        use_container_width=True,
        height=350,
        hide_index=True,
    )

    # ── Top States chart ───────────────────────────────────────────────────────
    state_ch = (
        geo.groupby(["state", "channel_name"])[value_col].sum()
        .reset_index()
    )
    state_order = (
        state_ch.groupby("state")[value_col].sum()
        .sort_values(ascending=False).index.tolist()
    )

    st.subheader("Top States")
    if not state_ch.empty:
        fig_state = px.bar(
            state_ch,
            x="state", y=value_col, color="channel_name",
            barmode="stack",
            labels={value_col: y_label, "channel_name": "Channel", "state": "State"},
            color_discrete_map=CHANNEL_COLOR_MAP,
            category_orders={"state": state_order},
        )
        fig_state.update_layout(
            xaxis_title=None, margin=dict(t=30),
            xaxis=dict(tickangle=-40),
            height=450,
        )
        if metric == "Revenue":
            fig_state.update_layout(yaxis=dict(tickformat=",.0f", tickprefix="₹"))
        _bar_totals(fig_state, state_ch, "state")
        st.plotly_chart(fig_state, use_container_width=True)

    # ── Blinkit — City Performance ────────────────────────────────────────────
    blinkit_geo = geo[geo["channel_name"] == "Blinkit"]
    if not blinkit_geo.empty:
        st.markdown("---")
        st.subheader("Blinkit — City Performance")

        col_left, col_right = st.columns([1, 2])

        with col_left:
            bk_city = (
                blinkit_geo.groupby("city")
                .agg(
                    Orders=("order_id", "count"),
                    Units=("quantity", "sum"),
                    Revenue=("gross_value", "sum"),
                )
                .reset_index()
                .sort_values("Units", ascending=False)
            )
            bk_city["Revenue"] = bk_city["Revenue"].apply(fmt_inr)
            total_row = pd.DataFrame([{
                "city":    "TOTAL",
                "Orders":  bk_city["Orders"].sum(),
                "Units":   bk_city["Units"].sum(),
                "Revenue": fmt_inr(blinkit_geo["gross_value"].sum()),
            }])
            bk_display = pd.concat([bk_city, total_row], ignore_index=True).rename(columns={"city": "City"})

            def _bold_blinkit_total(styler):
                n = len(styler.data)
                return styler.set_properties(
                    subset=pd.IndexSlice[n - 1, :],
                    **{"font-weight": "bold", "border-top": "1px solid #ccc"},
                )

            st.dataframe(
                _bold_blinkit_total(bk_display.style),
                use_container_width=True,
                hide_index=True,
            )

        with col_right:
            bk_trend = (
                blinkit_geo.groupby(["month_dt", "city"])["quantity"].sum()
                .reset_index()
            )
            bk_trend["Month"] = bk_trend["month_dt"].dt.strftime("%b %Y")
            bk_trend = _project_col(bk_trend, "quantity", _cur_mult())
            month_order = bk_trend.sort_values("month_dt")["Month"].unique().tolist()

            all_bk_cities = sorted(blinkit_geo["city"].unique().tolist())
            sel_bk_cities = st.multiselect(
                "Cities to show",
                options=all_bk_cities,
                default=all_bk_cities,
                key="bk_city_sel",
            )
            bk_plot = bk_trend[bk_trend["city"].isin(sel_bk_cities)] if sel_bk_cities else bk_trend

            fig_bk = px.line(
                bk_plot,
                x="Month", y="quantity", color="city",
                markers=True,
                labels={"quantity": "Units", "city": "City"},
                category_orders={"Month": month_order},
            )
            fig_bk.update_layout(
                xaxis_title=None, yaxis_title="Units",
                margin=dict(t=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.caption("Monthly units — current month projected to full month")
            st.plotly_chart(fig_bk, use_container_width=True)


# ── Auth gate ──────────────────────────────────────────────────────────────────
def _require_auth() -> None:
    """Password gate for public deployment. No-op if APP_PASSWORD secret is not set."""
    try:
        pwd_secret = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        return  # secrets not configured — local dev, skip gate

    if not pwd_secret:
        return  # secret present but empty — treat as disabled

    if st.session_state.get("_auth_ok"):
        return

    st.markdown("## Growth Spurt Dashboard")
    pwd = st.text_input("Password", type="password", key="_pwd")
    if st.button("Enter"):
        if pwd == pwd_secret:
            st.session_state["_auth_ok"] = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    _require_auth()

    import base64
    logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as _f:
            logo_b64 = base64.b64encode(_f.read()).decode()
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                <img src="data:image/png;base64,{logo_b64}" width="70"/>
                <h2 style="margin:0;padding:0;">Growth Spurt Dashboard</h2>
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("## Growth Spurt Dashboard")

    raw_df = load_data()
    if raw_df.empty:
        st.warning("No orders data found. Run an ingest script first.")
        return

    filters = sidebar(raw_df)
    fdf     = apply_filters(raw_df, filters)

    if fdf.empty:
        st.info("No data for the selected filters.")
        return

    t1, t2, t3, t4, t5, t6 = st.tabs([
        "📊 Overview", "📈 Trends", "🏪 By Channel", "📦 By SKU", "🔄 Returns", "🗺️ Geography",
    ])
    with t1:
        tab_overview(raw_df, fdf, filters["net_mode"], filters)
    with t2:
        tab_trends(fdf, filters["net_mode"])
    with t3:
        tab_channel(fdf, filters["net_mode"])
    with t4:
        tab_sku(fdf, filters["net_mode"])
    with t5:
        tab_returns(raw_df, fdf, filters)
    with t6:
        tab_geography(fdf, filters["net_mode"])


if __name__ == "__main__":
    main()
