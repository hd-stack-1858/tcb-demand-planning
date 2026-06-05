"""
Monthly FnP CDA reconciliation — reconcile_fnp_orders.py

Reads ALL cda-export_*.xls* files from data/fnp/manual/ (accumulates history)
and runs three checks:

  [A] Payment risk — DB FnP orders older than the safe window (last 7 days of
      the latest report's period) that do NOT appear in any CDA file. These
      were shipped but FnP has no delivery record — investigate whether payment
      is coming.

  [B] App miss — ORDER NOs in the latest CDA file not found in DB at all.
      These were delivered by FnP but never recorded. Punch in manually.

  [C] Enrichment — DB FnP orders where city or state is NULL, filled from
      CDA data (via pincode lookup).

Design notes:
  - All CDA files are loaded on every run so that an order appearing in the
    April file is not re-flagged as missing when running the May reconciliation.
  - The "latest" CDA file (by period end date in filename) drives the cutoff:
      cutoff = period_end - SAFE_WINDOW_DAYS + 1
    Orders with order_date >= cutoff are exempt (may still be in transit).
    Orders beyond the latest period end (i.e. next month's orders) are also
    exempt — no point checking June orders against a May report.
  - Check is at ORDER NO level (not order × SKU). A multi-SKU order sharing
    one ORDER NO is "found" if that ORDER NO appears in any CDA file.
  - SALE_RETURN and RTO orders are excluded from [A] — FnP doesn't pay for
    returned orders, so their absence from CDA is expected.

Usage:
  python ingest/reconcile_fnp_orders.py [--env dev|prod] [--dry-run]

File placement:
  Place each new monthly CDA file in data/fnp/manual/ with the filename format:
  cda-export_1May 2026 to 31May 2026.xls
  The script picks up all files in that folder automatically.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

# Windows console defaults to cp1252; force UTF-8 so Unicode output works.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FNP_CHANNEL_ID  = 5
SAFE_WINDOW_DAYS = 7   # last N days of period_end are exempt from payment risk
CDA_FOLDER      = Path(__file__).parent.parent / "data" / "fnp" / "manual"


# ── Filename parsing ───────────────────────────────────────────────────────────

def _parse_period_end(fname: str) -> date | None:
    """
    Extract the period end date from a CDA filename.
    Handles both:
      'cda-export_1May 2026 to 31May 2026.xls'   → 2026-05-31
      'cda-export_1Dec 2025 to 30Apr 2026.xls'   → 2026-04-30
    """
    m = re.search(r'to (\d{1,2})([A-Za-z]{3,9}) (\d{4})', fname, re.IGNORECASE)
    if not m:
        return None
    day_str, month_str, year_str = m.groups()
    # Try abbreviated (3-letter) then full month name
    for fmt in ("%d%b %Y", "%d%B %Y"):
        try:
            return datetime.strptime(f"{day_str}{month_str} {year_str}", fmt).date()
        except ValueError:
            continue
    return None


# ── CDA file loading ───────────────────────────────────────────────────────────

def _pincode_str(raw) -> str | None:
    """Normalise a PIN CODE cell (may be float like 110036.0) to zero-padded string."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        return str(int(float(raw))).zfill(6)
    except (ValueError, TypeError):
        s = str(raw).strip()
        return s if s.isdigit() else None


def _load_all_cda_files(folder: Path) -> tuple[dict[str, dict], date | None, set[str]]:
    """
    Load all cda-export_*.xls* files from folder.

    Returns:
      accumulated      — {order_no: row_data} from ALL files combined. If the
                         same ORDER NO appears in multiple files (rare), the
                         first occurrence is kept.
      latest_end       — period end date of the most recent file.
      latest_order_nos — set of ORDER NOs from the latest file only (for [B]).
    """
    files = sorted(folder.glob("cda-export_*.xls*"))
    if not files:
        raise FileNotFoundError(
            f"No CDA files found in {folder}.\n"
            "Place cda-export_*.xls files there and re-run."
        )

    # Sort files by their period end date so we know which is "latest"
    file_ends: list[tuple[date, Path]] = []
    for f in files:
        end = _parse_period_end(f.name)
        if end:
            file_ends.append((end, f))
        else:
            logger.warning("Could not parse period end from filename '%s' — skipping.", f.name)

    if not file_ends:
        raise RuntimeError("No CDA files with parseable period-end dates found.")

    file_ends.sort(key=lambda x: x[0])
    latest_end, latest_file = file_ends[-1]

    accumulated: dict[str, dict] = {}

    for _end, f in file_ends:
        logger.info("Loading CDA file: %s (period end: %s)", f.name, _end)
        df = pd.read_excel(f, dtype=str)
        df["ORDER NO"] = df["ORDER NO"].astype(str).str.strip()
        df["PIN CODE"] = df["PIN CODE"].apply(_pincode_str)

        loaded = 0
        for _, row in df.iterrows():
            order_no = str(row["ORDER NO"]).strip()
            if not order_no or order_no.lower() == "nan":
                continue
            if order_no not in accumulated:
                accumulated[order_no] = {
                    "city":         str(row.get("CITY", "") or "").strip().title() or None,
                    "pincode":      row.get("PIN CODE"),
                    "product_id":   str(row.get("PRODUCT_ID", "") or "").strip() or None,
                    "product_name": str(row.get("PRODUCT_NAME", "") or "").strip() or None,
                    "accepted_date": str(row.get("ACCEPTED DATE", "") or "").strip() or None,
                    "source_file":  f.name,
                }
                loaded += 1
        logger.info("  Loaded %d new order(s) from %s (total accumulated: %d)",
                    loaded, f.name, len(accumulated))

    # Latest file order nos (for Check B)
    df_latest = pd.read_excel(latest_file, dtype=str)
    df_latest["ORDER NO"] = df_latest["ORDER NO"].astype(str).str.strip()
    latest_order_nos = {
        s for s in df_latest["ORDER NO"].tolist()
        if s and s.lower() != "nan"
    }

    logger.info("CDA total: %d unique order(s) across %d file(s). Latest period end: %s",
                len(accumulated), len(file_ends), latest_end)
    return accumulated, latest_end, latest_order_nos


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _load_db_fnp_orders(db) -> dict[str, list[dict]]:
    """Return {platform_order_id: [db_rows]} for all FnP orders."""
    rows = (
        db.table("orders")
          .select("order_id, platform_order_id, sku_id, status, order_date, city, state")
          .eq("channel_id", FNP_CHANNEL_ID)
          .execute().data
    ) or []
    result: dict[str, list[dict]] = {}
    for r in rows:
        pid = r.get("platform_order_id")
        if pid:
            result.setdefault(pid, []).append(r)
    return result


def _load_fnp_sku_map(db) -> dict[str, str]:
    """Return {platform_pid: sku_id} from sku_channel_ids for FNP."""
    rows = (
        db.table("sku_channel_ids")
          .select("sku_id, platform_pid")
          .eq("channel_code", "FNP")
          .execute().data
    ) or []
    return {
        r["platform_pid"]: r["sku_id"]
        for r in rows
        if r.get("platform_pid") and r["platform_pid"] not in ("Not listed", "NA", "")
    }


# ── Main run ───────────────────────────────────────────────────────────────────

def run(folder: Path = CDA_FOLDER, dry_run: bool = False) -> None:
    from tcb.db import get_client
    db = get_client()

    # Load CDA files
    accumulated, latest_end, latest_order_nos = _load_all_cda_files(folder)
    cda_order_nos = set(accumulated.keys())

    # Cutoff: orders with order_date strictly before this date are expected in CDA
    cutoff = latest_end - timedelta(days=SAFE_WINDOW_DAYS - 1)
    logger.info("Latest period end: %s | Safe window: >= %s | Exempt: > %s",
                latest_end, cutoff, latest_end)

    # Load DB
    db_orders   = _load_db_fnp_orders(db)
    sku_map     = _load_fnp_sku_map(db)
    logger.info("DB: %d unique FnP order nos (%d total rows)",
                len(db_orders), sum(len(v) for v in db_orders.values()))

    # ── [A] Payment risk ──────────────────────────────────────────────────────
    payment_risk: list[dict] = []

    for order_no, db_rows in db_orders.items():
        # Skip returns — FnP doesn't pay for these
        statuses = {r["status"] for r in db_rows}
        if statuses <= {"SALE_RETURN", "RTO"}:
            continue

        dates = sorted(r["order_date"] for r in db_rows if r.get("order_date"))
        if not dates:
            continue
        earliest_date = dates[0]    # YYYY-MM-DD string — lexicographic sort works

        # Exempt: beyond the latest report period (next month's orders)
        if earliest_date > latest_end.isoformat():
            continue

        # Exempt: within the safe window (may still be in transit)
        if earliest_date >= cutoff.isoformat():
            continue

        # Should be in CDA — check
        if order_no not in cda_order_nos:
            payment_risk.append({
                "order_no":   order_no,
                "order_date": earliest_date,
                "sku_ids":    sorted({r["sku_id"] for r in db_rows}),
                "statuses":   sorted(statuses),
            })

    # ── [B] App miss ──────────────────────────────────────────────────────────
    app_miss: list[dict] = []

    for order_no in sorted(latest_order_nos):
        if order_no not in db_orders:
            cda_row = accumulated.get(order_no, {})
            pid      = cda_row.get("product_id")
            sku_id   = sku_map.get(pid) if pid else None
            app_miss.append({
                "order_no":     order_no,
                "product_id":   pid,
                "sku_id":       sku_id or f"? (pid={pid})",
                "product_name": cda_row.get("product_name"),
                "city":         cda_row.get("city"),
                "accepted_date": cda_row.get("accepted_date"),
            })

    # ── [C] Enrichment ────────────────────────────────────────────────────────
    enriched = 0
    try:
        from tcb.geo import pincode_to_city_state
        geo_available = True
    except ImportError:
        geo_available = False
        logger.warning("tcb.geo not available — skipping pincode enrichment.")

    for order_no, cda_row in accumulated.items():
        db_rows = db_orders.get(order_no, [])
        for db_row in db_rows:
            if db_row.get("city") and db_row.get("state"):
                continue

            pincode = cda_row.get("pincode")
            cda_city = cda_row.get("city")

            payload: dict = {}

            if geo_available and pincode:
                city, state = pincode_to_city_state(pincode)
                if not db_row.get("city") and city:
                    payload["city"] = city
                if not db_row.get("state") and state:
                    payload["state"] = state
            elif cda_city and not db_row.get("city"):
                # Fallback: use CDA city directly (no pincode lookup)
                payload["city"] = cda_city

            if not payload:
                continue

            if dry_run:
                logger.info("[DRY-RUN] Enrich %s/%s: %s", order_no, db_row["sku_id"], payload)
            else:
                db.table("orders").update(payload).eq(
                    "order_id", db_row["order_id"]
                ).eq("channel_id", FNP_CHANNEL_ID).execute()
                logger.info("Enriched %s/%s: %s", order_no, db_row["sku_id"], payload)
            enriched += 1

    # ── Print results ─────────────────────────────────────────────────────────
    tag = "  [DRY-RUN — nothing written]" if dry_run else ""

    print()
    if payment_risk:
        print(f"[A] PAYMENT RISK{tag} — {len(payment_risk)} order(s) shipped but NOT in any CDA file")
        print(f"    (order_date before {cutoff} — delivery should have been confirmed by now)")
        print(f"    Action: log in to FnP portal and check delivery status for each order below.")
        print()
        print(f"  {'Order No':<14} {'Date':<12} {'SKU(s)':<16} Status")
        print("  " + "─" * 58)
        for r in sorted(payment_risk, key=lambda x: x["order_date"]):
            print(f"  {r['order_no']:<14} {r['order_date']:<12} "
                  f"{','.join(r['sku_ids']):<16} {'/'.join(r['statuses'])}")
    else:
        print(f"[A] PAYMENT RISK: 0 — all old DB orders appear in CDA (OK)")

    print()
    if app_miss:
        print(f"[B] APP MISS{tag} — {len(app_miss)} order(s) in latest CDA not found in DB")
        print(f"    Action: record each order manually in Warehouse App > Ship Out.")
        print()
        print(f"  {'Order No':<14} {'Date':<12} {'SKU':<10} {'City':<18} Product Name")
        print("  " + "─" * 80)
        for r in app_miss:
            pname = (r["product_name"] or "")[:45]
            print(f"  {r['order_no']:<14} {r['accepted_date'] or '?':<12} "
                  f"{r['sku_id']:<10} {(r['city'] or '?'):<18} {pname}")
    else:
        print(f"[B] APP MISS: 0 — all CDA orders found in DB (OK)")

    print()
    print(f"[C] ENRICHMENT: {enriched} order row(s) updated with city/state from CDA{tag}")

    print()
    print(f"─" * 60)
    print(f"FnP Reconciliation summary{tag}")
    print(f"  CDA files loaded          : {len(list(folder.glob('cda-export_*.xls*')))}")
    print(f"  Accumulated CDA orders    : {len(accumulated)}")
    print(f"  DB FnP orders (unique nos): {len(db_orders)}")
    print(f"  Latest report period end  : {latest_end}")
    print(f"  Safe window (exempt from) : >= {cutoff}  and  > {latest_end}")
    print(f"  [A] Payment risk          : {len(payment_risk)}")
    print(f"  [B] App miss              : {len(app_miss)}")
    print(f"  [C] Enriched rows         : {enriched}")
    print(f"─" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FnP monthly CDA reconciliation: payment risk + app miss + enrichment"
    )
    parser.add_argument("--env",     choices=["dev", "prod"], default="prod")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run all checks but do not write enrichment to DB")
    parser.add_argument("--folder",  default=None,
                        help="Override CDA folder path (default: data/fnp/manual/)")
    args = parser.parse_args()

    os.environ.setdefault("TCB_ENV", args.env)

    folder = Path(args.folder) if args.folder else CDA_FOLDER
    run(folder=folder, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
