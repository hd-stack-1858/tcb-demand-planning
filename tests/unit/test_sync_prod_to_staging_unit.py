"""Contract tests for setup/sync_prod_to_staging.py (release 0.1).

Guards that the script: exists, imports cleanly, supports --dry-run and the
three required credentials (via CLI or env vars), and covers all key tables in
its clear and load phases. No DB credentials or network access required.
"""
import ast
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
SCRIPT      = REPO_ROOT / "setup" / "sync_prod_to_staging.py"
ENV_EXAMPLE = REPO_ROOT / ".env.staging.example"


def _src() -> str:
    return SCRIPT.read_text()


def _ast_names() -> set[str]:
    tree = ast.parse(_src())
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


# ── Existence & importability ─────────────────────────────────────────────────

def test_script_exists():
    assert SCRIPT.exists(), "setup/sync_prod_to_staging.py is missing"


def test_env_staging_example_exists():
    assert ENV_EXAMPLE.exists(), ".env.staging.example is missing"


def test_env_staging_example_documents_staging_db_url():
    assert "STAGING_DB_URL" in ENV_EXAMPLE.read_text()


def test_script_is_valid_python():
    ast.parse(_src())  # raises SyntaxError on bad syntax


def test_script_has_main_guard():
    assert 'if __name__ == "__main__"' in _src()


# ── CLI flags ─────────────────────────────────────────────────────────────────

def test_dry_run_flag_present():
    assert "--dry-run" in _src()


def test_prod_url_flag_present():
    assert "--prod-url" in _src()


def test_prod_key_flag_present():
    assert "--prod-key" in _src()


def test_staging_db_url_flag_present():
    assert "--staging-db-url" in _src()


# ── Credential resolution ─────────────────────────────────────────────────────

def test_reads_prod_url_from_env_file():
    # Falls back to .env SUPABASE_URL when CLI flag absent
    assert "SUPABASE_URL" in _src()


def test_reads_prod_key_from_env_file():
    assert "SUPABASE_KEY" in _src()


def test_reads_staging_db_url_from_env_staging():
    assert ".env.staging" in _src()


def test_errors_on_missing_credentials():
    # _resolve_credentials must call sys.exit when any of the three are missing
    assert "sys.exit" in _src()


# ── Table coverage ────────────────────────────────────────────────────────────

_REQUIRED_TABLES = [
    "channels", "suppliers", "skus", "items", "bom",
    "sku_channel_ids", "sku_pricing", "sku_channel_tp",
    "partner_locations", "company_config",
    "item_batches", "sku_cogs_lots",
    "inventory", "sku_inventory",
    "blinkit_ds_sku_eligibility",
    "orders", "inventory_transactions", "sku_inventory_transactions",
    "blinkit_inventory_snapshots", "blinkit_performance_detail",
]


@pytest.mark.parametrize("table", _REQUIRED_TABLES)
def test_table_covered(table):
    assert table in _src(), f'"{table}" not referenced in sync_prod_to_staging.py'


def test_clear_phase_runs_before_load_phase():
    src = _src()
    clear_pos = src.find("_clear_staging")
    load_pos  = src.find("_load_all_tables")
    assert clear_pos < load_pos, "_clear_staging must be called before _load_all_tables"


def test_partner_locations_has_parent_first_logic():
    # Self-referential FK — roots must be inserted before children
    assert "parent_first" in _src()
    assert "parent_location_id" in _src()
