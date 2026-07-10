# Blinkit Performance Ingestion — Fix Plan

## Context

This investigation started from a question about the "Warehouse — City Mapping" table on the Blinkit Deepdive tab, but uncovered a chain of real ingestion-pipeline bugs, the most severe of which is currently live in prod:

**"Mumbai M12 - Feeder" has been a `Serving warehouse` value in our own downloaded performance CSVs since at least 2026-06-27 (12+ daily files) — 34 dark stores, 841 currently-active (`Considered=Y`) rows in the most recent file alone, covering Mumbai, Nashik, Vadodara, Surat, Anand, Bharuch, Navsari.** Every one of these rows has been silently dropped, every day, because `"Mumbai M12 - Feeder"` was never added to the hardcoded `WH_PERF_TO_CODE` dict. Three separate functions gate on this dict and silently skip anything not in it (`refresh_ds_master`, `update_wh_ds_mapping`, `upsert_detail`) — only a `print()` warning, never surfaced anywhere. Himanshu only learned this WH existed because Blinkit told him directly and he happened to see it in a raw file screenshot.

Himanshu's stated principle (previously discussed, not currently honored by the code): **the performance detail report is the "mother file"** — whatever WH/DS appears in the latest data must get reflected into `partner_locations` automatically, not gated behind a hand-maintained allowlist.

Along the way we also confirmed:
- `is_active` / eligibility staleness never self-heals on the daily automated run — only a rare manual full reprocess catches it (found via Chennai C5's Urapakkam/Mogappair dark stores, frozen 18 days to 3+ months).
- `propagate_darkstore_closed()` can incorrectly overwrite a SKU's fresh, legitimate status (e.g. `launch_awaited`) at a DS just because another SKU at that DS got a "store closed" remark — Himanshu flagged this specifically and wants it fixed as part of this work.
- Blinkit gives us no DS-level inventory quantity anywhere (SOH is WH-aggregate only; performance detail has a per-DS boolean, not a quantity) — so any "stranded stock" detection can only ever be a risk flag, never a certainty. Agreed as **Trigger 3**.

Goal of this work: make the ingestion pipeline self-healing and self-reporting, so a new/changed WH or a staleness gap surfaces as an alert the same day, not discovered by chance weeks later.

**No DB schema migration is required.** `partner_locations.code` has no unique DB constraint (confirmed in `setup/migrations/009_partner_locations.sql` — plain nullable TEXT); uniqueness is enforced in application code only, same as the existing DS-insert pattern. This is a code-only change.

---

## 1. Unify the three duplicated WH-name dicts

Three hand-maintained, independently-drifting dicts currently gate everything: `WH_PERF_TO_CODE` (`ingest/blinkit_performance_loader.py`), `_PERF_WH_TO_CODE` (`tcb/replenishment.py` — identical copy), and `WH_SOH_NAME_TO_CODE` (`ingest/blinkit_inventory_loader.py`).

Create a new leaf module **`ingest/blinkit_wh_resolver.py`** (no `tcb`/loader imports, avoids cycles):
- `WH_MANUAL_OVERRIDES` — the only hand-maintained map left: aliases (`'Bengaluru B3' → 'Bengaluru B3 - Feeder'`) and preferred human-readable codes for the ~20 legacy WHs (`'Mumbai M10 - Feeder' → 'BLK_WH_2123'`). Never a gate — absence never drops a row, it just means the auto-generated code is used instead.
- `_wh_code(name)` — same pattern as the existing `_ds_code()` (`ingest/blinkit_performance_loader.py:236`): `f'BLK_WH_{md5(name)[:8].upper()}'`.
- `build_wh_name_lookup(sb)` — runtime `name → code` built from `partner_locations` WH rows, layered with `WH_MANUAL_OVERRIDES` aliases. This replaces the read path of all three old dicts.
- `resolve_wh_code(name, lookup)` — override → existing DB name → `_wh_code(name)`. Always returns something; never `None`.

Migrate all three call sites (`blinkit_performance_loader.py`, `blinkit_inventory_loader.py`, `tcb/replenishment.py`) to import from here. Farukhnagar→Faridabad becomes an override entry, same as today.

## 2. Auto-create WH rows (the actual Mumbai M12 fix)

New function `ensure_whs_exist(wh_names, wh_lookup, sb)` in `blinkit_performance_loader.py`, called in **both** the daily scraper path and the manual `main()`, right before `refresh_ds_master()`:
- Fetch existing WH names from `partner_locations`.
- For each `Serving warehouse` value in the file not already present **by exact name match**, insert `{channel_id: 4, location_type: 'WH', name: <exact raw string from file>, code: resolve_wh_code(...), is_active: True}`. Exact-string `name` is required — migration 024 established that WH-level COGS finalization joins on `partner_locations.name` matching the file's string exactly.
- Rebuild `wh_lookup` immediately so DS under the brand-new WH get linked in the *same* run, not the next one.

`refresh_ds_master`, `update_wh_ds_mapping`, `upsert_detail` switch from `WH_PERF_TO_CODE.get(...)` / `.isin(our_whs)` to the shared resolver — the `.isin(our_whs)` filters that currently exclude unknown WHs are removed; every WH the file mentions is now "ours" by construction.

## 3. Make unrecognized-row discovery loud, not a silent print

`ingest/blinkit_inventory_loader.py` already does this correctly for the SOH file (lines 236-251) — reuse the exact same pattern for the performance loader, which currently only prints:
```python
if (skipped_wh or skipped_sku) and not dry_run:
    from automation.email_sender import send_alert
    send_alert(subject="...", body="...")
```
Thread structured counts up through the pipeline: `update_eligibility` returns `unknown_sku` / `unknown_ds` / `unknown_remarks` / a new `unclassified_n` counter (see §5 below on what that last one is); `upsert_detail` returns its skip counts; `process_file` merges all of these into one report dict. The daily scraper's `ingest()` (`automation/blinkit_performance_scraper.py`) sends one `send_alert()` if anything unclassified was found this run. Once §2 lands, "unknown WH" mostly disappears from this list (replaced by an informational "new WH auto-created: X" note) — what's left (unknown SKU, unmatched remark text, unclassified N-rows) are the genuine edge cases worth a human look.

## 4. Move staleness-healing functions into the daily path

`update_is_active()`, `propagate_darkstore_closed()`, `_check_trigger1_vanished_y()` currently only run from the loader's manual `main()` (gated `and not args.file`) — never from the daily automated scraper. Add calls to all three in `automation/blinkit_performance_scraper.py:ingest()`, after `process_file()`.

**Safety gate needed:** `update_is_active()` deactivates every DS absent from the *single* file being processed — fine for a normal daily file, dangerous if that day's download were truncated/corrupted (would mass-deactivate real DS). Gate this behind the §6 reconciliation check: skip the is_active sync (and alert instead) if the file's total/Y-row count is anomalously low vs. the trailing average.

This does not conflict with the documented "Once a DS, Always a DS" principle (`.claude/memory/blinkit_replen_system.md`) — no row is ever deleted, `is_active` toggling is the existing documented mechanism, just now running daily instead of rarely.

## 5. Fix `propagate_darkstore_closed()` (Himanshu's point a)

Today, Pass A does a blanket update: `.update({'status':'darkstore_closed',...}).in_('location_id', chunk).neq('status','darkstore_closed')` — this overwrites *any* non-closed status for *any* SKU at that DS, including one set moments earlier in the same run by `update_eligibility()` (e.g. a legitimate `launch_awaited`).

Fix: `process_file` collects `fresh_pairs: set[(location_id, sku_id)]` — every pair `update_eligibility()` actually classified *this run*, regardless of status. Thread this into `propagate_darkstore_closed(fresh_pairs)`:
- Keep the existing guard (DS with any DB `status='active'` row = reopened, don't touch).
- **Pass A**: instead of the blanket update, fetch existing non-closed rows for candidate closed-DS, subtract `fresh_pairs`, update only what remains (per-location `.in_('sku_id', [...])` on the non-fresh subset).
- **Pass B** (missing-pair insert): add `and (ds_id, sku_id) not in fresh_pairs` to the existing comprehension.

Net effect: propagation only ever touches SKU-DS pairs with **no fresh signal at all** from today's file — strictly less destructive than today, and matches Himanshu's requirement exactly.

## 6. Daily reconciliation check

In `process_file`, compute: total file rows, Y-rows, rows successfully classified into eligibility, and skips broken out by reason (`unknown_sku`, `unknown_ds`, `unknown_remark`, `unclassified_n` — see below). Feed into the §3 alert and the §4 safety gate.

**Point (b) explained for the record** (already covered in conversation, included here so the spec is self-contained): in `update_eligibility()`, an N-row with a blank `Darkstore remark` *and* a `Remarks` column that doesn't match the one known "FE movement bottlenecked" string just hits `continue` — no DB write in either direction. If the pair had a prior status, it stays frozen; if new, no row is ever created. This isn't being changed behaviorally (we still don't know what it means), but it now gets counted as `unclassified_n` and surfaced via §3 instead of vanishing into a print statement.

## 7. Trigger 3 — Orphaned WH stock (UI)

Add to `tab_blinkit_deepdive()`'s Data Quality Alerts section in `ui/growthspurt_app.py`, immediately after the existing Trigger 2 block (~line 2089), following the same query → `st.warning(...)` / silent-if-clean pattern as Triggers 1 and 2:
- Latest `blinkit_inventory_snapshots` snapshot, grouped by `location_id` (WH), `sum(total_sellable) > 0`.
- For each such WH, check `blinkit_performance_detail` over the trailing ~15 days for **zero** `Considered=Y` dark stores.
- If stock exists with no active DS underneath: `st.warning("**Trigger 3 — Orphaned WH stock:** ...")`, framed explicitly as a risk flag to check with Blinkit, not a certainty (no DS-level quantity data exists to prove it).

---

## Critical files

- `ingest/blinkit_performance_loader.py` — most of the change: new `ensure_whs_exist`, resolver migration, `propagate_darkstore_closed` fix, `fresh_pairs` threading, report dict
- `ingest/blinkit_wh_resolver.py` (new) — shared WH name/code resolution
- `automation/blinkit_performance_scraper.py` — daily `ingest()` gains the §4 calls + §3 alert + §6 gate
- `ingest/blinkit_inventory_loader.py` — switches to the shared resolver, no other behavior change (its alert pattern is the one being reused elsewhere)
- `tcb/replenishment.py` — switches to the shared resolver, deletes `_PERF_WH_TO_CODE`
- `ui/growthspurt_app.py` — Trigger 3 block in `tab_blinkit_deepdive()`

## Verification

Per project convention (`CLAUDE.md` — dev DB first, never test against prod):
1. Run the full loader manually against `TCB_ENV=dev` with a copy of a recent real file that contains "Mumbai M12 - Feeder" rows (one already exists locally). Confirm: a new WH row is created in dev `partner_locations` with `name` exactly matching the file string; its dark stores get inserted with correct `parent_location_id`; `blinkit_performance_detail` picks up its rows; no `[WARN] unknown_wh` for it anymore.
2. Re-run the same file a second time — confirm idempotency (no duplicate WH/DS rows, `ensure_whs_exist` finds it already present).
3. Construct a small synthetic CSV covering the `propagate_darkstore_closed` edge case (one SKU with an explicit "store closed" remark, another SKU at the same DS with a fresh `launch_awaited` row in the same file) — confirm the second SKU's status is *not* overwritten.
4. Confirm the reconciliation counts balance: classified + all skip-reason counts == total distinct (SKU, DS) pairs in the file.
5. Trigger 3: manually verify against the known current case (Chennai C5, 52 units, no active DS) that the alert fires; verify it's silent for a WH with genuine active DS and stock.
6. Once verified on dev, apply the same steps against a copy of prod data before flipping the daily scraper over (per the mandatory dev-first workflow) — Himanshu confirms when to cut over the live daily job.

## Implementation notes — two additional bugs found during dev verification (2026-07-10)

Both required a code fix beyond the original plan; both are now fixed and re-verified on dev.

1. **`scan_ds_from_files()` picked the WH assignment by file row order, not by actual date.** Testing against a real file with Mumbai M12 rows showed all 34 of its dark stores ALSO appear tagged under the old "Mumbai M10 - Feeder" on earlier rows in the SAME file (Blinkit's mid-transition: M10 through 2026-06-29, M12 from 2026-06-30 onward, confirmed by inspecting the raw `Date` column). The old code took whichever row happened to be read last, which was M10 by coincidence — so Mumbai M12 never won even after the auto-create fix. Fixed by adding `Date` to the columns scanned and sorting by `(filename, Date)` so the row with the actual latest date wins per DS, not row order.
2. **`ensure_whs_exist()` checked existence by exact name string, not resolved code.** This created duplicate WH rows (sharing the same `code` as an existing row) for 5 WHs whose `partner_locations.name` is still the pre-migration-024 SOH-style string ("Bengaluru B3", "Kundli Feeder", "Pune P3 - Feeder Warehouse", "Lucknow L4", "Kolkata K6 - Feeder Warehouse") while the performance file's string is the other alias ("Bengaluru B3 - Feeder", etc.) — both resolve to the same code via `WH_MANUAL_OVERRIDES`, but a literal-name check didn't know that. Fixed by checking `resolve_wh_code(name) not in wh_lookup` instead of literal name membership. Caught and cleaned up on dev only (re-synced from prod) — never touched prod.

**Related discovery, not yet actioned:** migration `024_blinkit_wh_name_sync.sql` (documented as applied, per `.claude/memory/blinkit_perf_detail_columns.md` and `CLAUDE.md`) does not appear to have actually run against prod — the 5 WHs above still carry their pre-migration names in the live DB (confirmed via dev, freshly synced from prod). This directly contradicts the design assumption behind WH-level COGS finalization (G2c), which is documented as joining on `partner_locations.name` matching `serving_wh` exactly. Trigger 3 was changed to join via the DS network (`parent_location_id`) instead of the name string specifically because of this — sidesteps the inconsistency, but G2c itself (not yet built) will need the same treatment or an actual re-application of migration 024. Flagged for Himanshu to decide: re-run migration 024 for real, or design G2c to go through the resolver instead of a raw name join.
