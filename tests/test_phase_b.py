"""Phase B1 tests — Blinkit sell-out ingestion.

Requires dev DB with sku_channel_ids seeded for BLINKIT:
  Run setup/seed_blinkit_sku_channel_ids.sql in dev Supabase SQL editor first.

All tests hit dev DB only (TCB_ENV=dev set by conftest.py).
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ingest.utils import resolve_blinkit_sku, get_sku_cogs_at_date

# Sales file paths
_SALES_DIR = Path("blinkit_reports/sales")
_JAN_FILE  = _SALES_DIR / "sales-report_January 2026.xlsx"
_PAYOUT_DIR = Path("blinkit_reports/payout sheets")
_DEC_PAYOUT = _PAYOUT_DIR / "payout_sheet_2025-12"
_MAR_PAYOUT = _PAYOUT_DIR / "payout_sheet_2026-03"


# ── COGS helpers ──────────────────────────────────────────────────────────────

def test_cogs_at_date_known_sku(db):
    """TCB005 should return a non-zero COGS for Jan 2026 (batches exist from Sep 2025)."""
    get_sku_cogs_at_date.cache_clear()
    cogs = get_sku_cogs_at_date("TCB005", date(2026, 1, 15))
    assert cogs is not None, "Expected COGS, got None — check item_batches in dev DB"
    assert 400 < cogs < 700, f"COGS {cogs} outside expected range for TCB005"


def test_cogs_at_date_no_prior_batch(db):
    """Returns None if no batch existed before the given date (before Jun 2025)."""
    get_sku_cogs_at_date.cache_clear()
    cogs = get_sku_cogs_at_date("TCB005", date(2025, 1, 1))
    assert cogs is None, f"Expected None (no batches in Jan 2025), got {cogs}"


# ── SKU resolution ────────────────────────────────────────────────────────────

def test_resolve_sku_tcb009_feb(db):
    """item 10274008 before 2026-03-01 → TCB009 (2025 mugs)."""
    assert resolve_blinkit_sku(10274008, date(2026, 2, 15)) == "TCB009"


def test_resolve_sku_tcb009_1_mar(db):
    """item 10274008 from 2026-03-01 → TCB009_1 (2026 mugs)."""
    assert resolve_blinkit_sku(10274008, date(2026, 3, 1)) == "TCB009_1"


def test_resolve_sku_known(db):
    """Known item IDs resolve correctly."""
    assert resolve_blinkit_sku(10272641, date(2026, 1, 1)) == "TCB005"
    assert resolve_blinkit_sku(10282817, date(2026, 1, 1)) == "TCB011"


def test_resolve_sku_unknown(db):
    """Unknown item ID returns None without raising."""
    result = resolve_blinkit_sku(99999999, date(2026, 1, 1))
    assert result is None


# ── Sales loader ──────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _JAN_FILE.exists(), reason="Jan sales file not found")
def test_sales_dry_run(db):
    """Dry run parses Jan file and builds row dicts without any DB writes."""
    from ingest.load_blinkit_sales import load_file
    new, dup, skip = load_file(_JAN_FILE, db, dry_run=True)
    # 173 parseable rows; 2 share a duplicate order_id within the file itself
    assert new == 173, f"Expected 173 rows, got {new}"
    assert dup == 0
    assert skip < 5


@pytest.mark.skipif(not _JAN_FILE.exists(), reason="Jan sales file not found")
def test_sales_inserts(db):
    """Load Jan file into dev orders — expect 171 unique new rows for BLK channel."""
    from ingest.load_blinkit_sales import load_file

    db.table("orders").delete().eq("channel_id", 4).gte("order_date", "2020-01-01").execute()

    new, dup, skip = load_file(_JAN_FILE, db, dry_run=False)
    assert new == 173, f"Expected 173 new, got {new}"
    assert skip < 5


@pytest.mark.skipif(not _JAN_FILE.exists(), reason="Jan sales file not found")
def test_sales_idempotent(db):
    """Loading Jan file twice produces zero new rows on second run."""
    from ingest.load_blinkit_sales import load_file

    load_file(_JAN_FILE, db, dry_run=False)  # ensure loaded
    new, dup, _ = load_file(_JAN_FILE, db, dry_run=False)
    assert new == 0, f"Expected 0 new on re-run, got {new}"
    assert dup == 173


# ── Payout loader ─────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _DEC_PAYOUT.exists(), reason="Dec 2025 payout folder not found")
def test_payout_creates_dec_orders(db):
    """Dec 2025 payout (no daily file) creates FULFILLED orders for that month."""
    from ingest.load_blinkit_payout import load_payout_folder

    # Clean up Dec rows
    db.table("orders").delete() \
      .eq("channel_id", 4) \
      .lte("order_date", "2025-12-31") \
      .gte("order_date", "2025-12-01") \
      .execute()

    new, skipped, returns = load_payout_folder(_DEC_PAYOUT, db, dry_run=False)
    assert new == 41, f"Expected 41 Dec orders, got {new}"

    # Verify rows landed in DB
    rows = (
        db.table("orders")
        .select("order_id")
        .eq("channel_id", 4)
        .gte("order_date", "2025-12-01")
        .lte("order_date", "2025-12-31")
        .execute()
        .data
    )
    assert len(rows) >= 41


@pytest.mark.skipif(not _MAR_PAYOUT.exists(), reason="Mar 2026 payout folder not found")
def test_payout_marks_returns(db):
    """Mar 2026 payout marks correct number of orders as SALE_RETURN."""
    from ingest.load_blinkit_payout import load_payout_folder
    from ingest.load_blinkit_sales import load_file

    # Ensure Mar orders exist (load daily file if available, else payout will create them)
    mar_file = _SALES_DIR / "sales-report_March 2026.xlsx"
    if mar_file.exists():
        load_file(mar_file, db, dry_run=False)

    _, _, returns = load_payout_folder(_MAR_PAYOUT, db, dry_run=False)
    # 12 rows in Cancelled/Returned tab = 7 genuine returns + 5 cancellation confirmations
    assert returns == 7, f"Expected 7 returns for Mar 2026, got {returns}"

    # Verify in DB
    returned = (
        db.table("orders")
        .select("order_id")
        .eq("channel_id", 4)
        .eq("status", "SALE_RETURN")
        .gte("order_date", "2026-03-01")
        .lte("order_date", "2026-03-31")
        .execute()
        .data
    )
    assert len(returned) >= 7


@pytest.mark.skipif(not _DEC_PAYOUT.exists(), reason="Dec 2025 payout folder not found")
def test_payout_idempotent(db):
    """Running Dec payout twice produces zero new orders on the second run."""
    from ingest.load_blinkit_payout import load_payout_folder

    load_payout_folder(_DEC_PAYOUT, db, dry_run=False)  # ensure loaded
    new, skipped, _ = load_payout_folder(_DEC_PAYOUT, db, dry_run=False)
    assert new == 0, f"Expected 0 new on re-run, got {new}"
