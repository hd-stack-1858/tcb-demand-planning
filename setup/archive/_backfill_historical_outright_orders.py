"""
One-shot backfill: orders rows for historical OUTRIGHT invoices to Peeko/Kiddo
that predate the warehouse app implementation.

These dispatches are already reflected in the April 25 opening stock seed —
we only need orders rows for MIS visibility. No stock/lot adjustments.
Safe to re-run: skips rows that already exist.
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ['TCB_ENV'] = 'prod'
from tcb.db import get_client
from tcb.geo import city_to_state

db = get_client()

PEEKO = 7
KIDDO = 9

INVOICES = [
    {
        "channel_id":   KIDDO,
        "channel_code": "KIDDO",
        "reference":    "GT_26-27_006",
        "order_date":   "2026-04-16",
        "city":         "Noida",
        "lines": [
            ("TCB001", 2),
            ("TCB004", 1),
            ("TCB006", 1),
            ("TCB008", 2),
            ("TCB012", 2),
        ],
    },
    {
        "channel_id":   PEEKO,
        "channel_code": "PEEKO",
        "reference":    "GT/25-26/025",
        "order_date":   "2026-03-12",
        "city":         "Bengaluru",
        "lines": [
            ("TCB001", 2),
            ("TCB002", 2),
            ("TCB008", 2),
            ("TCB009_1", 1),
            ("TCB010",  2),
            ("TCB011",  2),
            ("TCB012",  2),
        ],
    },
    {
        "channel_id":   PEEKO,
        "channel_code": "PEEKO",
        "reference":    "GT/25-26/013",
        "order_date":   "2026-01-16",
        "city":         "Bengaluru",
        "lines": [
            ("TCB001", 2),
            ("TCB002", 2),
            ("TCB003", 2),
            ("TCB004", 2),
            ("TCB005", 2),
            ("TCB006", 2),
            ("TCB011", 2),
        ],
    },
    {
        "channel_id":   PEEKO,
        "channel_code": "PEEKO",
        "reference":    None,           # invoice number unknown
        "order_date":   "2025-12-15",
        "city":         "Bengaluru",
        "lines": [
            ("TCB001",   1),
            ("TCB002",   1),
            ("TCB003",   1),
            ("TCB004",   1),
            ("TCB005",   1),
            ("TCB006",   1),
            ("TCB007",   1),
            ("TCB008",   1),
            ("TCB009_1", 1),            # TCB009 in invoice = TCB009_1 in DB
        ],
    },
]


def get_unit_cogs(sku_id, date_str):
    """Latest ASSEMBLY unit_cogs recorded on or before date_str. Returns 0 if none."""
    rows = (db.table("sku_inventory_transactions")
              .select("unit_cogs")
              .eq("sku_id", sku_id)
              .eq("type", "ASSEMBLY")
              .gt("unit_cogs", 0)
              .lte("created_at", date_str + "T23:59:59+05:30")
              .order("created_at", desc=True)
              .limit(1).execute().data)
    return float(rows[0]["unit_cogs"]) if rows else 0.0


inserted = skipped = warned = 0

for inv in INVOICES:
    ch_id    = inv["channel_id"]
    ch_code  = inv["channel_code"]
    ref      = inv["reference"]
    date_str = inv["order_date"]
    city     = inv["city"]
    state    = city_to_state(city)
    print(f"\n--- {ch_code}  {ref or '(no ref)'}  {date_str} ---")

    for sku_id, qty in inv["lines"]:
        # Idempotency check
        if ref:
            existing = (db.table("orders")
                          .select("order_id")
                          .eq("platform_order_id", ref)
                          .eq("channel_id", ch_id)
                          .eq("sku_id", sku_id)
                          .execute().data)
        else:
            existing = (db.table("orders")
                          .select("order_id")
                          .eq("channel_id", ch_id)
                          .eq("sku_id", sku_id)
                          .eq("order_date", date_str)
                          .eq("fulfillment_type", "OUTRIGHT")
                          .execute().data)
        if existing:
            print(f"  SKIP   {sku_id}")
            skipped += 1
            continue

        # SP + MRP at order date
        pricing = (db.table("sku_pricing")
                     .select("sp, mrp")
                     .eq("sku_id", sku_id)
                     .lte("effective_date", date_str)
                     .order("effective_date", desc=True)
                     .limit(1).execute().data)
        if not pricing or not pricing[0].get("sp"):
            print(f"  WARN   {sku_id}  no SP in sku_pricing — skipping")
            warned += 1
            continue
        sp  = float(pricing[0]["sp"])
        mrp = float(pricing[0]["mrp"]) if pricing[0].get("mrp") else None
        disc = round((mrp - sp) / mrp * 100, 2) if mrp and mrp > 0 else None

        # TP at order date
        tp_row = (db.table("sku_channel_tp")
                    .select("transfer_price")
                    .eq("sku_id", sku_id)
                    .eq("channel_code", ch_code)
                    .lte("effective_date", date_str)
                    .order("effective_date", desc=True)
                    .limit(1).execute().data)
        tp = float(tp_row[0]["transfer_price"]) if tp_row else None

        unit_cogs = get_unit_cogs(sku_id, date_str)

        db.table("orders").insert({
            "channel_id":         ch_id,
            "order_date":         date_str,
            "sku_id":             sku_id,
            "quantity":           qty,
            "mrp":                mrp,
            "selling_price":      sp,
            "gross_value":        round(qty * sp, 2),
            "discount_pct":       disc,
            "cogs":               round(qty * unit_cogs, 2),
            "transfer_price":     tp,
            "fulfillment_type":   "OUTRIGHT",
            "platform_order_id":  ref,
            "status":             "FULFILLED",
            "source_file":        "backfill",
            "city":               city,
            "state":              state,
            "lot_cogs_finalized": True,
        }).execute()
        print(f"  INSERT {sku_id:10s}  qty={qty}  sp={sp}  tp={tp}  cogs={round(qty * unit_cogs, 2)}")
        inserted += 1

print(f"\nDone: {inserted} inserted, {skipped} skipped, {warned} warned")
