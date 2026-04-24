"""
Seed script: populates sku_pricing and sku_channel_tp tables.
Run after 02_seed_data.py.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tcb.db import get_client

db = get_client()

def upsert(table, rows, conflict_col):
    for row in rows:
        db.table(table).upsert(row, on_conflict=conflict_col).execute()
    print(f"  {table}: {len(rows)} rows upserted")

# ── 1. SKU PRICING ────────────────────────────────────────────
# Effective-dated. Multiple rows per SKU when MRP or SP changes.
# TCB009_1 launched March 2026 (not Oct 2025).
print("Seeding sku_pricing...")

pricing_rows = [
    # SKUs with unchanged MRP + SP since launch (1-Oct-2025)
    {"sku_id": "TCB001",   "effective_date": "2025-10-01", "mrp": 1595, "sp": 1299, "notes": "Launch pricing"},
    {"sku_id": "TCB002",   "effective_date": "2025-10-01", "mrp": 1595, "sp": 1299, "notes": "Launch pricing"},
    {"sku_id": "TCB003",   "effective_date": "2025-10-01", "mrp": 2495, "sp": 1999, "notes": "Launch pricing"},
    {"sku_id": "TCB004",   "effective_date": "2025-10-01", "mrp": 2495, "sp": 1999, "notes": "Launch pricing"},
    {"sku_id": "TCB005",   "effective_date": "2025-10-01", "mrp": 1795, "sp": 1499, "notes": "Launch pricing"},
    {"sku_id": "TCB006",   "effective_date": "2025-10-01", "mrp": 1795, "sp": 1499, "notes": "Launch pricing"},
    {"sku_id": "TCB007",   "effective_date": "2025-10-01", "mrp": 1995, "sp": 1799, "notes": "Launch pricing"},
    {"sku_id": "TCB010",   "effective_date": "2025-10-01", "mrp": 3295, "sp": 2499, "notes": "Launch pricing"},
    {"sku_id": "TCB011",   "effective_date": "2025-10-01", "mrp": 1095, "sp":  899, "notes": "Launch pricing"},
    {"sku_id": "TCB012",   "effective_date": "2025-10-01", "mrp": 1195, "sp":  949, "notes": "Launch pricing"},
    # TCB008: SP increased from 849 to 949 on 10-Jan-2026
    {"sku_id": "TCB008",   "effective_date": "2025-10-01", "mrp":  995, "sp":  849, "notes": "Launch pricing"},
    {"sku_id": "TCB008",   "effective_date": "2026-01-10", "mrp":  995, "sp":  949, "notes": "SP increased from 849"},
    # TCB009: SP increased from 849 to 949 on 11-Mar-2026
    {"sku_id": "TCB009",   "effective_date": "2025-10-01", "mrp":  995, "sp":  849, "notes": "Launch pricing"},
    {"sku_id": "TCB009",   "effective_date": "2026-03-11", "mrp":  995, "sp":  949, "notes": "SP increased from 849"},
    # TCB009_1: launched March 2026 (replacement for TCB009)
    {"sku_id": "TCB009_1", "effective_date": "2026-03-01", "mrp":  995, "sp":  949, "notes": "Launch pricing (Mar 2026 replacement for TCB009)"},
]

upsert("sku_pricing", pricing_rows, "sku_id,effective_date")

# ── 2. SKU CHANNEL TP ─────────────────────────────────────────
# TP channels: FNP, PEEKO, FC, KIDDO, OZI only.
# Multiple rows per SKU×channel when TP changes.
# Channel go-live dates: FnP=Dec-2025, Peeko=Dec-2025, FC=Feb-2026, Kiddo=Apr-2026, Ozi=Oct-2025(some SKUs)/Feb-2026
print("Seeding sku_channel_tp...")

tp_rows = [

    # ── FnP ──────────────────────────────────────────────────
    {"sku_id": "TCB001", "channel_code": "FNP", "effective_date": "2025-12-01", "transfer_price":  780.00, "notes": "Launch TP"},
    {"sku_id": "TCB002", "channel_code": "FNP", "effective_date": "2025-12-01", "transfer_price":  780.00, "notes": "Launch TP"},
    {"sku_id": "TCB003", "channel_code": "FNP", "effective_date": "2025-12-01", "transfer_price": 1200.00, "notes": "Launch TP"},
    {"sku_id": "TCB004", "channel_code": "FNP", "effective_date": "2025-12-01", "transfer_price": 1200.00, "notes": "Launch TP"},
    {"sku_id": "TCB005", "channel_code": "FNP", "effective_date": "2025-12-01", "transfer_price":  900.00, "notes": "Launch TP"},
    {"sku_id": "TCB006", "channel_code": "FNP", "effective_date": "2025-12-01", "transfer_price":  900.00, "notes": "Launch TP"},
    {"sku_id": "TCB008", "channel_code": "FNP", "effective_date": "2025-12-01", "transfer_price":  509.00, "notes": "Launch TP"},
    {"sku_id": "TCB008", "channel_code": "FNP", "effective_date": "2026-01-10", "transfer_price":  570.00, "notes": "TP increased from 509"},

    # ── Peeko ─────────────────────────────────────────────────
    {"sku_id": "TCB001",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price":  844.35, "notes": "Launch TP"},
    {"sku_id": "TCB002",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price":  844.35, "notes": "Launch TP"},
    {"sku_id": "TCB003",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price": 1299.35, "notes": "Launch TP"},
    {"sku_id": "TCB004",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price": 1299.35, "notes": "Launch TP"},
    {"sku_id": "TCB005",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price":  974.35, "notes": "Launch TP"},
    {"sku_id": "TCB006",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price":  974.35, "notes": "Launch TP"},
    {"sku_id": "TCB007",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price": 1169.35, "notes": "Launch TP"},
    {"sku_id": "TCB008",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price":  551.85, "notes": "Launch TP"},
    {"sku_id": "TCB008",   "channel_code": "PEEKO", "effective_date": "2026-01-10", "transfer_price":  616.85, "notes": "TP increased from 551.85"},
    {"sku_id": "TCB009",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price":  551.85, "notes": "Launch TP"},
    {"sku_id": "TCB009",   "channel_code": "PEEKO", "effective_date": "2026-03-11", "transfer_price":  616.85, "notes": "TP increased from 551.85"},
    {"sku_id": "TCB009_1", "channel_code": "PEEKO", "effective_date": "2026-03-01", "transfer_price":  616.85, "notes": "Launch TP (Mar 2026)"},
    {"sku_id": "TCB010",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price": 1624.35, "notes": "Launch TP"},
    {"sku_id": "TCB011",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price":  584.35, "notes": "Launch TP"},
    {"sku_id": "TCB012",   "channel_code": "PEEKO", "effective_date": "2025-12-01", "transfer_price":  616.85, "notes": "Launch TP"},

    # ── First Cry ─────────────────────────────────────────────
    {"sku_id": "TCB001",   "channel_code": "FC", "effective_date": "2026-02-01", "transfer_price":  844.33, "notes": "Launch TP"},
    {"sku_id": "TCB002",   "channel_code": "FC", "effective_date": "2026-02-01", "transfer_price":  844.35, "notes": "Launch TP"},
    {"sku_id": "TCB003",   "channel_code": "FC", "effective_date": "2026-02-01", "transfer_price": 1299.35, "notes": "Launch TP"},
    {"sku_id": "TCB004",   "channel_code": "FC", "effective_date": "2026-02-01", "transfer_price": 1299.35, "notes": "Launch TP"},
    {"sku_id": "TCB005",   "channel_code": "FC", "effective_date": "2026-02-01", "transfer_price":  974.35, "notes": "Launch TP"},
    {"sku_id": "TCB006",   "channel_code": "FC", "effective_date": "2026-02-01", "transfer_price":  974.35, "notes": "Launch TP"},
    {"sku_id": "TCB009_1", "channel_code": "FC", "effective_date": "2026-03-01", "transfer_price":  616.85, "notes": "Launch TP (Mar 2026)"},
    {"sku_id": "TCB010",   "channel_code": "FC", "effective_date": "2026-02-01", "transfer_price": 1624.35, "notes": "Launch TP"},
    {"sku_id": "TCB011",   "channel_code": "FC", "effective_date": "2026-02-01", "transfer_price":  584.35, "notes": "Launch TP"},
    {"sku_id": "TCB012",   "channel_code": "FC", "effective_date": "2026-02-01", "transfer_price":  616.82, "notes": "Launch TP"},

    # ── Kiddo ─────────────────────────────────────────────────
    {"sku_id": "TCB001", "channel_code": "KIDDO", "effective_date": "2026-04-01", "transfer_price":  870.00, "notes": "Launch TP"},
    {"sku_id": "TCB004", "channel_code": "KIDDO", "effective_date": "2026-04-01", "transfer_price": 1350.00, "notes": "Launch TP"},
    {"sku_id": "TCB006", "channel_code": "KIDDO", "effective_date": "2026-04-01", "transfer_price": 1010.00, "notes": "Launch TP"},
    {"sku_id": "TCB008", "channel_code": "KIDDO", "effective_date": "2026-04-01", "transfer_price":  640.00, "notes": "Launch TP"},
    {"sku_id": "TCB012", "channel_code": "KIDDO", "effective_date": "2026-04-01", "transfer_price":  640.00, "notes": "Launch TP"},

    # ── Ozi ───────────────────────────────────────────────────
    {"sku_id": "TCB001",   "channel_code": "OZI", "effective_date": "2026-02-01", "transfer_price":  974.25, "notes": "Launch TP"},
    {"sku_id": "TCB002",   "channel_code": "OZI", "effective_date": "2026-02-01", "transfer_price":  974.25, "notes": "Launch TP"},
    {"sku_id": "TCB003",   "channel_code": "OZI", "effective_date": "2026-02-01", "transfer_price": 1349.25, "notes": "Launch TP"},
    {"sku_id": "TCB004",   "channel_code": "OZI", "effective_date": "2026-02-01", "transfer_price": 1349.25, "notes": "Launch TP"},
    {"sku_id": "TCB005",   "channel_code": "OZI", "effective_date": "2026-02-01", "transfer_price": 1124.25, "notes": "Launch TP"},
    {"sku_id": "TCB006",   "channel_code": "OZI", "effective_date": "2026-02-01", "transfer_price": 1124.25, "notes": "Launch TP"},
    {"sku_id": "TCB007",   "channel_code": "OZI", "effective_date": "2026-02-01", "transfer_price": 1349.25, "notes": "Launch TP"},
    {"sku_id": "TCB008",   "channel_code": "OZI", "effective_date": "2025-10-01", "transfer_price":  636.75, "notes": "Launch TP"},
    {"sku_id": "TCB008",   "channel_code": "OZI", "effective_date": "2026-01-10", "transfer_price":  711.75, "notes": "TP increased from 636.75"},
    {"sku_id": "TCB009",   "channel_code": "OZI", "effective_date": "2025-10-01", "transfer_price":  636.75, "notes": "Launch TP"},
    {"sku_id": "TCB009",   "channel_code": "OZI", "effective_date": "2026-03-11", "transfer_price":  711.75, "notes": "TP increased from 636.75"},
    {"sku_id": "TCB009_1", "channel_code": "OZI", "effective_date": "2026-03-01", "transfer_price":  711.75, "notes": "Launch TP (Mar 2026)"},
]

upsert("sku_channel_tp", tp_rows, "sku_id,channel_code,effective_date")

print("\nPricing seed complete.")
