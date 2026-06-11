# Phase K1 — Blinkit Lot Integrity: Audit, Baseline, and Daily Monitoring

*Plan created: 11-Jun-2026 | Revised: 11-Jun-2026 after Himanshu voice input*

---

## Context

`sku_cogs_lots.qty_remaining` tracks unsold Blinkit WH inventory and is the input to Phase E (Reorder Integration). As of 6-Jun-2026, lots were 30–44 units overstated vs actual Blinkit SOH on some SKUs. Before we can trust lot data for reorder decisions, we need to understand WHY lots drift and fix the root causes — not just auto-correct them daily.

**Why auto-correction was wrong:** The original plan wired `refresh_blinkit_lots.py` into the daily runner to auto-adjust lots to match SOH. That is too aggressive because:
- SOH has a timing gap (~4h of daily sales not reflected)
- New lots need a cool-off period before being comparable
- Recalled inventory accounting is broken/unclear
- Initial lots were seeded manually and may have errors
- Code bugs on our side may be the real root cause of drift

**The right approach:**
1. Audit our code first — confirm lot consumption is correct
2. Do a one-time manual cleanup to set a clean baseline (Himanshu signs off)
3. Then run daily monitoring that flags discrepancies to Himanshu — no auto-correction ever

---

## Known Nuances of Blinkit SOH Data

These must be understood before any comparison logic is written.

### N1 — SOH Timing Gap (~4h daily)
The SOH report freezes at a point in the day (e.g. 7:55 PM on 11-Jun), but `finalize_blk_cogs()` processes sales through midnight. So the last ~4h of each day's sales will not be reflected in the SOH downloaded the next morning. The lots will always appear slightly overstated by exactly those unseen sales. **This is expected, not a bug.**

**Impact on design:** Any comparison must back out orders placed AFTER the SOH file timestamp (using `orders.order_date` vs the file's last-updated timestamp). Or accept a per-day noise band and only alert on deltas that persist across multiple days.

### N2 — New Lot Cool-Off (1–2 days)
When Himanshu ships to Blinkit via TinySteps, a lot is created immediately in our DB. But Blinkit takes 1–2 days to show this as incoming inventory in their SOH. Comparing a brand-new lot immediately will always show it as overstated (we have it, Blinkit doesn't yet).

**Design rule:** Exclude any `sku_cogs_lots` row where `assembled_at >= today - 3 days` from all comparisons.

### N3 — Recalled Inventory: Cumulative and Unreliable
The `Recalled` column in Blinkit SOH keeps accumulating — it does NOT reset when recalled stock returns to us. Example: 63 recalled units for TCB006 in Hyderabad (Jun-11 SOH) even though most have already returned.

Additionally: when Himanshu does a "returns inward" in TinySteps for recalled Blinkit stock, it's unclear whether that also reduces the Blinkit lot in `sku_cogs_lots`. If it does not, this is a code bug.

**Design rule:** Exclude `Recalled` column from expected_qty formula entirely. Compare against **sellable only** until recalled accounting is fully understood and fixed.

### N4 — Sellable Is the Reliable Signal
`Total Sellable = WH stock + darkstore stock + in-transit (WH→darkstore)`. All three sub-components are accurate. This is the primary column for comparison.

### N5 — Unsellable = Separate Workflow
`Damaged` and `Lost` columns in SOH represent units that Blinkit has written off. These:
- Should be flagged to Himanshu (not folded into lot comparison)
- Himanshu manually marks these as lost in TinySteps → reduces the lot
- Creates a compensation tracking trail (Blinkit owes payment for damages/losses)
- Expired/near-expiry will always be zero for our category — can be ignored

### N6 — Initial Lot Seeding Was Manual
The initial lots were seeded manually and may not have been accurate. This is an acceptable one-time problem to solve via the cleanup exercise (see K1b).

---

## Revised K1 Structure

K1 is now four sequential sub-phases. Each depends on the previous.

```
K1a → Code Audit         (no new code — read and verify existing logic)
K1b → One-Time Cleanup   (manual diff → Himanshu signs off → single apply)
K1c → Daily Monitoring   (report only — never auto-correct)
K1d → Damaged/Lost Alert (parallel flag — separate from reconciliation)
```

---

## K1a — Code Audit: Verify Lot Consumption Is Correct

**Goal:** Before comparing our lots to Blinkit SOH, confirm that all paths that should reduce `sku_cogs_lots.qty_remaining` are actually doing so correctly. Fix any bugs found before proceeding to K1b.

### Paths to audit

| Event | Expected lot impact | Code location | Verified? |
|-------|--------------------|--------------------|-----------|
| Blinkit sale (FULFILLED) | qty_remaining decremented via `finalize_blk_cogs()` | `tcb/inventory.py` | ⬜ |
| Blinkit lot creation (ship-out to Blinkit) | New lot inserted; OWN_WH lot decremented | `tcb/inventory.py:dispatch_sku()` | ⬜ |
| Recalled stock returned to OWN_WH (returns inward) | Blinkit lot decremented? Or is this unhandled? | `tcb/inventory.py:return_item()` | ⬜ |
| Damaged/lost at Blinkit (manual write-off in TinySteps) | Blinkit lot decremented | `tcb/inventory.py` | ⬜ |
| SOR sale via payout sheet | lot consumed via `consume_sor_sale()` | `tcb/inventory.py` | ⬜ |

### Specific question to answer in the audit

**Q: When Himanshu does a "returns inward" in TinySteps for recalled Blinkit stock — does `sku_cogs_lots.qty_remaining` for the Blinkit lot get decremented?**

If NO → this is a bug. The returned stock enters OWN_WH inventory but the Blinkit lot stays open, overstating unsold Blinkit stock. Fix: `return_item()` for Blinkit channel should also call `_consume_lots_fifo()` on the Blinkit channel lot. (Need to verify the exact function call and ensure we don't double-count with `finalize_blk_cogs()`.)

### Output of K1a
A written audit finding per path above: ✅ correct / ❌ bug found + fix needed. No K1b until all bugs are fixed.

---

## K1b — One-Time Manual Cleanup

**Goal:** Set a clean, verified baseline for all Blinkit lots. Do this once, manually, with Himanshu's sign-off on every change.

### Process

1. **Generate the diff report.** Run `refresh_blinkit_lots.py` in dry-run mode against the latest SOH file, applying the correct formula:
   ```
   expected_qty = total_sellable   (sellable only — recalled excluded per N3)
   ```
   Apply the 3-day cool-off filter (N2). Back out orders placed after the SOH file timestamp (N1).

2. **Present the diff to Himanshu.** Table format:
   | SKU | WH | DB qty_remaining | SOH sellable | Delta | Action |
   |-----|-----|-----------------|--------------|-------|--------|
   | TCB001 | Faridabad | 40 | 0 | -40 | Reduce |
   | TCB005 | BLR B3 | 18 | 22 | +4 | Increase |
   | TCB006 | HYD H3 | 30 | 30 | 0 | No change |

3. **Himanshu reviews and signs off.** He can approve each row, skip rows he wants to investigate further, or adjust the target qty.

4. **Apply only approved changes.** One-time run of `refresh_blinkit_lots.py` (or a targeted SQL update) for the approved rows only. Log each change to `lot_reconciliation_log` with `reason = 'ONE_TIME_CLEANUP'`.

5. **After cleanup:** The lots are now the authoritative baseline. Any future discrepancy needs investigation — not auto-correction.

---

## K1c — Daily Monitoring (No Auto-Correction)

**Goal:** Every day after the SOH download, compare lots to SOH and report discrepancies to Himanshu. Never auto-correct.

### Comparison formula (final)

```
expected_qty = total_sellable
             + orders_placed_after_soh_timestamp  # back-out timing gap (N1)

delta = expected_qty - sum(qty_remaining for lots where assembled_at < today - 3 days)
                       # cool-off filter (N2), recalled excluded (N3)
```

### What gets reported

The daily monitoring script generates a table per SKU×WH:
- **Green (delta = 0 or within noise band ±5 units):** no action
- **Yellow (|delta| 6–20 units):** logged silently, included in weekly summary email
- **Red (|delta| > 20 units OR persists 3+ consecutive days):** Email alert to Himanshu with the full diff table. No WhatsApp for lot discrepancies.

### What does NOT happen
- No writes to `sku_cogs_lots`
- No auto-correction of any kind
- Himanshu decides what to do after seeing the report

### How Himanshu acts on alerts
- If drift = expected (e.g. new shipment in transit): reply to ignore until cool-off
- If drift = Blinkit redistribution: Himanshu adjusts lot manually or flags for next week's review
- If drift = confirmed loss/damage: handled via K1d workflow

---

## K1d — Damaged/Lost Alert (Separate Workflow)

**Goal:** Every day, surface any `Damaged` or `Lost` units appearing in the SOH to Himanshu so he can action them and track Blinkit compensation.

### Daily flag

After SOH download, check if `damaged + lost > 0` for any SKU×WH that was zero yesterday (or compare to previous SOH file).

Email alert to Himanshu (no WhatsApp):
```
Subject: ⚠️ Blinkit Loss Alert — TCB003 HYD H3
Body: 2 units damaged, 1 unit lost (per Jun-11 SOH).
Action: mark as loss in TinySteps → reduces lot + creates compensation record.
```

### Himanshu's action
- Opens TinySteps → Write-off tab → records the damaged/lost units against the Blinkit lot
- This reduces `sku_cogs_lots.qty_remaining` correctly
- Compensation tracking: a note/log is added (for now just a comment in TinySteps; a formal compensation tracker is future scope)

---

## Files to Build / Change

| File | Type | What |
|------|------|------|
| (Audit notes doc) | Output of K1a | Written findings — not code |
| `setup/migrations/022_lot_reconciliation_log.sql` | New | Audit log table — same schema as before |
| `setup/refresh_blinkit_lots.py` | Modify | Add cool-off filter, exclude recalled, back out post-SOH orders, dry-run diff report format |
| `automation/daily_runner.py` | Modify | Add G4b step: run monitoring script, send drift alerts, NO lot writes |
| `automation/blinkit_lot_monitor.py` | New | Daily monitoring logic separated out cleanly (not inside refresh_blinkit_lots.py) |
| `ui/tinysteps_app.py` | Modify (future) | Damaged/lost write-off tab that correctly reduces Blinkit lot |

---

## Sequencing

```
Week 1:
  K1a — Code audit (1–2 sessions)
       → Fix any bugs found (e.g. returns inward not reducing Blinkit lot)

Week 2:
  K1b — One-time cleanup
       → Generate diff report
       → Himanshu reviews + signs off
       → Apply approved changes

Week 2-3:
  K1c + K1d — Daily monitoring wired into daily runner
            → No auto-correction
            → Alert on drift > 20 units or 3-day persistence

When K1 is stable (1–2 weeks of clean reports):
  → Phase E (Reorder Integration) is safe to build
```

---

## Strategic Notes (CEO Review)

**Why no auto-correction is the right call:**
At ~₹5.5L/month revenue and growing, a wrong reorder trigger is worse than a late one. Auto-correcting lots without understanding the root cause means we might mask a real inventory problem (theft, Blinkit accounting error, system bug) that needs human attention. Manual sign-off keeps Himanshu in the loop and creates accountability.

**Why the code audit must come first:**
If `return_item()` for Blinkit recalled stock doesn't decrement the Blinkit lot, then every recall creates a permanent overstatement. No amount of SOH comparison will fix that — the fix must be in the code. Building the monitoring on top of a broken code base produces a dashboard that always shows false alarms.

**Why sellable-only comparison is correct:**
Recalled units are still "Blinkit's problem" until they physically arrive at our warehouse. Once they arrive and Himanshu does returns inward, the lot should be decremented then. Unsellable (damaged/lost) is flagged separately as a compensation event. Mixing all these into one formula creates confusion about who owns the units.

**Phase E dependency:**
Phase E (Reorder) can be built once K1b (baseline cleanup) is done and K1c is running for 1–2 weeks without large unexplained alerts. "Running cleanly" = no persistent red alerts and Himanshu can explain any yellow alerts by inspection.

---

## Verification Checklist

### K1a
- [ ] All 5 lot consumption paths audited and documented
- [ ] `return_item()` for Blinkit channel verified: does/doesn't reduce Blinkit lot
- [ ] If bug found: fix written, tested on dev, Himanshu applies to prod

### K1b
- [ ] Diff report generated with correct formula (sellable only, 3-day cool-off, timing gap backed out)
- [ ] Himanshu reviews and signs off each row
- [ ] Approved changes applied, `lot_reconciliation_log` rows inserted with `reason='ONE_TIME_CLEANUP'`
- [ ] Post-cleanup: run diff again → all deltas should be zero or within noise band

### K1c + K1d
- [ ] Daily monitoring runs after G4 in daily runner
- [ ] No writes to `sku_cogs_lots` — verified by querying `updated_at` timestamps
- [ ] Yellow/red threshold alert fires correctly in test
- [ ] K1d: damaged/lost alert sends correctly when SOH has non-zero values
- [ ] Week-1 clean run confirmed (no false positives on known-good lots)
