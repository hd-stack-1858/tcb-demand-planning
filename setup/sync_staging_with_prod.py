#!/usr/bin/env python3
"""
setup/sync_prod_to_staging.py

Copies a full snapshot of the prod Supabase DB onto staging. Clears staging
data first, then loads every table from prod. Safe to re-run.

Credentials are resolved in this order:
  1. Command-line flags (--prod-url, --prod-key, --staging-db-url)
  2. .env.staging (for STAGING_DB_URL) + .env (for SUPABASE_URL / SUPABASE_KEY)
  3. OS environment variables

At minimum you need:
  PROD_SUPABASE_URL   — prod project URL   (https://xxx.supabase.co)
  PROD_SUPABASE_KEY   — prod service-role key
  STAGING_DB_URL      — staging direct PostgreSQL connection string
                        (postgresql://postgres.xxx:PASSWORD@aws-xxx.pooler.supabase.com:5432/postgres)

The staging DB must already have the correct schema — run migrations against
staging before calling this script. This script only syncs data.

Usage:
    python setup/sync_prod_to_staging.py
    python setup/sync_prod_to_staging.py --dry-run
    python setup/sync_prod_to_staging.py \\
        --prod-url  https://xxx.supabase.co \\
        --prod-key  <service-role-key> \\
        --staging-db-url postgresql://...
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import dotenv_values
import psycopg2
from psycopg2.extras import execute_values
from supabase import create_client

ROOT = Path(__file__).parent.parent

# ── Credential resolution ─────────────────────────────────────────────────────

def _resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    """Return (prod_url, prod_key, staging_db_url) from args → .env files → env."""
    prod_cfg    = dotenv_values(ROOT / ".env")
    staging_cfg = dotenv_values(ROOT / ".env.staging")

    prod_url        = (args.prod_url
                       or os.environ.get("PROD_SUPABASE_URL")
                       or prod_cfg.get("SUPABASE_URL")
                       or "")
    prod_key        = (args.prod_key
                       or os.environ.get("PROD_SUPABASE_KEY")
                       or prod_cfg.get("SUPABASE_KEY")
                       or "")
    staging_db_url  = (args.staging_db_url
                       or os.environ.get("STAGING_DB_URL")
                       or staging_cfg.get("STAGING_DB_URL")
                       or "")

    missing = [k for k, v in [
        ("--prod-url / PROD_SUPABASE_URL", prod_url),
        ("--prod-key / PROD_SUPABASE_KEY", prod_key),
        ("--staging-db-url / STAGING_DB_URL", staging_db_url),
    ] if not v]

    if missing:
        sys.exit(
            "ERROR: missing required credentials:\n"
            + "\n".join(f"  {m}" for m in missing)
            + "\n\nSet them via CLI flags, .env / .env.staging, or environment variables."
        )

    return prod_url, prod_key, staging_db_url


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_db_url(url: str) -> dict:
    """Parse a postgresql://user:password@host:port/dbname URL into psycopg2 kwargs."""
    s         = url[len("postgresql://"):]
    ui, hi    = s.rsplit("@", 1)
    user, pw  = ui.split(":", 1)
    hp, db    = hi.rsplit("/", 1)
    host, port = hp.rsplit(":", 1)
    return dict(host=host, port=int(port), dbname=db, user=user, password=pw, sslmode="require")


def _staging_conn(staging_db_url: str):
    return psycopg2.connect(**_parse_db_url(staging_db_url))


def _fetch_all(prod_sb, table: str) -> list[dict]:
    """Fetch every row of a prod table via the REST API."""
    rows, off, ps = [], 0, 1000
    while True:
        batch = prod_sb.table(table).select("*").range(off, off + ps - 1).execute().data
        rows.extend(batch)
        if len(batch) < ps:
            break
        off += ps
    return rows


def _clear_staging(staging_db_url: str, dry: bool) -> None:
    """Truncate all tables on staging in dependency-safe leaf-first order."""
    print("\n=== Phase 1: Clear staging data ===")
    clear_order = [
        "blinkit_performance_detail",
        "blinkit_ds_sku_eligibility",
        "blinkit_inventory_snapshots",
        "orders",
        "inventory_transactions",
        "sku_inventory_transactions",
        "inventory",
        "sku_inventory",
        "sku_cogs_lots",
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
    if dry:
        for t in clear_order:
            print(f"  DRY  TRUNCATE {t}")
        return

    conn = _staging_conn(staging_db_url)
    conn.autocommit = True
    cur = conn.cursor()
    for t in clear_order:
        try:
            cur.execute(f"TRUNCATE {t} RESTART IDENTITY CASCADE")
            print(f"  OK   TRUNCATE {t}")
        except psycopg2.errors.UndefinedTable:
            print(f"  SKIP TRUNCATE {t} (does not exist in staging schema)")
        except Exception as e:
            print(f"  ERR  TRUNCATE {t}: {e}")
    cur.close()
    conn.close()


def _load_table(prod_sb, table: str, staging_db_url: str, pk_col: str | None,
                dry: bool, parent_first: bool = False) -> None:
    """Fetch all rows from prod and insert into staging."""
    rows = _fetch_all(prod_sb, table)
    if not rows:
        print(f"  SKIP {table} (empty in prod)")
        return
    if dry:
        print(f"  DRY  {table}: {len(rows)} rows")
        return

    cols    = list(rows[0].keys())
    col_sql = ", ".join(f'"{c}"' for c in cols)

    def _insert_batch(batch):
        vals = [tuple(r[c] for c in cols) for r in batch]
        with _staging_conn(staging_db_url) as conn:
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

    if parent_first:
        # partner_locations is self-referential — insert root rows first
        roots    = [r for r in rows if not r.get("parent_location_id")]
        children = [r for r in rows if r.get("parent_location_id")]
        if roots:
            _insert_batch(roots)
        if children:
            _insert_batch(children)
    else:
        _insert_batch(rows)

    print(f"  OK   {table}: {len(rows)} rows")


def _load_all_tables(prod_sb, staging_db_url: str, dry: bool) -> None:
    print("\n=== Phase 2: Load master data ===")
    master = [
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
    for table, pk_col in master:
        _load_table(prod_sb, table, staging_db_url, pk_col, dry)

    # partner_locations: self-referential FK — roots before children
    _load_table(prod_sb, "partner_locations", staging_db_url, "location_id", dry,
                parent_first=True)

    print("\n=== Phase 3: Load current-state data ===")
    current_state = [
        ("item_batches",              "batch_id"),
        ("sku_cogs_lots",             "lot_id"),
        ("inventory",                 "inv_id"),
        ("sku_inventory",             "sku_inv_id"),
        ("blinkit_ds_sku_eligibility", None),
    ]
    for table, pk_col in current_state:
        _load_table(prod_sb, table, staging_db_url, pk_col, dry)

    print("\n=== Phase 4: Load transactional data (full history) ===")
    transactional = [
        ("orders",                      None),
        ("inventory_transactions",      "txn_id"),
        ("sku_inventory_transactions",  "txn_id"),
        ("blinkit_inventory_snapshots", "id"),
        ("blinkit_performance_detail",  None),
    ]
    for table, pk_col in transactional:
        _load_table(prod_sb, table, staging_db_url, pk_col, dry)


def _verify(staging_db_url: str) -> None:
    print("\n=== Phase 5: Verify ===")
    key_tables = [
        "channels", "suppliers", "items", "bom", "skus", "sku_channel_ids",
        "partner_locations", "company_config", "sku_pricing", "sku_channel_tp",
        "item_batches", "sku_cogs_lots", "inventory", "sku_inventory",
        "orders", "inventory_transactions", "sku_inventory_transactions",
        "blinkit_ds_sku_eligibility", "blinkit_inventory_snapshots",
        "blinkit_performance_detail",
    ]
    with _staging_conn(staging_db_url) as conn:
        with conn.cursor() as cur:
            print("\n  Row counts:")
            for t in key_tables:
                try:
                    cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                    n = cur.fetchone()[0]
                    flag = "  " if n > 0 else "WARN"
                    print(f"    {flag} {t:<35} {n}")
                except psycopg2.errors.UndefinedTable:
                    print(f"    SKIP {t:<35} (table does not exist)")

    print("\n  Sync complete.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy a full prod snapshot onto the staging Supabase DB."
    )
    parser.add_argument("--prod-url",       default="",
                        help="Prod Supabase project URL (https://xxx.supabase.co)")
    parser.add_argument("--prod-key",       default="",
                        help="Prod Supabase service-role key")
    parser.add_argument("--staging-db-url", default="",
                        help="Staging direct PostgreSQL connection string")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without writing anything")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN — no writes will be made ===\n")

    prod_url, prod_key, staging_db_url = _resolve_credentials(args)
    prod_sb = create_client(prod_url, prod_key)

    _clear_staging(staging_db_url, args.dry_run)
    _load_all_tables(prod_sb, staging_db_url, args.dry_run)

    if not args.dry_run:
        _verify(staging_db_url)

    print("\nDone.")


if __name__ == "__main__":
    main()
