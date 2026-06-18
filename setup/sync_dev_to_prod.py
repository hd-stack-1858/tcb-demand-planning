#!/usr/bin/env python3
"""
setup/sync_dev_to_prod.py

One-shot dev DB sync: brings the dev Supabase project to the same schema + master
data as prod.  Safe to re-run — uses IF EXISTS / ON CONFLICT DO NOTHING throughout.

Usage:
    python setup/sync_dev_to_prod.py            # apply all changes
    python setup/sync_dev_to_prod.py --dry-run  # show plan, no writes
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from dotenv import dotenv_values
import psycopg2
from psycopg2.extras import execute_values
from supabase import create_client

ROOT        = Path(__file__).parent.parent
PROD_CFG    = dotenv_values(ROOT / ".env")
DEV_CFG     = dotenv_values(ROOT / ".env.dev")
DRY         = "--dry-run" in sys.argv
CUTOFF_DAYS = 90  # window for recent transactional data (orders, txns, snapshots)

prod_sb = create_client(PROD_CFG["SUPABASE_URL"], PROD_CFG["SUPABASE_KEY"])


def _parse_url(url: str) -> dict:
    s            = url[len("postgresql://"):]
    ui, hi       = s.rsplit("@", 1)
    user, pw     = ui.split(":", 1)
    hp, db       = hi.rsplit("/", 1)
    host, port   = hp.rsplit(":", 1)
    return dict(host=host, port=int(port), dbname=db, user=user, password=pw, sslmode="require")


def _conn():
    return psycopg2.connect(**_parse_url(DEV_CFG["DEV_DB_URL"]))


def _sql(cur, stmt: str, label: str):
    """Execute DDL on an autocommit cursor — errors are non-fatal."""
    if DRY:
        print(f"  DRY  {label}")
        return
    try:
        cur.execute(stmt)
        print(f"  OK   {label}")
    except Exception as e:
        print(f"  ERR  {label}: {e}")


def _fetch_prod(table: str) -> list[dict]:
    rows, off, ps = [], 0, 1000
    while True:
        b = prod_sb.table(table).select("*").range(off, off + ps - 1).execute().data
        rows.extend(b)
        if len(b) < ps:
            break
        off += ps
    return rows


def _fetch_prod_filtered(table: str, date_col: str, cutoff_iso: str) -> list[dict]:
    rows, off, ps = [], 0, 1000
    while True:
        b = (prod_sb.table(table).select("*").gte(date_col, cutoff_iso)
             .range(off, off + ps - 1).execute().data)
        rows.extend(b)
        if len(b) < ps:
            break
        off += ps
    return rows


def _insert_rows(table: str, rows: list[dict], pk_col: str | None = None,
                  exclude_cols: set[str] | None = None, label: str | None = None):
    label = label or table
    if not rows:
        print(f"  SKIP {label} (no rows in prod window)")
        return
    exclude_cols = exclude_cols or set()
    cols    = [c for c in rows[0].keys() if c not in exclude_cols]
    col_sql = ", ".join(f'"{c}"' for c in cols)
    vals    = [tuple(r[c] for c in cols) for r in rows]
    with _conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                f'INSERT INTO "{table}" ({col_sql}) VALUES %s ON CONFLICT DO NOTHING',
                vals,
            )
            if pk_col:
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', '{pk_col}'), "
                    f"(SELECT COALESCE(MAX(\"{pk_col}\"), 1) FROM \"{table}\"))"
                )
            conn.commit()
    print(f"  OK   {label}: {len(rows)} rows")


def _upsert_rows(table: str, rows: list[dict], pk_col: str, label: str | None = None):
    """Insert rows from prod; update all non-PK columns on conflict.
    Used for current-state tables (inventory, item_batches, sku_cogs_lots,
    sku_inventory) where dev may already have rows with stale values."""
    label = label or table
    if not rows:
        print(f"  SKIP {label} (no rows)")
        return
    cols     = list(rows[0].keys())
    col_sql  = ", ".join(f'"{c}"' for c in cols)
    upd_cols = [c for c in cols if c != pk_col]
    upd_sql  = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in upd_cols)
    vals     = [tuple(r[c] for c in cols) for r in rows]
    with _conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                f'INSERT INTO "{table}" ({col_sql}) VALUES %s '
                f'ON CONFLICT ("{pk_col}") DO UPDATE SET {upd_sql}',
                vals,
            )
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{pk_col}'), "
                f"(SELECT COALESCE(MAX(\"{pk_col}\"), 1) FROM \"{table}\"))"
            )
            conn.commit()
    print(f"  OK   {label}: {len(rows)} rows (upserted)")


# ── DDL strings ───────────────────────────────────────────────────────────────

_BLINKIT_DS_ELIGIBILITY = """
CREATE TABLE IF NOT EXISTS blinkit_ds_sku_eligibility (
    location_id   INTEGER NOT NULL REFERENCES partner_locations(location_id),
    sku_id        TEXT    NOT NULL REFERENCES skus(sku_id),
    status        TEXT    NOT NULL DEFAULT 'active'
                      CHECK (status IN (
                          'active','launch_awaited','darkstore_closed',
                          'sku_moved_out_low_sales','sku_city_exited','sku_recalled'
                      )),
    last_remark   TEXT,
    updated_date  DATE NOT NULL,
    PRIMARY KEY (location_id, sku_id)
);
"""


_BLINKIT_INV_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS blinkit_inventory_snapshots (
    id              SERIAL  PRIMARY KEY,
    snapshot_date   DATE    NOT NULL,
    location_id     INTEGER NOT NULL REFERENCES partner_locations(location_id),
    sku_id          TEXT    NOT NULL REFERENCES skus(sku_id),
    units_wh        INTEGER NOT NULL DEFAULT 0,
    units_incoming  INTEGER NOT NULL DEFAULT 0,
    units_ds        INTEGER NOT NULL DEFAULT 0,
    units_transit   INTEGER NOT NULL DEFAULT 0,
    total_sellable  INTEGER NOT NULL DEFAULT 0,
    last_7d_sales   INTEGER,
    last_15d_sales  INTEGER,
    last_30d_sales  INTEGER,
    UNIQUE (snapshot_date, location_id, sku_id)
);
"""

_BLINKIT_PERFORMANCE_DETAIL = """
CREATE TABLE IF NOT EXISTS blinkit_performance_detail (
    data_date              DATE     NOT NULL,
    location_id            INTEGER  NOT NULL,
    sku_id                 TEXT     NOT NULL,
    ds_name                TEXT,
    city                   TEXT,
    serving_wh             TEXT,
    inventory_available    BOOLEAN  NOT NULL DEFAULT FALSE,
    total_orders           INTEGER  NOT NULL DEFAULT 0,
    orders_with_complaint  INTEGER  NOT NULL DEFAULT 0,
    download_date          DATE     NOT NULL,
    CONSTRAINT blinkit_performance_detail_pkey
        PRIMARY KEY (data_date, location_id, sku_id)
);
CREATE INDEX IF NOT EXISTS idx_bpd_sku_date ON blinkit_performance_detail (sku_id, data_date);
CREATE INDEX IF NOT EXISTS idx_bpd_loc_sku ON blinkit_performance_detail (location_id, sku_id);
"""


_V_ASSEMBLABLE_SKUS = """
CREATE OR REPLACE VIEW v_assemblable_skus AS
SELECT
  b.sku_id,
  MIN(FLOOR((inv.quantity_on_hand - inv.quantity_reserved) / b.quantity_per_sku))::INT
      AS max_assemblable
FROM bom b
JOIN inventory inv ON inv.item_id = b.item_id
JOIN channels c    ON c.channel_id = inv.channel_id AND c.code = 'OWN_WH'
GROUP BY b.sku_id;
"""


def phase1_schema():
    """Drop stale objects and apply schema fixes to match prod.

    Uses an autocommit connection so each DDL statement is its own transaction —
    one failure does not abort subsequent statements.
    """
    conn = _conn()
    conn.autocommit = True
    cur = conn.cursor()

    print("\n=== Phase 1a: Drop stale views ===")
    for v in ("v_monthly_mis", "v_blinkit_reconciliation",
              "v_amazon_reconciliation", "v_darkstore_doc", "v_inventory_available"):
        _sql(cur, f"DROP VIEW IF EXISTS {v} CASCADE", f"DROP VIEW {v}")

    print("\n=== Phase 1b: Drop stale tables ===")
    stale = [
        "blinkit_ageing_snapshots",     # dropped prod — adds no replen value
        "blinkit_performance_summary",  # dropped prod — not used in engine
        "distribution_rules",           # legacy Blinkit distribution logic
        "replenishment_recommendations",# legacy recommendation table
        "demand_forecasts",             # legacy forecasting table
        "invoice_items",                # invoicing deferred
        "invoices",                     # invoicing deferred
        "purchase_order_items",         # dropped prod this session
        "purchase_orders",              # dropped prod this session
        "darkstore_inventory",          # dropped prod — migration 006
        "darkstore_sales",              # dropped prod — migration 006
        "amazon_fba_inventory",         # dropped prod — migration 007
        "amazon_warehouses",            # dropped prod — migration 007
    ]
    for t in stale:
        _sql(cur, f"DROP TABLE IF EXISTS {t} CASCADE", f"DROP TABLE {t}")

    print("\n=== Phase 1c: Schema fixes ===")

    # inventory: ensure batch_id FK column exists (prod tracks inventory per-batch)
    _sql(cur,
         "ALTER TABLE inventory ADD COLUMN IF NOT EXISTS "
         "batch_id INTEGER REFERENCES item_batches(batch_id)",
         "inventory: ensure batch_id FK column exists")
    # Drop the old over-restrictive unique constraint (prod allows multiple rows
    # per item_id/channel_id, one per batch — required for per-batch tracking).
    _sql(cur,
         "ALTER TABLE inventory DROP CONSTRAINT IF EXISTS inventory_item_channel_uq",
         "inventory: drop over-restrictive unique constraint if present")
    # Truncate inventory — phase 6 will upsert current prod stock values.
    _sql(cur,
         "TRUNCATE inventory RESTART IDENTITY CASCADE",
         "inventory: truncate stale rows (phase 6 will reload from prod)")

    # inventory_transactions: unit_cost dropped in migration 004
    _sql(cur,
         "ALTER TABLE inventory_transactions DROP COLUMN IF EXISTS unit_cost",
         "inventory_transactions: drop unit_cost")

    # orders: drop P&L columns removed by migration 001
    for col in ("commission_pct", "commission_amt", "logistics_cost",
                "ad_spend_allocated", "net_margin"):
        _sql(cur, f"ALTER TABLE orders DROP COLUMN IF EXISTS {col}",
             f"orders: drop {col}")

    # orders: add columns from migrations 005, 011, 012, 013
    for stmt, label in [
        ("ALTER TABLE orders ADD COLUMN IF NOT EXISTS partner_location_id INT",
         "orders: add partner_location_id"),
        ("ALTER TABLE orders ADD COLUMN IF NOT EXISTS lot_cogs_finalized BOOLEAN NOT NULL DEFAULT FALSE",
         "orders: add lot_cogs_finalized"),
        ("ALTER TABLE orders ADD COLUMN IF NOT EXISTS transfer_price NUMERIC(12,4)",
         "orders: add transfer_price"),
        ("ALTER TABLE orders ADD COLUMN IF NOT EXISTS return_responsible TEXT",
         "orders: add return_responsible"),
        ("ALTER TABLE orders ADD COLUMN IF NOT EXISTS return_customer_verbatim TEXT",
         "orders: add return_customer_verbatim"),
    ]:
        _sql(cur, stmt, label)

    # orders: add DIRECT to fulfillment_type check (migration 006)
    _sql(cur, "ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_fulfillment_type_check",
         "orders: drop old fulfillment_type check")
    _sql(cur,
         "ALTER TABLE orders ADD CONSTRAINT orders_fulfillment_type_check "
         "CHECK (fulfillment_type IN ('DROP_SHIP', 'OUTRIGHT', 'SOR', 'DIRECT'))",
         "orders: add fulfillment_type check with DIRECT")

    # orders: add REPLACEMENT to status check (migration 021)
    _sql(cur, "ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_status_check",
         "orders: drop old status check")
    _sql(cur,
         "ALTER TABLE orders ADD CONSTRAINT orders_status_check "
         "CHECK (status IN ('PENDING','FULFILLED','CANCELLED','RTO','SALE_RETURN','REPLACEMENT'))",
         "orders: add status check with REPLACEMENT")

    print("\n=== Phase 2: Create missing tables ===")
    _sql(cur, _BLINKIT_DS_ELIGIBILITY, "CREATE blinkit_ds_sku_eligibility")
    _sql(cur, _BLINKIT_INV_SNAPSHOTS,  "CREATE blinkit_inventory_snapshots")
    _sql(cur, _BLINKIT_PERFORMANCE_DETAIL, "CREATE blinkit_performance_detail")

    print("\n=== Phase 3: Create missing views ===")
    _sql(cur, _V_ASSEMBLABLE_SKUS, "CREATE v_assemblable_skus")

    cur.close()
    conn.close()


def phase4_clear_data():
    """Clear all transactional + master data so prod data can be loaded cleanly."""
    print("\n=== Phase 4: Clear transactional + master data ===")
    # Leaf-first order avoids FK violations without CASCADE.
    # Tables that may not exist in dev (e.g. already dropped stale ones) are skipped.
    clear_order = [
        "blinkit_performance_detail",
        "blinkit_ds_sku_eligibility",
        "blinkit_inventory_snapshots",
        "orders",
        "inventory_transactions",
        "inventory",
        "sku_inventory_transactions",
        "sku_cogs_lots",
        "sku_inventory",
        "item_batches",
        "bom",
        "sku_channel_ids",
        "sku_pricing",
        "sku_channel_tp",
        "partner_locations",
        "items",
        "channels",
        "skus",
        "suppliers",
        "company_config",
    ]
    conn = _conn()
    conn.autocommit = True          # each statement is its own txn — failure is non-fatal
    cur = conn.cursor()
    for t in clear_order:
        try:
            cur.execute(f"TRUNCATE {t} RESTART IDENTITY CASCADE")
            print(f"  OK   TRUNCATE {t}")
        except psycopg2.errors.UndefinedTable:
            print(f"  SKIP TRUNCATE {t} (table does not exist)")
        except Exception as e:
            print(f"  ERR  TRUNCATE {t}: {e}")
    cur.close()
    conn.close()


def phase5_load_master():
    """Fetch master data from prod via REST and insert into dev via psycopg2."""
    print("\n=== Phase 5: Load master data from prod ===")

    # Insert order: parents before children
    master_tables = [
        ("channels",       "channel_id"),
        ("suppliers",      "supplier_id"),
        ("skus",           None),           # TEXT primary key — no sequence
        ("company_config", "config_id"),
        ("items",          "item_id"),
        ("bom",            "bom_id"),
        ("sku_channel_ids","id"),
        ("sku_pricing",    "pricing_id"),
        ("sku_channel_tp", "tp_id"),
    ]

    for table, pk_col in master_tables:
        rows = _fetch_prod(table)
        if not rows:
            print(f"  SKIP {table} (empty in prod)")
            continue
        cols    = list(rows[0].keys())
        col_sql = ", ".join(f'"{c}"' for c in cols)
        vals    = [tuple(r[c] for c in cols) for r in rows]

        with _conn() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    f'INSERT INTO "{table}" ({col_sql}) VALUES %s ON CONFLICT DO NOTHING',
                    vals,
                )
                if pk_col:
                    cur.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table}', '{pk_col}'), "
                        f"(SELECT COALESCE(MAX(\"{pk_col}\"), 1) FROM \"{table}\"))"
                    )
                conn.commit()
        print(f"  OK   {table}: {len(rows)} rows")

    # partner_locations: self-referential FK — insert root rows (parent IS NULL) first
    pl_rows = _fetch_prod("partner_locations")
    if pl_rows:
        cols     = list(pl_rows[0].keys())
        col_sql  = ", ".join(f'"{c}"' for c in cols)
        roots    = [r for r in pl_rows if not r.get("parent_location_id")]
        children = [r for r in pl_rows if r.get("parent_location_id")]

        with _conn() as conn:
            with conn.cursor() as cur:
                for batch in [roots, children]:
                    if batch:
                        vals = [tuple(r[c] for c in cols) for r in batch]
                        execute_values(
                            cur,
                            f'INSERT INTO partner_locations ({col_sql}) VALUES %s ON CONFLICT DO NOTHING',
                            vals,
                        )
                cur.execute(
                    "SELECT setval(pg_get_serial_sequence('partner_locations','location_id'), "
                    "(SELECT MAX(location_id) FROM partner_locations))"
                )
                conn.commit()
        print(f"  OK   partner_locations: {len(pl_rows)} rows "
              f"({len(roots)} root + {len(children)} DS)")


def phase6_load_current_state():
    """Full copy of current-state tables from prod — these aren't date-filtered,
    they represent a single live balance per row (stock on hand, open lots, etc).
    Uses _upsert_rows (not _insert_rows) so existing dev rows with stale values
    (e.g. inventory.quantity_on_hand=0) are overwritten with prod's live figures."""
    print("\n=== Phase 6: Load current-state data (full copy) from prod ===")
    _upsert_rows("item_batches",   _fetch_prod("item_batches"),   pk_col="batch_id")
    _upsert_rows("sku_cogs_lots",  _fetch_prod("sku_cogs_lots"),  pk_col="lot_id")
    _upsert_rows("inventory",      _fetch_prod("inventory"),      pk_col="inv_id")
    _upsert_rows("sku_inventory",  _fetch_prod("sku_inventory"),  pk_col="sku_inv_id")
    _insert_rows("blinkit_ds_sku_eligibility", _fetch_prod("blinkit_ds_sku_eligibility"))


def phase7_load_recent_transactional():
    """Copy the last CUTOFF_DAYS of transactional history from prod — enough for
    realistic order flow, ADS/replenishment calcs, and recent stock movements
    without dragging the entire prod history into dev."""
    cutoff = (date.today() - timedelta(days=CUTOFF_DAYS)).isoformat()
    print(f"\n=== Phase 7: Load recent transactional data (since {cutoff}) ===")
    _insert_rows("orders",
                 _fetch_prod_filtered("orders", "order_date", cutoff))
    _insert_rows("inventory_transactions",
                 _fetch_prod_filtered("inventory_transactions", "txn_date", cutoff),
                 pk_col="txn_id")
    _insert_rows("sku_inventory_transactions",
                 _fetch_prod_filtered("sku_inventory_transactions", "txn_date", cutoff),
                 pk_col="txn_id")
    _insert_rows("blinkit_inventory_snapshots",
                 _fetch_prod_filtered("blinkit_inventory_snapshots", "snapshot_date", cutoff),
                 pk_col="id")
    _insert_rows("blinkit_performance_detail",
                 _fetch_prod_filtered("blinkit_performance_detail", "data_date", cutoff))


def phase8_verify():
    print("\n=== Phase 8: Verify ===")
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )
            tables = [r[0] for r in cur.fetchall()]
            cur.execute(
                "SELECT viewname FROM pg_views WHERE schemaname='public' ORDER BY viewname"
            )
            views = [r[0] for r in cur.fetchall()]

            # Row counts for key tables
            counts = {}
            for t in ("channels","suppliers","items","bom","skus","sku_channel_ids",
                      "partner_locations","company_config","sku_pricing","sku_channel_tp",
                      "item_batches","sku_cogs_lots","inventory","sku_inventory",
                      "orders","inventory_transactions","sku_inventory_transactions",
                      "blinkit_ds_sku_eligibility","blinkit_inventory_snapshots",
                      "blinkit_performance_detail"):
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                counts[t] = cur.fetchone()[0]

    print(f"\n  Tables  ({len(tables)}): {', '.join(tables)}")
    print(f"  Views   ({len(views)}): {', '.join(views)}")
    print("\n  Master data row counts:")
    for t, n in counts.items():
        print(f"    {t:<25} {n}")

    required_tables = {
        "channels","suppliers","items","bom","skus","sku_channel_ids",
        "inventory","inventory_transactions","orders","partner_locations",
        "blinkit_ds_sku_eligibility",
        "blinkit_inventory_snapshots","company_config","item_batches",
    }
    required_views = {
        "v_inventory_summary","v_assemblable_skus",
        "v_item_current_cost","v_sku_live_cogs",
    }
    missing_t = required_tables - set(tables)
    missing_v = required_views  - set(views)
    if missing_t:
        print(f"\n  WARN  Missing tables: {missing_t}")
    if missing_v:
        print(f"\n  WARN  Missing views: {missing_v}")
    if not missing_t and not missing_v:
        print("\n  All required tables and views present. Dev DB in sync.")


def main():
    if DRY:
        print("=== DRY RUN — no writes will be made ===")

    # Phases 1–3: schema changes (autocommit — each statement is independent)
    phase1_schema()

    if DRY:
        print("\n[DRY RUN complete — rerun without --dry-run to apply changes]")
        return

    # Phase 4: clear data (autocommit conn — each truncate is independent)
    phase4_clear_data()

    # Phase 5: load master data (one conn per table — isolates failures)
    phase5_load_master()

    # Phase 6: load current-state data (full copy — stock, lots, batches)
    phase6_load_current_state()

    # Phase 7: load recent transactional history (last CUTOFF_DAYS days)
    phase7_load_recent_transactional()

    # Phase 8: verify
    phase8_verify()

    print("\nSync complete.")


if __name__ == "__main__":
    main()
