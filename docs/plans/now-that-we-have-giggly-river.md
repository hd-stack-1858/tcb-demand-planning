# Sales MIS Dashboard — Phase C

## Context

All channel ingest scripts (Amazon, Blinkit, FnP, FirstCry, Peeko) are now live and the `orders` table is populated with real data. Phase C builds the read-only analytics dashboard (`ui/growthspurt_app.py`) on top of this data. The dashboard surfaces what the CLI scripts can't: trend visibility, cross-channel comparison, status splits, and month projections — all in one browser-accessible view. Auth is handled by Streamlit Cloud's built-in viewer allowlist (zero code).

---

## Critical Schema Facts (inform every query)

| Fact | Impact on dashboard |
|------|---------------------|
| `net_margin`, `commission_amt`, `logistics_cost`, `ad_spend_allocated` — NOT populated by any ingest script | Excluded entirely — COGS/margin analysis is deferred to P&L MIS phase |
| `return_reason` — populated only for Amazon and FirstCry | Show for those channels; all others label "Reason not known" |
| Statuses: `FULFILLED`, `PENDING`, `CANCELLED`, `RTO`, `SALE_RETURN`, `REPLACEMENT` | Dashboard must handle all 6; REPLACEMENT added in migration 21 |
| `v_monthly_mis` excludes CANCELLED orders and doesn't aggregate by status | Query `orders` table directly for all analysis |
| `order_id` is not globally unique — PK is `(order_id, channel_id)` | Always use both in deduplication |

---

## Core Metric Definitions (consistent across all tabs)

| Metric | Definition |
|--------|------------|
| **Gross Revenue** | `SUM(gross_value)` for all statuses **except CANCELLED** |
| **Net Revenue** | `SUM(gross_value)` for `FULFILLED + REPLACEMENT` only |
| **Units (Gross)** | `SUM(quantity)` for all statuses **except CANCELLED** |
| **Units (Net)** | `SUM(quantity)` for `FULFILLED + REPLACEMENT` only |
| **Orders (Gross)** | count of distinct orders, all statuses **except CANCELLED** |
| **Return Rate %** | `(RTO + SALE_RETURN + REPLACEMENT) / (FULFILLED + RTO + SALE_RETURN + REPLACEMENT)` |
| **ASP** | `gross_value / quantity` — computed only on FULFILLED + REPLACEMENT rows to avoid 0-value distortion |

**Default everywhere:** Gross view (excludes Cancelled). A **"Gross / Net" toggle** in the sidebar switches all tabs to Net view simultaneously. Cancelled orders appear **only** in the Status Analysis tab (Tab 5) and are clearly labelled.

Callout banner shown on all tabs: _"Cancelled orders are excluded from all metrics on this tab."_

---

## Files to Create / Modify

| File | Action |
|------|--------|
| `ui/growthspurt_app.py` | **Create** — main dashboard (entire Phase C) |
| `tcb/db.py` | **Modify** — add `get_orders_raw()` helper for MIS queries |
| `.streamlit/secrets.toml` | **Create** (if not exists) — placeholder; actual secrets set in Streamlit Cloud |

---

## Dashboard Architecture

### Data Layer

Add one function to `tcb/db.py`:

```python
def get_orders_raw(start_date: str | None = None, end_date: str | None = None) -> list[dict]:
    """Fetch all orders with channel + sku name joins for MIS dashboard."""
    q = get_client().table("orders").select(
        "order_id, channel_id, order_date, sku_id, quantity, mrp, "
        "selling_price, gross_value, discount_pct, cogs, "
        "city, state, status, return_date, return_reason, source_file, "
        "channels(name, code), skus(name)"
    )
    if start_date:
        q = q.gte("order_date", start_date)
    if end_date:
        q = q.lte("order_date", end_date)
    return q.execute().data
```

All aggregation happens in pandas after this fetch. Cache with `@st.cache_data(ttl=300)`.

### Auth (zero code)

Streamlit Cloud → App Settings → Viewers → add allowed emails. No code change needed.

### UI Structure

**Layout:** wide mode on desktop; all components use `st.columns` with responsive stacking. No fixed pixel widths — Streamlit's fluid layout renders acceptably on mobile browsers.

**Global Sidebar Filters** (apply to all tabs):
- Date range: month-picker (default = all available data)
- Channel: multi-select with **"All Channels"** as first option (default = All)
- SKU: multi-select with **"All SKUs"** as first option (default = All)
- **Gross / Net Revenue toggle** (default = Gross): switches all tabs simultaneously

Note: Status filter is NOT in sidebar — status filtering is handled per-tab only (Tab 5 shows all; other tabs always exclude Cancelled).

**5 Tabs:**

---

#### Tab 1 — 📊 Overview

KPI row (5 metric cards — responsive, stack to 2-3 per row on mobile):
- **Total Orders** (Gross: excl. Cancelled)
- **Total Units** (Gross: excl. Cancelled)
- **Gross Revenue ₹** (all statuses excl. Cancelled)
- **Net Revenue ₹** (FULFILLED + REPLACEMENT only)
- **Return Rate %** = (RTO + SALE_RETURN + REPLACEMENT) / (FULFILLED + RTO + SALE_RETURN + REPLACEMENT)

All 5 cards respect the sidebar Gross/Net toggle for orders/units (revenue cards are always both Gross and Net shown side by side).

Current Month Projection box (always uses full unfiltered data for current month):
- Formula: `projected = actual_mtd_units * (days_in_month / days_elapsed_today)`
- Display: _"May 2026: X units so far (11 days of 31) → ~Z projected by month-end"_
- Uses FULFILLED + REPLACEMENT only for projection (conservative)
- Show projected Gross Revenue alongside: `projected_units × last_3_month_avg_sp`

Two charts side-by-side (stack vertically on mobile):
- Left: Monthly gross revenue bar chart (stacked by channel, x=month, last 6 months)
- Right: Revenue share donut by channel (for filtered period)

Summary pivot table:
- Rows = channels, Cols = last 6 months + "Total", Values = units sold
- Color-code cells by volume (light → dark heatmap)
- % share of total shown in each cell

---

#### Tab 2 — 📈 Trends

Trendline chart (dual axis):
- Primary y-axis: Units sold per month (line, by channel)
- Secondary y-axis: Orders count per month (line, dashed)
- x-axis: month
- Filters apply; toggle channel visibility in legend

MoM comparison table (3 comparisons, always shown for the current/selected month M):
| Column | Definition |
|--------|-----------|
| M | Current month (or latest complete month if mid-month) |
| M-1 | Previous month |
| M-2 | Two months ago |
| Avg (M-1, M-2, M-3) | Rolling 3-month average |
| vs M-1 Δ% | `(M - M-1) / M-1 × 100` |
| vs M-2 Δ% | `(M - M-2) / M-2 × 100` |
| vs 3M avg Δ% | `(M - avg) / avg × 100` |

- Applied to: Units, Orders, Gross Revenue — shown as 3 sub-tables or one wide table with grouped headers
- Sort by `vs M-1 Δ%` descending (shows biggest movers)
- Green = positive, red = negative Δ%

Quarter selector widget:
- Dropdown: Q1 (Jan-Mar), Q2 (Apr-Jun), Q3 (Jul-Sep), Q4 (Oct-Dec)
- When selected → show 3-month grouped bar chart side by side for each channel
- Show quarter total and % of year-to-date

---

#### Tab 3 — 🏪 By Channel

Channel selector (radio buttons at top): "All Channels" + one per channel

Per-channel metrics table (for selected channel or all):
- Month | Orders | Units | Gross Revenue | Net Revenue | ASP | Return Rate % | % of Total Revenue

All revenue/unit columns = Gross by default (respects sidebar toggle).
% of Total Revenue = this channel's revenue / all-channel revenue for that month.

Channel trend chart:
- Monthly units bar chart, one color per channel (stacked or grouped toggle)

Fulfillment type breakdown:
- Pie/donut chart: SOR / DROP_SHIP / OUTRIGHT / DIRECT split of orders by %

---

#### Tab 4 — 📦 By SKU

SKU performance table (sortable by any column):
- SKU ID | SKU Name | Orders | Units | Gross Revenue | Net Revenue | ASP | Return Rate % | % of Total Units
- Default sort: units descending
- Color-code Return Rate: green (<5%), yellow (5-15%), red (>15%)
- % of Total Units = this SKU's units / total units across all SKUs

SKU trend chart:
- Multi-line: top 5 SKUs by units, monthly trend
- Remaining SKUs shown as "Others" aggregate line (toggle)

Cross-tab: SKU × Channel heatmap
- Rows = SKUs, Cols = channels, Values = units sold (color intensity)
- Shows which SKUs sell on which channels and relative concentration

---

#### Tab 5 — 🔄 Returns & Status

**This is the only tab that includes CANCELLED orders.** A bold callout at the top says: _"This tab shows ALL order statuses including Cancelled. All other tabs exclude Cancelled orders."_

Status breakdown (full picture, **no filters applied** — always whole dataset):
- Horizontal bar chart: count and % for each status
- Order: FULFILLED → REPLACEMENT → PENDING → RTO → SALE_RETURN → CANCELLED
- Show: N orders + % of total for each bar

Cancellation analysis box:
- Cancelled as % of total orders placed (incl. Cancelled)
- By channel: which channels have highest cancellation rate

Return rate metrics table:
- Columns: Channel | Total Placed | Fulfilled | RTO | Sale Return | Replacement | Return Rate %
- Return Rate = (RTO + SALE_RETURN + REPLACEMENT) / (FULFILLED + RTO + SALE_RETURN + REPLACEMENT)
- Second table same structure but by SKU

Return reasons table:
- `return_reason` values grouped + counted, filtered to Amazon + FirstCry only
- All other channels show "Reason not known" as one grouped row
- Note: _"Return reason data available for Amazon and FirstCry only"_

Monthly return trend:
- Line chart: return rate % per month (RTO + SALE_RETURN + REPLACEMENT) / total fulfilled+returns
- Separate lines for RTO rate and SALE_RETURN rate

---

## Implementation Steps

1. **Add `get_orders_raw()` to `tcb/db.py`** — pure read, no side effects

2. **Create `ui/growthspurt_app.py`** with this structure:
   ```
   st.set_page_config(layout="wide")
   load_data() → cached pandas DataFrame (orders + channel name + sku name)
   sidebar_filters() → returns filter state dict
   apply_filters(df, filters) → filtered df
   
   tab1, tab2, tab3, tab4, tab5 = st.tabs([...])
   with tab1: render_overview(df, filtered_df)
   with tab2: render_trends(filtered_df)
   with tab3: render_by_channel(filtered_df)
   with tab4: render_by_sku(filtered_df)
   with tab5: render_returns(filtered_df)
   ```

3. **Libraries to use:**
   - `plotly.express` and `plotly.graph_objects` for all charts (already used in project or easy to add)
   - `pandas` for all aggregation
   - No new heavy dependencies

4. **Create `.streamlit/secrets.toml`** with placeholder comment only (real values set in Streamlit Cloud env)

5. **Auth setup (manual, no code):** After deploy, go to Streamlit Cloud → App → Settings → Viewers → add email addresses

---

## Projection Formula (Tab 1)

```python
from datetime import date
import calendar

today = date.today()
days_elapsed = today.day
days_in_month = calendar.monthrange(today.year, today.month)[1]

# Use unfiltered full dataset for projection (always shows true current month)
current_month_orders = df[
    (df["order_date"].dt.year == today.year) &
    (df["order_date"].dt.month == today.month) &
    (df["status"].isin(["FULFILLED", "REPLACEMENT"]))
]
actual_units = current_month_orders["quantity"].sum()
actual_revenue = current_month_orders["gross_value"].sum()
multiplier = days_in_month / days_elapsed

projected_units = round(actual_units * multiplier)
projected_revenue = round(actual_revenue * multiplier)
```

---

## Verification

After implementation:

1. Run `streamlit run ui/growthspurt_app.py` locally with `TCB_ENV=prod` — confirm app loads without errors
2. Verify KPI cards show non-zero values matching known data
3. Check status breakdown includes REPLACEMENT rows (added in migration 21)
4. Verify current month projection shows today=May 11, 31-day month, correct multiplier (31/11 ≈ 2.82x)
5. Confirm sidebar filters propagate to all 5 tabs
6. Verify return reasons column shows "N/A" for unpopulated rows, not an error
7. Check that orders with `status=CANCELLED` appear in Tab 5 counts but are NOT included in revenue totals on Tab 1
