"""
K1a audit — verify whether Blinkit SKU returns (recalled stock) correctly
decrement the Blinkit lot, or fall through to the OWN_WH fallback path.

Checks:
1. Any sku_cogs_lots rows for BLK channel with partner_location_id IS NULL
   (real Blinkit TRANSFER_OUT lots should never have a null location — if
   these exist, they were created by return_sku()'s fallback branch).
2. Every RETURN-type sku_inventory_transactions row with from_channel_id=BLK,
   and whether a matching OWN_WH lot was created on the same day with
   fallback COGS (the signature of the bug) instead of the original Blinkit
   lot being decremented.

Run: python setup/archive/_check_blk_return_lot_bug.py --env prod
"""
from __future__ import annotations
import argparse, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", choices=["dev", "prod"], default="prod")
    args = parser.parse_args()
    os.environ["TCB_ENV"] = args.env

    from tcb.db import get_client
    db = get_client()

    ch_rows = db.table("channels").select("code, channel_id").execute().data
    blk_id = next(r["channel_id"] for r in ch_rows if r["code"] == "BLK")
    own_wh_id = next(r["channel_id"] for r in ch_rows if r["code"] == "OWN_WH")

    print(f"env={args.env}  BLK channel_id={blk_id}  OWN_WH channel_id={own_wh_id}\n")

    # 1. Null-location BLK lots (should be zero per design)
    null_loc_lots = (db.table("sku_cogs_lots")
                        .select("lot_id, sku_id, assembled_at, unit_cogs, qty_assembled, qty_remaining")
                        .eq("channel_id", blk_id)
                        .is_("partner_location_id", "null")
                        .execute().data)
    print(f"[1] BLK lots with partner_location_id IS NULL: {len(null_loc_lots)}")
    for r in null_loc_lots:
        print(f"    lot_id={r['lot_id']} sku={r['sku_id']} assembled_at={r['assembled_at']} "
              f"unit_cogs={r['unit_cogs']} qty_assembled={r['qty_assembled']} qty_remaining={r['qty_remaining']}")

    # 2. RETURN txns from BLK
    returns = (db.table("sku_inventory_transactions")
                 .select("txn_id, sku_id, quantity, unit_cogs, created_at, notes")
                 .eq("type", "RETURN")
                 .eq("from_channel_id", blk_id)
                 .order("created_at")
                 .execute().data)
    print(f"\n[2] RETURN transactions from BLK: {len(returns)}")
    for r in returns:
        print(f"    txn_id={r['txn_id']} sku={r['sku_id']} qty={r['quantity']} "
              f"unit_cogs={r['unit_cogs']} created_at={r['created_at']} notes={r['notes']!r}")

    if not returns:
        print("\nNo BLK returns recorded yet — bug cannot have fired. "
              "Confirms code-path risk only (theoretical), not yet realized in prod data.")
        return

    # 3. For each BLK return, check whether a same-day OWN_WH lot was created
    #    at fallback COGS (the bug's signature) vs the BLK lot's qty_remaining
    #    actually dropping.
    skus = sorted({r["sku_id"] for r in returns})
    own_lots = (db.table("sku_cogs_lots")
                  .select("lot_id, sku_id, assembled_at, unit_cogs, qty_assembled, qty_remaining")
                  .eq("channel_id", own_wh_id)
                  .in_("sku_id", skus)
                  .execute().data)
    print(f"\n[3] OWN_WH lots for affected SKUs ({len(own_lots)} rows) — "
          f"look for assembled_at matching a return's created_at date with non-standard unit_cogs:")
    for r in own_lots:
        print(f"    sku={r['sku_id']} assembled_at={r['assembled_at']} unit_cogs={r['unit_cogs']} "
              f"qty_assembled={r['qty_assembled']} qty_remaining={r['qty_remaining']}")


if __name__ == "__main__":
    main()
