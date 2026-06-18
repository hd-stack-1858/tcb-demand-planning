# K1a — Blinkit Lot Consumption Code Audit

*Completed: 16-Jun-2026*

Audit of every code path that should move `sku_cogs_lots.qty_remaining` for the Blinkit (BLK) channel. Goal: confirm correctness before trusting any SOH comparison (K1b/K1c). All findings below are verified against prod data, not just code reading.

---

## Summary of paths

| # | Event | Code location | Verdict |
|---|-------|---------------|---------|
| 1 | Blinkit lot creation (ship-out to Blinkit) | `dispatch_sku()` → `_upsert_lot()` | ✅ Correct |
| 2 | Blinkit sale, daily/MTD report → COGS finalized same day | `load_blinkit_sales.py` (writes `supply_state`) → daily runner G2b `finalize_blk_cogs()` → `consume_sor_sale()` | ✅ Correct — **confirmed working daily in prod**, see below |
| 3 | Blinkit sale, payout file (backstop only) | `load_blinkit_payout.py:_apply_lot_cogs()` → `consume_sor_sale()` | ✅ Correct — redundant safety net, skips anything already finalized daily |
| 4 | Recalled/returned stock → OWN_WH (TinySteps Returns tab) | `return_sku()` via `ui/tinysteps_app.py` Tab 5 | ❌ **Bug A — confirmed in prod** |
| 5 | Customer return at Blinkit (payout Cancelled/Returned tab → status=SALE_RETURN) | `load_blinkit_payout.py:load_payout_folder()` return-marking loop | ❌ **Bug B — confirmed in prod** |
| 6 | Damaged/lost stock at Blinkit, manual write-off | `writeoff_sku()` | ⚠️ **Gap — not a regression, never built** |

---

## Daily vs. payout lot consumption — verified, not assumed

Initial read of an older design memory suggested lot consumption only happened twice a month at payout sync, which would make the K1c daily monitor pointless (SOH updates daily, lots wouldn't). That memory was stale. The current code already captures **Supply State** in the daily/MTD report itself (`load_blinkit_sales.py:92`, column 11 of the sales export) and the daily runner's **G2b step calls `finalize_blk_cogs()` immediately after the scraper, every day at ~12:01 IST**, consuming the lot same-cycle via `consume_sor_sale()`.

Verified against prod (last 30 days, 16-Jun-2026):
- 536 BLK FULFILLED orders with `order_date` in the last 30 days
- **536/536 (100%) already `lot_cogs_finalized=True`** — zero backlog
- 26/536 (~5%) have a NULL `supply_state` on that order (source file gap) and fall back to tier-2 channel-wide FIFO — still correct, just less precise than state-level matching

So the payout file's `_apply_lot_cogs()` (twice/month) is a backstop for orders the daily scraper missed, not the primary consumption path. **This means K1c's daily SOH comparison is meaningful from day one** — lots already move daily in step with sales, so any drift the monitor finds is real drift, not an artifact of consumption lag.

---

## Bug A — Recall return to OWN_WH never decrements the Blinkit lot

**Path:** TinySteps → Returns tab → "📦 Full SKU (assembled hamper)" → `return_sku(sku_id, qty, from_channel_id=BLK, ...)` — called **without** `partner_location_id` (`ui/tinysteps_app.py:846-852`).

**Root cause:** Every real Blinkit lot is created by `dispatch_sku()` with a specific, non-null `partner_location_id` (the WH it was shipped to) — confirmed 0 BLK lots in prod have a null location. When `return_sku()` is called with `partner_location_id=None` (the UI's default — it never asks which Blinkit WH the recall came from), `_consume_lots_fifo()` searches for BLK lots `WHERE partner_location_id IS NULL`. That set is always empty, so `available(0) < qty` raises `ValueError`, and `return_sku()` falls into its `except` branch:
```python
except ValueError:
    unit_cogs = _get_sku_cogs_fallback(sku_id, db)
    _upsert_lot(db, sku_id, own_wh_id, None, date.today(), unit_cogs, qty)
```
This fabricates a brand-new OWN_WH lot at fallback cost. The OWN_WH side ends up numerically correct (stock did come back), but **the original Blinkit lot is never decremented** — it stays permanently overstated by the returned quantity.

**Confirmed in prod (`setup/archive/_check_blk_return_lot_bug.py`):** Both of the only 2 BLK `RETURN` transactions ever recorded show the exact signature — a new OWN_WH lot created same-day, same qty, same unit_cogs as the return:
| txn_id | SKU | Qty | Date | OWN_WH lot created same day? |
|--------|-----|-----|------|------|
| 126 | TCB010 | 1 | 2026-05-12 | Yes — `assembled_at=2026-05-12, unit_cogs=910.689, qty=1` |
| 501 | TCB003 | 4 | 2026-06-06 | Yes — `assembled_at=2026-06-06, unit_cogs=724.697, qty=4` |

**Net effect:** Blinkit lots overstated by 5 confirmed units so far (1 TCB010, 4 TCB003). Will recur on every future recall return until fixed.

**Fix:** Returns tab needs the same WH selector pattern Ship Out already uses (`load_sor_whs(channel_id)`), and must pass `partner_location_id` through to `return_sku()`.

---

## Bug B — Blinkit customer return (payout SALE_RETURN) never restores the lot

**Path:** `load_blinkit_payout.py:load_payout_folder()`. Within a single payout run, `_apply_lot_cogs()` consumes a BLK lot for every row in `delivered_rows` (Forward Orders tab) — **including orders that the same file's Cancelled/Returned tab will later mark `SALE_RETURN`**. The return-marking loop that follows only does:
```python
db.table("orders").update({"status": "SALE_RETURN", "return_date": ...})...
```
It never restores a unit to any BLK lot, even though physically the customer-returned unit goes back into Blinkit's own sellable stock (this is a customer RTO at Blinkit, not a recall back to our WH — those are two different physical flows, see Bug A).

**Confirmed in prod:** 6 BLK orders are `status=SALE_RETURN` AND `lot_cogs_finalized=True` (lot was consumed before the return downgrade was applied) — all from April 2026, all `order_date == return_date` (same-day return, both rows present in one payout file). The other 14 BLK `SALE_RETURN` orders have `lot_cogs_finalized=False` (predate lot tracking — no exposure).

**Net effect:** Blinkit lots **understated** by 6 confirmed units — opposite direction from Bug A. This is why per-SKU drift doesn't move in one consistent direction; both bugs are real and both need fixing.

**Fix:** When marking an order `SALE_RETURN`, if it was already `lot_cogs_finalized=True`, restore 1 unit to a BLK lot using the **Supply State already available in the Cancelled/Returned tab (column 10)** — pick any active BLK location in that state and call `_upsert_lot()`, mirroring how `dispatch_sku()` creates lots. This keeps the restored unit eligible for tier-1 state-level FIFO matching on the next sale.

---

## Gap — No way to write off Blinkit-located stock (blocks K1d)

`writeoff_sku()` hardcodes `own_wh_id` — it can only ever write off stock sitting in OWN_WH. The TinySteps Write-off tab never offers a channel/WH selector. There is currently **no code path to reduce a Blinkit lot for damaged/lost units** reported in Blinkit's SOH. This isn't a regression (K1d was never built), but it's a hard blocker for K1d as scoped in the approved plan ("Himanshu opens TinySteps → Write-off tab → records the damaged/lost units against the Blinkit lot").

**Fix:** Extend `writeoff_sku()` with optional `from_channel_id` / `partner_location_id` params (default OWN_WH, preserving current behavior), consuming the partner lot via `_consume_lots_fifo()` instead of always assuming OWN_WH. Add channel + WH selectors to the Write-off tab UI, mirroring Ship Out / Returns.

---

## Verdict

K1b (baseline cleanup) can proceed once Bug A and Bug B are fixed — fixing them first means the SOH diff report won't be polluted by drift these bugs would keep re-creating every cycle. Both fixes are pure app-code changes (no schema migration needed) and can go dev → prod the same day per normal deployment workflow.
