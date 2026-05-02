"""
Bootstrap sku_cogs_lots for existing Blinkit SOH.

Seeds synthetic lot rows (assembled_at=2025-12-01, unit_cogs=CATALOG_COGS)
for each (sku_id, partner_location_id) with current Blinkit sellable stock.

SOH figures extracted from Blinkit inventory report (May 2026).
Mappings resolved fresh from DB at runtime (item_id via platform_pid_additional,
facility_id via partner_locations.external_id).

Run once on prod (and optionally dev) after migration 009:
  python setup/seed_blinkit_partner_lots.py --env prod
  python setup/seed_blinkit_partner_lots.py --env dev
"""
import os, sys, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Historical baseline COGS (Himanshu, May 2026) — pre-app assembly batches
CATALOG_COGS: dict[str, float] = {
    "TCB001": 441.3,  "TCB002": 441.3,
    "TCB003": 700.8,  "TCB004": 700.8,
    "TCB005": 472.7,  "TCB006": 472.7,
    "TCB008": 276.3,
    "TCB009_1": 334.2,
    "TCB010":   840.2,
    "TCB011":   297.3,
    "TCB012":   305.5,
}

BASELINE_DATE = "2025-12-01"

# Blinkit SOH from May 2026 inventory report: {item_id: {facility_id: sellable_qty}}
# item_id  = Blinkit "Item ID" column = sku_channel_ids.platform_pid_additional
# facility_id = Blinkit "Warehouse Facility ID" = partner_locations.external_id
BLINKIT_SOH: dict[int, dict[int, int]] = {
    10271993: {264: 43, 2010: 7,  2576: 17},                           # TCB001
    10271630: {264: 24, 2010: 11, 2576: 13, 5096: 9},                 # TCB002
    10272017: {264: 10, 1873: 13, 2010: 3,  2576: 21, 5096: 50, 5397: 20},  # TCB004
    10272588: {1873: 32, 2576: 34, 3201: 4,  3262: 8,  5096: 59, 5397: 18}, # TCB006
    10272608: {1873: 27, 3201: 1,  3262: 16, 5397: 10},               # TCB003
    10272641: {1873: 23, 3201: 1,  3262: 6,  5397: 12},               # TCB005
    10273430: {1873: 8,  5397: 28},                                     # TCB008
    10274008: {1873: 6,  5397: 16},                      # TCB009_1 (both variants share this item_id)
    10282817: {1873: 23, 5397: 27},                                     # TCB011
    10282820: {1873: 46, 5397: 22},                                     # TCB012
    10285562: {1873: 1},                                                 # TCB010
}


def main(env: str):
    os.environ["TCB_ENV"] = env
    from tcb.db import get_client
    db = get_client()

    # BLK channel_id
    blk = db.table("channels").select("channel_id").eq("code", "BLK").single().execute().data
    blk_channel_id = blk["channel_id"]
    print(f"BLK channel_id = {blk_channel_id}")

    # ── 1. item_id -> sku_id via sku_channel_ids.platform_pid_additional ──────
    pid_rows = (db.table("sku_channel_ids")
                  .select("sku_id, platform_pid_additional")
                  .eq("channel_code", "BLK")
                  .execute().data)

    item_to_sku: dict[int, str] = {}
    for r in pid_rows:
        pid = r.get("platform_pid_additional")
        if not pid:
            continue
        try:
            iid = int(pid)
        except (ValueError, TypeError):
            continue  # skip non-numeric values like 'Not listed'
        # Prefer TCB009_1 over TCB009 when both share the same item_id
        if iid not in item_to_sku or r["sku_id"] == "TCB009_1":
            item_to_sku[iid] = r["sku_id"]

    print("\nItem ID -> SKU (BLK channel, from prod):")
    for iid, sku_id in sorted(item_to_sku.items()):
        print(f"  {iid}  ->  {sku_id}")

    # ── 2. facility_id -> location_id via partner_locations.external_id ───────
    loc_rows = (db.table("partner_locations")
                  .select("location_id, name, external_id")
                  .eq("channel_id", blk_channel_id)
                  .execute().data)

    fac_to_loc: dict[int, int] = {}
    loc_name:   dict[int, str] = {}
    for r in loc_rows:
        ext = r.get("external_id")
        if ext:
            try:
                fid = int(ext)
                fac_to_loc[fid] = r["location_id"]
                loc_name[fid]   = r["name"]
            except (ValueError, TypeError):
                pass

    print("\nFacility ID -> location_id (from prod):")
    for fid, lid in sorted(fac_to_loc.items()):
        print(f"  {fid:>6}  ->  loc_id={lid}  {loc_name.get(fid, '?')}")

    # ── 3. Check existing BLK lots (idempotency) ──────────────────────────────
    existing = (db.table("sku_cogs_lots")
                  .select("sku_id, partner_location_id")
                  .eq("channel_id", blk_channel_id)
                  .execute().data)
    existing_keys = {(r["sku_id"], r["partner_location_id"]) for r in existing}

    # ── 4. Build insert records ───────────────────────────────────────────────
    to_insert = []
    warnings  = []

    print(f"\n{'SKU':<12} {'loc_id':>6} {'fac_id':>8} {'qty':>5} {'cogs':>8}  status")
    print("-" * 55)

    for item_id, fac_dict in sorted(BLINKIT_SOH.items()):
        sku_id = item_to_sku.get(item_id)
        if not sku_id:
            warnings.append(f"item_id {item_id} not in sku_channel_ids — skipped")
            continue

        cogs = CATALOG_COGS.get(sku_id)
        if cogs is None:
            warnings.append(f"no CATALOG_COGS for {sku_id} — skipped")
            continue

        for fac_id, qty in sorted(fac_dict.items()):
            loc_id = fac_to_loc.get(fac_id)
            if loc_id is None:
                warnings.append(f"facility_id {fac_id} not in partner_locations — skipped")
                continue

            key = (sku_id, loc_id)
            if key in existing_keys:
                print(f"{sku_id:<12} {loc_id:>6} {fac_id:>8} {qty:>5} {cogs:>8.2f}  SKIP (exists)")
                continue

            to_insert.append({
                "sku_id":              sku_id,
                "channel_id":          blk_channel_id,
                "partner_location_id": loc_id,
                "assembled_at":        BASELINE_DATE,
                "unit_cogs":           cogs,
                "qty_assembled":       qty,
                "qty_remaining":       qty,
            })
            print(f"{sku_id:<12} {loc_id:>6} {fac_id:>8} {qty:>5} {cogs:>8.2f}  INSERT")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  {w}")

    if not to_insert:
        print("\nNothing to insert.")
        return

    db.table("sku_cogs_lots").insert(to_insert).execute()
    print(f"\nInserted {len(to_insert)} Blinkit partner lot row(s).")
    print("\nVerify:")
    print("  SELECT sku_id, partner_location_id, assembled_at, unit_cogs,")
    print("         qty_assembled, qty_remaining")
    print("  FROM sku_cogs_lots WHERE channel_id = 4 ORDER BY sku_id, partner_location_id;")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="prod", choices=["dev", "prod"])
    args = parser.parse_args()
    main(args.env)
