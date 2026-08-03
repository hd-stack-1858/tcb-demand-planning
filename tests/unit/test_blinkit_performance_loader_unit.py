"""Unit tests for ingest/blinkit_performance_loader.py's resolved-key dedup
(PR #123, commit 09be16b): raw Darkstore name variants (case/whitespace/prefix)
that normalise to the same (location_id, sku_id[, date]) after ds_lookup
resolution must not produce duplicate rows or double upserts.

The loader creates a Supabase client at import time; dummy env vars are set
before the import so these tests run anywhere with no credentials. All DB
writes are captured on a mocked module-level `sb`.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_KEY", "test-dummy-key")

import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import pytest

import ingest.blinkit_performance_loader as loader

pytestmark = pytest.mark.unit


@pytest.fixture
def fake_sb(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(loader, "sb", fake)
    return fake


def _ds_lookup():
    return {"es my store": "DS_A", "es my store 2": "DS_B"}


def _sku_lookup():
    return {"ITM1": "SKU_1", "ITM2": "SKU_2"}


def _wh_lookup():
    return {"BLR_WH_5397": "WH_P1", "BLR_WH_1873": "WH_P2"}


def _wh_name_lookup():
    return {"BLR B5": "BLR_WH_5397", "BLR B3": "BLR_WH_1873"}


def _last_upsert_payload(fake_sb):
    """The records list passed to the most recent .upsert() call."""
    return fake_sb.table.return_value.upsert.call_args_list[-1][0][0]


def test_wh_ds_mapping_keeps_latest_name_variant_only(fake_sb, monkeypatch):
    monkeypatch.setattr(loader, "build_wh_name_lookup", lambda sb: _wh_name_lookup())

    df = pd.DataFrame([
        {"Darkstore name": "ES My Store",  "Serving warehouse": "BLR B5",
         "data_date": "2026-08-01"},   # older variant of DS_A
        {"Darkstore name": "ES MY STORE", "Serving warehouse": "BLR B3",
         "data_date": "2026-08-03"},   # newest — must win for DS_A
        {"Darkstore name": "ES My Store 2", "Serving warehouse": "BLR B5",
         "data_date": "2026-08-02"},
    ])

    result = loader.update_wh_ds_mapping(df, _ds_lookup(), _wh_lookup(),
                                         {"DS_A": "WH_P1", "DS_B": "WH_P1"})

    assert result["remapped"] == 1
    assert result["unknown_ds"] == set()
    assert result["unknown_wh"] == set()

    updates = [c.args[0] for c in fake_sb.table.return_value.update.call_args_list]
    # Exactly one remap: DS_A -> WH_P2 from the 2026-08-03 row. The older
    # name-variant row must NOT overwrite the mapping back to WH_P1.
    assert updates == [{"parent_location_id": "WH_P2"}]


def test_wh_ds_mapping_updates_distinct_ds_even_when_names_vary(fake_sb, monkeypatch):
    monkeypatch.setattr(loader, "build_wh_name_lookup", lambda sb: _wh_name_lookup())

    df = pd.DataFrame([
        {"Darkstore name": "ES My Store", "Serving warehouse": "BLR B5",
         "data_date": "2026-08-01"},
        {"Darkstore name": "ES My Store 2", "Serving warehouse": "BLR B3",
         "data_date": "2026-08-02"},
    ])

    result = loader.update_wh_ds_mapping(df, _ds_lookup(), _wh_lookup(),
                                         {"DS_A": "WH_P0", "DS_B": "WH_P0"})

    # Two different resolved DS ids — neither is a duplicate of the other.
    assert result["remapped"] == 2


def test_eligibility_dedupes_name_variants_on_resolved_pair(fake_sb):
    df = pd.DataFrame([
        {"Item ID": "ITM1", "Darkstore name": "ES My Store", "data_date": "2026-08-02",
         "Considered for assessment (Y/N)": "Y", "Darkstore remark": ""},
        {"Item ID": "ITM1", "Darkstore name": "ES MY STORE", "data_date": "2026-08-03",
         "Considered for assessment (Y/N)": "Y", "Darkstore remark": ""},
        {"Item ID": "ITM2", "Darkstore name": "ES My Store", "data_date": "2026-08-03",
         "Considered for assessment (Y/N)": "Y", "Darkstore remark": ""},
    ])

    result = loader.update_eligibility(df, _sku_lookup(), _ds_lookup())

    # ITM1's two raw name variants resolve to the same (DS_A, SKU_1) — only the
    # latest-dated one is kept. ITM2 is a genuinely distinct pair.
    assert result["count"] == 2
    assert result["fresh_pairs"] == {("DS_A", "SKU_1"), ("DS_A", "SKU_2")}

    payload = _last_upsert_payload(fake_sb)
    assert len(payload) == 2
    assert {(r["location_id"], r["sku_id"]) for r in payload} == result["fresh_pairs"]


def test_upsert_detail_skips_duplicate_resolved_key(fake_sb):
    df = pd.DataFrame([
        {"Considered for assessment (Y/N)": "Y", "Item ID": "ITM1",
         "Darkstore name": "ES My Store", "data_date": "2026-08-03",
         "download_date": "2026-08-03", "inv_available": True, "orders_n": 5,
         "complaint_orders": 0, "city_val": "Bangalore", "Serving warehouse": "BLR B3"},
        {"Considered for assessment (Y/N)": "Y", "Item ID": "ITM1",
         "Darkstore name": "ES MY STORE", "data_date": "2026-08-03",
         "download_date": "2026-08-03", "inv_available": True, "orders_n": 5,
         "complaint_orders": 0, "city_val": "Bangalore", "Serving warehouse": "BLR B3"},
        {"Considered for assessment (Y/N)": "Y", "Item ID": "ITM1",
         "Darkstore name": "ES My Store", "data_date": "2026-08-04",
         "download_date": "2026-08-04", "inv_available": True, "orders_n": 7,
         "complaint_orders": 0, "city_val": "Bangalore", "Serving warehouse": "BLR B3"},
    ])

    result = loader.upsert_detail(df, _sku_lookup(), _ds_lookup())

    # Rows 1+2 are the same (2026-08-03, DS_A, SKU_1) via name variants — the
    # duplicate is skipped instead of double-upserting the conflict key. Row 3
    # has a different data_date and is kept.
    assert result["inserted"] == 2
    assert result["skipped"] == 1
    assert result["unknown_ds"] == set()

    payload = _last_upsert_payload(fake_sb)
    assert len(payload) == 2
    keys = {(r["data_date"], r["location_id"], r["sku_id"]) for r in payload}
    assert keys == {("2026-08-03", "DS_A", "SKU_1"), ("2026-08-04", "DS_A", "SKU_1")}
