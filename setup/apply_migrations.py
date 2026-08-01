#!/usr/bin/env python3
"""
setup/apply_migrations.py

Apply not-yet-applied migrations from setup/migrations/*.sql in filename order,
recording each in a `schema_migrations` table. Safe to re-run — migrations that
are already recorded are skipped, and each migration runs in its own
transaction (a failure rolls back the file AND its schema_migrations row, so a
half-applied migration is never marked done).

Usage:
    python setup/apply_migrations.py              # apply pending migrations
    python setup/apply_migrations.py --dry-run    # show plan, no writes
    python setup/apply_migrations.py --baseline   # record existing files as applied WITHOUT executing
    python setup/apply_migrations.py --fresh      # apply all files from scratch (greenfield only)
    python setup/apply_migrations.py --status     # list applied vs pending, no writes

Connection: TCB_TEST_DB_URL env var, falling back to DEV_DB_URL in .env.dev.
Dev-only by design — prod apply stays a human step (see CLAUDE.md, DB Change Workflow).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import dotenv_values
import psycopg2

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "setup" / "migrations"
TABLE = "schema_migrations"


class MigrationError(Exception):
    pass


def get_db_url() -> str:
    url = os.environ.get("TCB_TEST_DB_URL")
    if url:
        return url
    dev = dotenv_values(ROOT / ".env.dev")
    return dev.get("DEV_DB_URL", "")





def ensure_migrations_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS {TABLE} ("
            "filename TEXT PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
    conn.commit()


def migrations_table_exists(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT to_regclass(%s)",
            (TABLE,),
        )
        return cur.fetchone()[0] is not None


def list_migrations(migrations_dir: Path) -> list[Path]:
    return sorted(migrations_dir.glob("*.sql"))


def applied_filenames(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT filename FROM {TABLE}")
        return {row[0] for row in cur.fetchall()}


def _done_filenames(conn) -> set[str]:
    if not migrations_table_exists(conn):
        return set()
    return applied_filenames(conn)


def apply_pending(conn, migrations_dir: Path, dry_run: bool = False, verbose: bool = True) -> list[str]:
    """Apply each not-yet-recorded migration in its own transaction. Returns applied filenames."""
    if not dry_run:
        ensure_migrations_table(conn)
    done = _done_filenames(conn)
    applied: list[str] = []
    for f in list_migrations(migrations_dir):
        if f.name in done:
            continue
        if dry_run:
            if verbose:
                print(f"  DRY  apply {f.name}")
            continue
        sql = f.read_text()
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(f"INSERT INTO {TABLE} (filename) VALUES (%s)", (f.name,))
            conn.commit()
            applied.append(f.name)
            if verbose:
                print(f"  OK   applied {f.name}")
        except Exception as e:
            conn.rollback()
            raise MigrationError(f"migration {f.name} failed: {e}") from e
    return applied


def record_baseline(conn, migrations_dir: Path, dry_run: bool = False, verbose: bool = True) -> list[str]:
    """Record all current migration files as applied WITHOUT executing them."""
    if not dry_run:
        ensure_migrations_table(conn)
    done = _done_filenames(conn)
    recorded: list[str] = []
    for f in list_migrations(migrations_dir):
        if f.name in done:
            continue
        if dry_run:
            if verbose:
                print(f"  DRY  baseline {f.name}")
            continue
        with conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {TABLE} (filename) VALUES (%s) ON CONFLICT DO NOTHING",
                (f.name,),
            )
        conn.commit()
        recorded.append(f.name)
        if verbose:
            print(f"  OK   baseline {f.name}")
    return recorded


def print_status(conn, migrations_dir: Path) -> int:
    if not migrations_table_exists(conn):
        print("schema_migrations table does not exist yet.")
        print(f"  {len(list_migrations(migrations_dir))} migration file(s) present.")
        print("First run on an environment that already has migrations applied by hand:")
        print("  python setup/apply_migrations.py --baseline")
        print("Greenfield only (apply everything from scratch):")
        print("  python setup/apply_migrations.py --fresh")
        return 0
    done = applied_filenames(conn)
    files = [f.name for f in list_migrations(migrations_dir)]
    pending = [n for n in files if n not in done]
    missing = sorted(done - set(files))
    print(f"Applied: {len(done)}   Pending: {len(pending)}")
    for name in files:
        state = "applied" if name in done else "pending"
        print(f"  {state:<8} {name}")
    if missing:
        print("\nRecorded but no longer present as files:")
        for name in missing:
            print(f"  missing  {name}")
    return 0


def run_migrations(
    *,
    dry_run: bool = False,
    baseline: bool = False,
    fresh: bool = False,
    status: bool = False,
    verbose: bool = True,
) -> int:
    url = get_db_url()
    if not url:
        print("ERROR: no DB URL — set TCB_TEST_DB_URL or DEV_DB_URL in .env.dev", file=sys.stderr)
        return 1

    conn = psycopg2.connect(url)
    try:
        if status:
            return print_status(conn, MIGRATIONS_DIR)

        exists = migrations_table_exists(conn)
        if not exists and not baseline and not fresh and list_migrations(MIGRATIONS_DIR):
            print(
                "First run on a database that already has migrations applied by hand. "
                "Use --baseline to record existing files as applied (no execution), "
                "or --fresh to apply every file from scratch (greenfield only).",
                file=sys.stderr,
            )
            return 1

        if dry_run:
            if baseline:
                record_baseline(conn, MIGRATIONS_DIR, dry_run=True, verbose=verbose)
            else:
                apply_pending(conn, MIGRATIONS_DIR, dry_run=True, verbose=verbose)
            print("\nDRY RUN complete — rerun without --dry-run to apply changes.")
            return 0

        if baseline:
            applied = record_baseline(conn, MIGRATIONS_DIR, verbose=verbose)
            print(f"\n{len(applied)} migration(s) baselined (recorded as applied, not executed).")
            return 0
        if fresh:
            applied = apply_pending(conn, MIGRATIONS_DIR, verbose=verbose)
            print(f"\n{len(applied)} migration(s) applied.")
            return 0
        applied = apply_pending(conn, MIGRATIONS_DIR, verbose=verbose)
        print(f"\n{len(applied)} migration(s) applied.")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="show plan, no writes")
    parser.add_argument("--baseline", action="store_true", help="record existing files as applied, no execution")
    parser.add_argument("--fresh", action="store_true", help="apply all files from scratch (greenfield only)")
    parser.add_argument("--status", action="store_true", help="list applied vs pending, no writes")
    parser.add_argument("--quiet", action="store_true", help="suppress per-file output")
    args = parser.parse_args()

    if sum([args.baseline, args.fresh, args.status]) > 1:
        parser.error("--baseline, --fresh, and --status are mutually exclusive")

    return run_migrations(
        dry_run=args.dry_run,
        baseline=args.baseline,
        fresh=args.fresh,
        status=args.status,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    sys.exit(main())
