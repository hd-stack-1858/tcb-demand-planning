"""
Bootstrap sku_cogs_lots for existing Amazon FBA SOH.

Seeds synthetic lot rows (assembled_at=2025-12-01, unit_cogs=CATALOG_COGS)
for each sku with current Amazon FBA sellable stock.

SOH figures from Amazon Seller Central (2 May 2026, 8:30 PM IST).
Amazon has a single FBA WH — location resolved from partner_locations at runtime.
ASIN -> sku_id resolved from sku_channel_ids.platform_pid at runtime.

Run once on prod after migration 009:
  python setup/seed_amazon_partner_lots.py --env prod
  python setup/seed_amazon_partner_lots.py --env dev
"""
import os, sys, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

CATALOG_COGS: dict[str, float] = {
    "TCB001": 441.3,  "TCB002": 441.3,
    "TCB003": 700.8,  "TCB004": 700.8,
    "TCB005": 472.7,  "TCB006": 472.7,
    "TCB007": 609.2,
    "TCB008": 276.3,
    "TCB009": 334.2,  "TCB009_1": 334.2,
    "TCB010": 840.2,
    "TCB011": 297.3,
    "TCB012": 305.5,
}

BASELINE_DATE = "2025-12-01"

# Amazon FBA SOH (2 May 2026) — only ASINs with sellable qty > 0
AMAZON_SOH: dict[str, int] = {
    "B0GRHC4YSZ": 13,
    "B0GHNGB1JD": 16,
    "B0GFD212V2": 19,
    "B0FTXGNPCS": 15,
    "B0G2M4M5GX": 18,
    "B0G33M7YLC": 17,
    "B0FTX8ZNS4": 13,
    "B0FTXB78VP":  4,
}


def main(env: str):
    os.environ["TCB_ENV"] = env
    from tcb.db import get_client
    db = get_client()

    # AZ channel_id
    az = db.table("channels").select("channel_id").eq("code", "AZ").single().execute().data
    az_channel_id = az["channel_id"]
    print(f"AZ channel_id = {az_channel_id}")

    # ── 1. ASIN -> sku_id via sku_channel_ids.platform_pid ───────────────────
    # sku_channel_ids uses "AZ" as channel_code for Amazon (FBA and FBM share same listings)
    pid_rows = (db.table("sku_channel_ids")
                  .select("sku_id, platform_pid")
                  .eq("channel_code", "AZ")
                  .execute().data)

    asin_to_sku: dict[str, str] = {r["platform_pid"]: r["sku_id"]
                                    for r in pid_rows if r.get("platform_pid")}

    print("\nASIN -> SKU (AZ channel, from prod):")
    for asin, sku_id in sorted(asin_to_sku.items()):
        soh = AMAZON_SOH.get(asin, 0)
        print(f"  {asin}  ->  {sku_id}  (SOH={soh})")

    # ── 2. Single Amazon FBA WH location ─────────────────────────────────────
    loc_rows = (db.table("partner_locations")
                  .select("location_id, name, code")
                  .eq("channel_id", az_channel_id)
                  .eq("is_active", True)
                  .execute().data)

    if not loc_rows:
        print("ERROR: no active partner_locations for AZ — run migration 009 first")
        return

    if len(loc_rows) > 1:
        print(f"NOTE: {len(loc_rows)} Amazon WH locations found — using first one")
    wh = loc_rows[0]
    az_loc_id = wh["location_id"]
    print(f"\nAmazon FBA WH: location_id={az_loc_id}  {wh['name']} ({wh['code']})")

    # ── 3. Idempotency check ──────────────────────────────────────────────────
    existing = (db.table("sku_cogs_lots")
                  .select("sku_id")
                  .eq("channel_id", az_channel_id)
                  .eq("partner_location_id", az_loc_id)
                  .execute().data)
    existing_skus = {r["sku_id"] for r in existing}

    # ── 4. Build insert records ───────────────────────────────────────────────
    to_insert = []
    warnings  = []

    print(f"\n{'ASIN':<14} {'SKU':<12} {'qty':>5} {'cogs':>8}  status")
    print("-" * 50)

    for asin, qty in sorted(AMAZON_SOH.items()):
        sku_id = asin_to_sku.get(asin)
        if not sku_id:
            warnings.append(f"ASIN {asin} not in sku_channel_ids — skipped")
            continue

        cogs = CATALOG_COGS.get(sku_id)
        if cogs is None:
            warnings.append(f"no CATALOG_COGS for {sku_id} — skipped")
            continue

        if sku_id in existing_skus:
            print(f"{asin:<14} {sku_id:<12} {qty:>5} {cogs:>8.2f}  SKIP (exists)")
            continue

        to_insert.append({
            "sku_id":              sku_id,
            "channel_id":          az_channel_id,
            "partner_location_id": az_loc_id,
            "assembled_at":        BASELINE_DATE,
            "unit_cogs":           cogs,
            "qty_assembled":       qty,
            "qty_remaining":       qty,
        })
        print(f"{asin:<14} {sku_id:<12} {qty:>5} {cogs:>8.2f}  INSERT")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  {w}")

    if not to_insert:
        print("\nNothing to insert.")
        return

    db.table("sku_cogs_lots").insert(to_insert).execute()
    print(f"\nInserted {len(to_insert)} Amazon FBA partner lot row(s).")
    print("\nVerify:")
    print("  SELECT sku_id, partner_location_id, assembled_at, unit_cogs,")
    print("         qty_assembled, qty_remaining")
    print(f"  FROM sku_cogs_lots WHERE channel_id = {az_channel_id}")
    print("  ORDER BY sku_id;")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="prod", choices=["dev", "prod"])
    args = parser.parse_args()
    main(args.env)
