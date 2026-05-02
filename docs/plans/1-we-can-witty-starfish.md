# Phase B1 — Blinkit Sell-out Ingestion + Daily Automation

## Context

Phase A wired up drop-ship sales capture. Phase B1 closes the loop for Blinkit — our largest channel (~62% gross sales) — which has zero data in the orders table today.

Orders table stays **simple** — core financial data only. P&L enrichment (commission, logistics, TCS, settlement) is a separate future layer, standardised across platforms.

The ingestion is **automated**: `load_blinkit_sales.py` supports a `--folder` mode that processes all files in the sales folder idempotently. Combined with Windows Task Scheduler, it runs daily after Himanshu drops the MTD file.

Historical data sources:
- **Daily sales files** (Jan–Apr 2026): `blinkit_reports/sales/` — 1,076 DELIVERED orders
- **Payout sheets** (Dec 2025–Mar 2026): `blinkit_reports/payout sheets/payout_sheet_{month}/` — provides Dec 2025 data + marks returns/cancellations
- **No Dec 2025 daily sales file** — payout sheet Forward Orders tab (41 rows) is the source

---

## What Already Exists (reuse)

| Item | Location | Use |
|------|----------|-----|
| `tcb/db.py` `get_client()` | `tcb/db.py` | All DB access |
| `channels` table | channel_id=4, code='BLK' | FK for all Blinkit orders |
| `sku_channel_ids` | `platform_item_id`, `platform_upc` | Blinkit Item ID → sku_id |
| `item_batches` | `received_date`, `cost_per_unit` | Historical COGS by date |
| `bom` | `item_id`, `quantity_per_sku` | COGS BOM lookup |
| `orders` table | core columns, no migration needed | Target for all Blinkit sales |
| `tests/conftest.py` | sets `TCB_ENV=dev` | Test isolation |

**Note:** `sku_channel_ids` is empty in dev but fully populated in prod. Dev needs seeding before tests run.

---

## Blinkit File Formats

### Daily sales report (same for MTD and monthly files)
`blinkit_reports/sales/sales-report-*.xlsx`, sheet "Sales Report", header row 1, data row 2.

Columns used: Order Id, Order Date, Item Id, UPC, Quantity (always 1 in our data), MRP (Rs), Selling Price (Rs), Total Gross Bill Amount, Customer City, Customer State.

### Payout sheet — Forward Orders tab
`blinkit_reports/payout sheets/payout_sheet_{YYYY-MM}/Forward & Return Cancelled Orders.xlsx`,
sheet "Forward Orders", header row 5, data row 7.

Has same core order data as daily file PLUS Invoice ID. Core columns used: Invoice ID, Order ID, Order Date, Item ID, Quantity, MRP (Rs), Selling Price (Rs), Total Gross Bill Amount, Customer City, Customer State.

### Payout sheet — Cancelled or Returned Orders tab
Same file, sheet "Cancelled or Returned Orders", header row 5, data row 7.

Columns used: **Forward Invoice ID** (links back to Forward Orders.Invoice ID → Order ID), Return Order ID, Return Order Date, Item ID.

Linking chain: `Forward Invoice ID` → `Forward Orders.Invoice ID` → `Forward Orders.Order ID` = our `platform_order_id`.

---

## SKU Mapping

| Blinkit Item ID | UPC | SKU ID |
|---|---|---|
| 10271993 | 8904492301572 | TCB001 |
| 10271630 | 8904492390002 | TCB002 |
| 10272608 | 8904492390040 | TCB003 |
| 10272017 | 8904492390019 | TCB004 |
| 10272641 | 8904492390057 | TCB005 |
| 10272588 | 8904492390064 | TCB006 |
| 10273430 | 8904492390026 | TCB008 |
| 10274008 | 8904492390071 | **TCB009** (before 2026-03-01) / **TCB009_1** (from 2026-03-01) |
| 10285562 | 21449631 | TCB010 |
| 10282817 | 21449585 | TCB011 |
| 10282820 | 21449608 | TCB012 |

---

## No Schema Migration Needed

Orders table is used as-is. The columns needed (order_id, channel_id, order_date, sku_id, quantity, mrp, selling_price, gross_value, city, state, cogs, fulfillment_type, status, platform_order_id, return_date, source_file, partner_location_id) all exist.

Only setup needed: dev DB seed for `sku_channel_ids`.

---

## New Files

### `setup/seed_blinkit_sku_channel_ids.sql`
Seeds dev DB (prod already has these):

```sql
INSERT INTO sku_channel_ids (sku_id, channel_code, platform_pid, platform_item_id, platform_upc)
VALUES
  ('TCB001',   'BLINKIT', '729524', '10271993', '8904492301572'),
  ('TCB002',   'BLINKIT', '728981', '10271630', '8904492390002'),
  ('TCB003',   'BLINKIT', '730250', '10272608', '8904492390040'),
  ('TCB004',   'BLINKIT', '729548', '10272017', '8904492390019'),
  ('TCB005',   'BLINKIT', '730293', '10272641', '8904492390057'),
  ('TCB006',   'BLINKIT', '730230', '10272588', '8904492390064'),
  ('TCB008',   'BLINKIT', '731714', '10273430', '8904492390026'),
  ('TCB009',   'BLINKIT', '732471', '10274008', '8904492390071'),
  ('TCB009_1', 'BLINKIT', '732471', '10274008', '8904492390071'),
  ('TCB010',   'BLINKIT', '749746', '10285562', '21449631'),
  ('TCB011',   'BLINKIT', '745246', '10282817', '21449585'),
  ('TCB012',   'BLINKIT', '745249', '10282820', '21449608')
ON CONFLICT (sku_id, channel_code) DO NOTHING;
```

---

### `ingest/utils.py`

```python
def get_sku_cogs_at_date(sku_id: str, as_of_date: date) -> float | None:
    """
    BOM × cost of most-recent batch per item received on or before as_of_date.
    In-process LRU cache keyed on (sku_id, as_of_date) — safe for bulk loads.
    Returns None if BOM is empty or no prior batch exists for any BOM item.
    """

def resolve_blinkit_sku(blinkit_item_id: int, order_date: date) -> str | None:
    """
    Looks up sku_id from sku_channel_ids where channel_code='BLINKIT'
    and platform_item_id = str(blinkit_item_id).
    Special case: item 10274008 → TCB009 if order_date < 2026-03-01, else TCB009_1.
    Returns None (logs warning) if item_id not found.
    """
```

---

### `ingest/load_blinkit_sales.py`

Handles daily MTD files and full monthly files (same format). Two modes:

```
# Single file
python ingest/load_blinkit_sales.py --file <path.xlsx> [--env dev|prod] [--dry-run]

# Folder mode (all .xlsx in folder — safe to re-run, already-loaded rows produce 0 new inserts)
python ingest/load_blinkit_sales.py --folder <path> [--env dev|prod] [--dry-run]
```

Per row:
- `order_id` = `BLK-{Order Id}`
- `platform_order_id` = str(Order Id)
- `channel_id` = 4
- `sku_id` = `resolve_blinkit_sku(Item Id, Order Date)` — skip row (warn) if None
- `cogs` = `get_sku_cogs_at_date(sku_id, order_date)` — NULL if no prior batch
- `city` = Customer City, `state` = Customer State
- `selling_price` = Selling Price (Rs), `mrp` = MRP (Rs)
- `gross_value` = Total Gross Bill Amount
- `quantity` = Quantity column
- `fulfillment_type` = 'SOR', `status` = 'FULFILLED'
- `source_file` = filename (basename only)

Upsert on `(order_id, channel_id)`. Existing rows not overwritten — idempotent.

Print per file: `{filename}: {N} new | {M} duplicate | {K} skipped (unknown SKU)`

---

### `ingest/load_blinkit_payout.py`

Processes one monthly payout folder. Handles Dec '25 (no daily file) and subsequent months.

```
python ingest/load_blinkit_payout.py --folder <payout_sheet_YYYY-MM path> [--env dev|prod] [--dry-run]
```

**Pass 1 — Forward Orders tab** (header row 5, data row 7):
Build in-memory dict: `{invoice_id: BLK-{Order Id}}` for use in Pass 2.
For each row: upsert order using same core fields as `load_blinkit_sales.py`. Rows that already exist (loaded via daily file) are NOT overwritten. New rows (e.g., Dec '25) ARE inserted.

**Pass 2 — Cancelled or Returned Orders tab** (header row 5, data row 7):
For each row: look up `Forward Invoice ID` in Pass 1's in-memory dict → get `order_id`. Update: `status = 'SALE_RETURN'`, `return_date = Return Order Date`. If no matching order found (data gap), insert new row with `status = 'SALE_RETURN'`.

Print: `Forward Orders: {N} new | {M} enriched | Returns: {R} marked`

---

### `scripts/fetch_blinkit_sales.py` (Playwright download bot)

Manually triggered by Himanshu. Opens a visible browser (so he can handle OTP/login), navigates to the Blinkit seller portal, downloads the current MTD sales report, saves it to `blinkit_reports/sales/`, then automatically runs `load_blinkit_sales.py` on the downloaded file.

```
python scripts/fetch_blinkit_sales.py [--env dev|prod]
```

Design:
- **Playwright in headed mode** — browser window visible; Himanshu completes login/OTP manually
- **Session persistence** — saves auth cookies to `.playwright_session/blinkit.json` (gitignored) after first login; reuses on subsequent runs if session is still valid
- **Download flow**: navigate to Reports → Sales Report → MTD → click Download → wait for file → save to `blinkit_reports/sales/` with today's date in filename
- **Auto-load**: on successful download, calls `load_blinkit_sales.py --file <downloaded_file> --env {env}`
- **Credentials**: `BLINKIT_EMAIL` and `BLINKIT_PASSWORD` in `.env` / `.env.dev` (never committed)

Exact navigation selectors to be mapped against the live portal during build.

Create `logs/` directory and add `logs/*.log`, `.playwright_session/` to `.gitignore`.

Add `playwright` to `requirements.txt`.

---

## Historical Load Sequence

```bash
# 1. Seed dev sku_channel_ids (one-time)
TCB_ENV=dev python -c "from tcb.db import get_client; ..."  # or via Supabase SQL editor

# 2. Load daily sales files (Jan–Apr '26)
python ingest/load_blinkit_sales.py --folder blinkit_reports/sales --env prod

# 3. Load payout sheets (creates Dec '25 + marks all returns)
python ingest/load_blinkit_payout.py --folder "blinkit_reports/payout sheets/payout_sheet_2025-12" --env prod
python ingest/load_blinkit_payout.py --folder "blinkit_reports/payout sheets/payout_sheet_2026-01" --env prod
python ingest/load_blinkit_payout.py --folder "blinkit_reports/payout sheets/payout_sheet_2026-02" --env prod
python ingest/load_blinkit_payout.py --folder "blinkit_reports/payout sheets/payout_sheet_2026-03" --env prod
# Apr '26 payout: run when available
```

---

## Tests — `tests/test_phase_b.py`

Pre-condition: dev sku_channel_ids seeded, no migration needed.

| Test | What it checks |
|------|---------------|
| `test_cogs_at_date_known_sku` | TCB005 COGS at 2026-01-15 = BOM × batches active at that date |
| `test_cogs_at_date_no_prior_batch` | Returns None when no batch precedes given date |
| `test_resolve_sku_tcb009_feb` | item 10274008, 2026-02-15 → TCB009 |
| `test_resolve_sku_tcb009_1_mar` | item 10274008, 2026-03-01 → TCB009_1 |
| `test_resolve_sku_unknown` | Returns None, no exception |
| `test_sales_dry_run` | Parses Jan file, builds row dicts, no DB write, no errors |
| `test_sales_inserts` | Loads Jan file → 173 rows in dev orders for channel_id=4 |
| `test_sales_idempotent` | Load Jan file twice → still 173 rows |
| `test_payout_creates_dec_orders` | Load Dec '25 payout → dev orders has Dec '25 rows |
| `test_payout_marks_returns` | Load Mar '26 payout → orders with status='SALE_RETURN' count matches |

---

## Verification Checklist

```
[ ] Dev sku_channel_ids seeded:
    TCB_ENV=dev python -c "from tcb.db import get_client as g; print(g().table('sku_channel_ids').select('*').eq('channel_code','BLINKIT').execute().data)"
    → 12 rows

[ ] Load all daily sales to dev:
    TCB_ENV=dev python ingest/load_blinkit_sales.py --folder blinkit_reports/sales
    → total 1076 new rows

[ ] Re-run: → 0 new, 1076 duplicate (idempotency confirmed)

[ ] Load Dec '25 payout to dev:
    TCB_ENV=dev python ingest/load_blinkit_payout.py --folder "blinkit_reports/payout sheets/payout_sheet_2025-12"
    → 41 new rows for Dec '25

[ ] Load Mar '26 payout to dev:
    TCB_ENV=dev python ingest/load_blinkit_payout.py --folder "blinkit_reports/payout sheets/payout_sheet_2026-03"
    → 12 orders updated to SALE_RETURN

[ ] Spot-check TCB009_1 cutoff:
    SELECT sku_id, order_date FROM orders WHERE channel_id=4 AND order_date >= '2026-03-01' LIMIT 5
    → sku_id = TCB009_1

[ ] pytest tests/test_phase_b.py → all pass

[ ] /simplify then /review before committing

[ ] Load all historical data to PROD:
    SELECT count(*), min(order_date), max(order_date) FROM orders WHERE channel_id=4
    → ~1117 rows (1076 daily + 41 Dec '25), Dec 2025 – Apr 2026

[ ] Verify returns on PROD:
    SELECT count(*) FROM orders WHERE channel_id=4 AND status='SALE_RETURN'
```

---

## Phase B2 (next leg)

After B1 ships:
- `ingest/load_blinkit_inventory.py` → `partner_soh_snapshots` table (warehouse SOH per SKU)
- `ingest/load_blinkit_performance.py` → `blinkit_darkstore_performance` table (WH→darkstore mapping, availability %, velocity per darkstore)
- New migration for those two tables
- Combined analysis: SKU × WH × darkstore_count × velocity → replenishment signal

---

## Build Order

1. Write `setup/seed_blinkit_sku_channel_ids.sql` → apply to dev
2. Write `ingest/utils.py` (COGS + SKU map helpers)
3. Write `ingest/load_blinkit_sales.py` (single file + folder mode)
4. Write `ingest/load_blinkit_payout.py` (forward orders + returns)
5. Write `tests/test_phase_b.py` — run against dev; all pass
6. Run verification checklist on dev
7. Load all historical data to prod
8. Write `scripts/fetch_blinkit_sales.py` (Playwright download + auto-load)
   — test against live Blinkit portal; map exact selectors during build
