"""
Tests for setup/apply_migrations.py (issue #41).

Runs the migration runner against a throwaway schema on a real Postgres,
asserting the runner's behaviour independent of the repo's actual migrations:
apply-in-order, re-run no-op, rollback-on-failure leaves no schema_migrations
row, and --baseline records without executing.

Connection: reads `TCB_TEST_DB_URL` env var, falling back to `DEV_DB_URL` in
`.env.dev`. Skips cleanly when neither is set so the module can be collected
in environments without a configured dev DB.

Run:
    python -m pytest tests/migrations/test_migrations_runner.py -m integration -q
"""
import os
import sys
import tempfile
from pathlib import Path

import psycopg2
import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from setup import apply_migrations as m  # noqa: E402


def _db_url() -> str:
    url = os.environ.get("TCB_TEST_DB_URL")
    if url:
        return url
    try:
        from dotenv import dotenv_values
        dev = dotenv_values(ROOT / ".env.dev")
    except Exception:
        dev = {}
    return dev.get("DEV_DB_URL", "")


@pytest.fixture()
def conn():
    url = _db_url()
    if not url:
        pytest.skip("No DB URL — set TCB_TEST_DB_URL or DEV_DB_URL in .env.dev")
    conn = psycopg2.connect(url)
    yield conn
    conn.close()


@pytest.fixture()
def schema(conn):
    """Isolate each test in its own schema so the runner never touches real tables."""
    name = f"mig_test_{os.getpid()}"
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {name} CASCADE")
        cur.execute(f"CREATE SCHEMA {name}")
        cur.execute(f"SET search_path TO {name}")
    conn.commit()
    yield name
    with conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA {name} CASCADE")
    conn.commit()


def _write_migrations(*files: tuple[str, str]) -> Path:
    """Create a temp migrations dir with (filename, sql) pairs."""
    d = Path(tempfile.mkdtemp())
    for name, sql in files:
        (d / name).write_text(sql)
    return d


def test_apply_in_order(conn, schema):
    d = _write_migrations(
        ("001_a.sql", "CREATE TABLE a (id INT);\n"),
        ("002_b.sql", "CREATE TABLE b (id INT);\n"),
    )
    applied = m.apply_pending(conn, d)
    assert applied == ["001_a.sql", "002_b.sql"]

    with conn.cursor() as cur:
        cur.execute(f"SELECT filename FROM {m.TABLE} ORDER BY filename")
        assert [r[0] for r in cur.fetchall()] == ["001_a.sql", "002_b.sql"]
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.a",))
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.b",))
        assert cur.fetchone()[0] is not None


def test_rerun_is_noop(conn, schema):
    d = _write_migrations(("001_a.sql", "CREATE TABLE a (id INT);\n"))
    assert m.apply_pending(conn, d) == ["001_a.sql"]
    assert m.apply_pending(conn, d) == []
    assert m.apply_pending(conn, d) == []


def test_failed_migration_rolls_back_and_is_not_recorded(conn, schema):
    d = _write_migrations(
        ("001_good.sql", "CREATE TABLE good (id INT);\n"),
        ("002_bad.sql", "SELECT * FROM does_not_exist;\n"),
        ("003_never.sql", "CREATE TABLE never (id INT);\n"),
    )
    with pytest.raises(m.MigrationError):
        m.apply_pending(conn, d)

    with conn.cursor() as cur:
        cur.execute(f"SELECT filename FROM {m.TABLE} ORDER BY filename")
        assert [r[0] for r in cur.fetchall()] == ["001_good.sql"]
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.good",))
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.never",))
        assert cur.fetchone()[0] is None


def test_baseline_records_without_executing(conn, schema):
    d = _write_migrations(("010_x.sql", "CREATE TABLE x (id INT);\n"))
    recorded = m.record_baseline(conn, d)
    assert recorded == ["010_x.sql"]

    with conn.cursor() as cur:
        cur.execute(f"SELECT filename FROM {m.TABLE}")
        assert [r[0] for r in cur.fetchall()] == ["010_x.sql"]
        # Recorded but never executed → the table must not exist.
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.x",))
        assert cur.fetchone()[0] is None

    # After baseline, apply_pending treats it as done.
    assert m.apply_pending(conn, d) == []


def test_dry_run_writes_nothing(conn, schema):
    d = _write_migrations(("001_a.sql", "CREATE TABLE a (id INT);\n"))
    assert m.apply_pending(conn, d, dry_run=True) == []

    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"{schema}.a",))
        assert cur.fetchone()[0] is None
        cur.execute("SELECT to_regclass(%s)", (m.TABLE,))
        assert cur.fetchone()[0] is None
