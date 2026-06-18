# G2c (WH-level Blinkit COGS finalization) + K1b (lot baseline reset)

## Context

Today (18-Jun-2026) is the last day before the agreed K1b baseline cutoff (lots reset to SOH before 19-Jun). Two things are blocking that cutoff from actually fixing anything long-term:

1. **G2c was never built.** The daily runner still finalizes Blinkit COGS via `finalize_blk_cogs()` (`tcb/inventory.py`), which pools lots at the **state** level (`consume_sor_sale(supply_state=...)`). This was proven wrong by the Pune/Mumbai cross-WH drift bug (Maharashtra orders consuming whichever Maharashtra WH had the oldest lot, regardless of which WH actually served the order). If we reset the K1b baseline tomorrow but keep state-level consumption running daily, the lots will start drifting away from SOH again immediately — the reset would be wasted.
2. **K1b has never been run/applied.** `setup/k1b_lot_baseline.py` exists and prints a diff (DB lot qty vs SOH sellable, with cool-off + in-transit + Bug A adjustments) but doesn't write anything yet, and the diff has never actually been reviewed.

Both need to land together: K1b resets the baseline, G2c is what keeps it accurate from 19-Jun onward by attributing each day's sales to the *exact* WH that served them (via the performance-detail report), not a state pool.

Out of scope for this session (confirmed with Himanshu): K1c (daily lot-vs-SOH monitoring/alerting) and K1d (damaged/lost alert). Those are deferred to a follow-up session — they don't block tomorrow's cutoff and don't write to prod.

**Verified today (not assumed):**
- All 1997 BLK FULFILLED orders in prod have `quantity = 1` — so "Total orders" in performance detail and `quantity` in `orders` are directly comparable, no need to handle multi-unit orders.
- 0 BLK orders currently have `lot_cogs_finalized = False` in prod — G2c starts clean from tomorrow's load, no backlog to catch up.
- `load_blinkit_payout.py` also calls `consume_sor_sale()` (state-level) as the payout backstop — that stays unchanged by design (it's the documented last-resort path for days G2c had to hold).

---

## Step A — Apply migration 024 to dev (WH name sync)

`setup/migrations/024_blinkit_wh_name_sync.sql` renames 5 `partner_locations.name` rows so they exactly match `serving_wh` strings in performance detail. G2c's WH lookup depends on this exact match.

1. Run `python setup/sync_dev_to_prod.py` first (mandatory per CLAUDE.md DB workflow — dev may have drifted).
2. Apply migration 024 to dev via psycopg2 (`DEV_DB_URL` in `.env.dev`).
3. Verify: query dev `partner_locations` for the 5 renamed rows, confirm names now match the `Serving warehouse` strings seen in the latest performance CSV.
4. Leave the migration file as-is for Himanshu to run on prod manually (per dev-first workflow — do not touch prod DDL).

## Step B — K1b: review and apply the lot baseline

1. Run `setup/k1b_lot_baseline.py` against prod (already read-only/dry-run) and present the full diff table in chat.
2. Pause for Himanshu's explicit row-by-row sign-off — no write happens before that. This mirrors the approved K1 design ("no auto-correction ever").
3. Add a new migration `setup/migrations/025_lot_reconciliation_log.sql` creating `lot_reconciliation_log` (sku_id, partner_location_id, old_qty, new_qty, delta, reason, created_at, created_by) — referenced by the original K1b design but never created.
4. Extend `k1b_lot_baseline.py` with an `--apply` mode (or a small new `setup/k1b_apply_baseline.py`) that, for only the rows Himanshu approved: updates the relevant `sku_cogs_lots.qty_remaining` (adjusting the oldest non-cooled-off lot, or inserting a small adjustment lot if cleaner — decide based on what the diff actually shows) and inserts one row per change into `lot_reconciliation_log` with `reason='ONE_TIME_CLEANUP'`.
5. Apply to dev first, verify, then run against prod only after Himanshu's sign-off in chat.
6. Re-run the diff after applying — deltas for approved rows should now be zero.

## Step C — Build G2c in `tcb/inventory.py`

New function `finalize_blk_cogs_wh_level(dry_run: bool = False) -> dict`, replacing `finalize_blk_cogs()` as the daily BLK COGS path. Reuses the existing `_consume_lots_fifo(db, sku_id, channel_id, qty, partner_location_id=...)` helper (already does exact-WH FIFO consumption and raises `ValueError` on insufficient qty — exactly tier-1-only behavior, no state fallback needed).

Algorithm:
1. Pull all BLK `FULFILLED` orders with `lot_cogs_finalized = False`, grouped by `order_date` (catches up any previously-held dates automatically, plus new ones — no separate "held" flag needed since unfinalized rows naturally retry next run).
2. For each `order_date`:
   - If `blinkit_performance_detail` has zero rows for that `data_date` → hold the whole date (performance data missing), collect for one alert.
   - Else group orders by `(sku_id, city)` → `sales_qty`, `order_ids`. Group performance-detail rows for that date by `(sku_id, city, serving_wh)` → counts.
   - For each `(sku_id, city)` bucket: compare `sales_qty` to the summed perf count across all `serving_wh`.
     - Mismatch (≠) → hold this bucket, collect for alert (never partially finalize).
     - Match → for each `serving_wh` with count > 0, resolve `partner_locations.name` (channel=BLK, type=WH) to a `location_id`. If any name doesn't resolve → hold the bucket (WH name drift — alert, this should self-heal once migration 024 is applied/kept in sync).
     - Pre-check `qty_remaining` is sufficient for every WH split *before* consuming any (so a shortfall on the second WH doesn't leave the first WH already decremented) — never partially finalize.
     - Consume each WH's split via `_consume_lots_fifo`, compute the qty-weighted average `unit_cogs` across splits, and stamp every order in the bucket: `cogs = unit_cogs_avg * quantity`, `lot_id` (single lot if only one split/lot was used, else `None`), `lot_cogs_finalized = True`.
3. Return a summary dict (`total`, `finalized`, `held_mismatch`, `held_no_perf_data`, `held_wh_unresolved`) and send one alert email (reuse `automation/email_sender.send_alert`) if anything was held, listing the specific (sku, city, date) buckets — mirrors how G4/G5 failures are already alerted in `daily_runner.py`.

Delete `finalize_blk_cogs()` (old state-level path) once nothing calls it — confirmed via grep that only `daily_runner.py` calls it; `consume_sor_sale()` itself (used by the payout backstop) stays untouched.

## Step D — Rewire `automation/daily_runner.py`

- Remove the current G2b block (right after `_run_blinkit()`) that calls `finalize_blk_cogs()`.
- After `_run_performance()` (G5) completes, call `finalize_blk_cogs_wh_level()`, log the summary, and send a failure-style alert if `held_mismatch`/`held_no_perf_data`/`held_wh_unresolved` are non-zero (same pattern as the existing G4/G5 alert blocks).
- Update the module docstring's sequence diagram at the top of the file to reflect: G2c now runs after G5, not right after G2.
- AZ COGS finalization (G1b, `finalize_az_cogs`) is untouched — Amazon stays state-level per the agreed design (single active FBA WH today).

## Step E — Update docs/memory to reflect "built" status

- `.claude/memory/project_sor_cogs_design.md`: change status line from "implementation pending" to "implemented (19-Jun-2026)", note the function name and where it's wired.
- `CLAUDE.md` (DemandPlanning) §"WH-Level COGS Finalization (G2c...)": update heading from "agreed Jun 2026, not yet built" to reflect it's live, keep the design rules (mismatch/missing-data handling) as-is since they're unchanged.
- `docs/build_plan.md` Phase K section: note K1b execution date and that G2c shipped alongside it.

## Verification

1. **Dev**: seed a small fixture — a few `orders` rows (BLK, FULFILLED, lot_cogs_finalized=False) and matching/mismatching `blinkit_performance_detail` rows covering: clean match, count mismatch, missing performance data, unresolved WH name. Run `finalize_blk_cogs_wh_level(dry_run=True)` then for real; assert correct rows get finalized and correct rows stay held.
2. Run existing `pytest tests/` against dev to confirm nothing else regresses (e.g. anything relying on `finalize_blk_cogs` existing).
3. **Prod, read-only first**: after migration 024 is applied to prod by Himanshu, run `finalize_blk_cogs_wh_level(dry_run=True)` against prod once new orders exist (i.e. after tomorrow's G2 run) to sanity-check the join before trusting it live.
4. K1b: confirm post-apply diff (`k1b_lot_baseline.py`) shows zero delta for every approved row.
