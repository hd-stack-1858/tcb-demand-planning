# Testing Guide

Covers what exists in the test suite today, the CI-safe isolation strategy for the parts that
currently hit a real database, and the coverage gaps that follow-up work should close. Written
for issue [#6](https://github.com/hd-stack-1858/tcb-demand-planning/issues/6).

## 1. What Exists Today

### 1.1 Test files

| File | Lines | What it covers |
|---|---|---|
| `tests/conftest.py` | 116 | Shared fixtures (below) |
| `tests/test_phase_a.py` | ~299 | Drop-ship sale capture, COGS lots, MRP/state enrichment (`tcb.inventory`, `tcb.geo`) — 23 tests |
| `tests/test_phase_b.py` | ~171 | Blinkit sell-out ingestion (`ingest.utils`, `ingest.load_blinkit_sales`, `ingest.load_blinkit_payout`) — 12 tests |
| `tests/test_secret_scan.py` | 36 | Unrelated — checks `.gitleaks.toml`/CI workflow presence and runs `gitleaks` against history. No DB interaction. |
| `tests/unit/*.py` | ~230 | Added by [#33](https://github.com/hd-stack-1858/tcb-demand-planning/issues/33) — pure-logic unit tests for `tcb/session_store.py` and the Blinkit/FirstCry auth+scraper session wiring. Everything mocked (Playwright, Supabase client) — zero DB, zero network, zero credentials. See 2.1 below — this is the first concrete instance of that strategy. |
| `tests/integration_mocked/*.py` | ~130 | Added by #33 — real cross-module code (`tcb/session_store.py`, `automation/blinkit_auth.py`, `automation/blinkit_scraper.py`), only the true external boundary (Supabase) faked via an in-memory `FakeSupabaseClient`. Catches integration bugs a pure unit test (which mocks session_store's own functions) would miss — e.g. proves a real auth-saved session is genuinely loadable by a real scraper run, not just that each module calls session_store correctly in isolation. No credentials needed — safe to run anywhere, like `tests/unit/`. |
| `tests/test_session_store.py` | ~65 | Added by #33 — real dev-DB round-trip for `tcb/session_store.py`'s `portal_sessions` table. Same shared-dev-project limitation as `test_phase_a.py`/`test_phase_b.py` (see 2.2/2.3) — not yet migrated to the local Supabase stack. |

`test_phase_b.py` has 6 of its 12 tests gated by `skipif` on local Excel fixture files
(`blinkit_reports/sales/*.xlsx`, `blinkit_reports/payout sheets/*`) that are gitignored and
absent on any fresh checkout — **these silently skip in CI or on a new machine**, giving no real
coverage signal there today.

### 1.2 Fixtures (`tests/conftest.py`)

| Fixture | Scope | Autouse | What it does |
|---|---|---|---|
| `db` | session | no | Real Supabase client via `tcb.db.get_client()` — hits the live dev project directly. |
| `own_wh_id` | session | no | Queries the real `channels` table for the `OWN_WH` channel id. |
| `seed_dev_cogs` | session | **yes** | Seeds a synthetic `ASSEMBLY` transaction + open COGS lot for any catalog SKU missing one. Tears down by deleting what it inserted, by reference/lot id, at session end. |
| `restore_sku` | function | no | Yields a tracker; after each test, reverses any dispatched stock via `tcb.inventory.return_sku`. |
| `clean_test_orders` | function | no | After each test, deletes `orders` and `sku_inventory_transactions` rows whose reference is prefixed `PYTEST_`. |

**Gotcha worth knowing:** `seed_dev_cogs`'s inserted rows use the reference `SEED_DEV_COGS_PYTEST`
— deliberately **not** prefixed `PYTEST_` — so that `clean_test_orders` doesn't wipe them out
mid-session between tests. If you ever rename that reference to start with `PYTEST_`, the seed
data will vanish after the first test that triggers `clean_test_orders`, and every subsequent
COGS-dependent test in the session will fail confusingly.

### 1.3 Environment behavior

- `TCB_ENV=dev` is forced at import time (`conftest.py:9`), before `tcb.db`/`tcb.inventory`/`tcb.catalog` are imported — this guarantees dev config regardless of the ambient environment, with no guard against accidentally pointing at prod.
- Every fixture and nearly every test hits the **real dev Supabase project directly**. There is no mocking, no in-memory DB, no test container anywhere in the repo today (confirmed by grep for `mock`/`Mock`/`monkeypatch` across `tests/` and `ingest/` — zero matches).
- `test_phase_a.py` hardcodes specific dev-DB state as test assumptions (e.g. "TCB011: 18 units in stock") — fragile, and a real source of flakiness if dev data drifts.

### 1.4 What blocks a clean checkout from running tests at all

- **Partially resolved by #33**: `requirements-dev.txt` (`-r requirements.txt` + `pytest`, `psycopg2-binary`, `playwright`) and `pytest.ini` (registers `unit`/`integration` markers) now exist. `scripts/run_tests.sh unit|integration|all` sets up a venv and runs the right tier — same script works on a local machine, in CI, or in a throwaway sandbox.
- **Resolved by #33**: `.github/workflows/tests.yml` now runs `scripts/run_tests.sh unit` (which covers both `tests/unit/` and `tests/integration_mocked/`) on every push/PR — safe to run unconditionally since neither tier needs credentials.
- **Still open**: the `integration` tier still requires `.env.dev` and still hits the shared dev project directly (see 2.2) — not wired into CI, and won't be until the ephemeral local Supabase stack [#26](https://github.com/hd-stack-1858/tcb-demand-planning/issues/26) describes is built. Wiring it in by pointing CI at the shared dev project instead would repeat the exact mistake 2.2 already rejects.

## 2. Isolation Strategy

Two different problems need two different answers — neither should be forced into a single tool.

### 2.1 Pure logic → mocked unit tests, run in CI unconditionally

Anything that doesn't need a database (see 3.1) gets real unit tests with `unittest.mock`/
`pytest-mock` at whatever external boundary it touches (HTTP calls, retry loops). These are
fast, safe, and should run on every PR without qualification.

**Implemented for the first time in #33**: `tests/unit/` mocks the Supabase client for
`tcb/session_store.py` and mocks Playwright entirely (a `MagicMock` context manager standing in
for `sync_playwright()`) for the Blinkit/FirstCry auth scripts and scrapers — no browser, no
network. `tests/unit/conftest.py` overrides the root `conftest.py`'s autouse `seed_dev_cogs`
fixture (which otherwise forces a live dev-DB connection for every test in the tree) so this
subtree genuinely needs zero credentials. This is the pattern future unit-test follow-ups
(3.1's gap table) should copy.

### 2.2 DB-dependent behavior → ephemeral local Supabase stack, not the shared dev project

The existing integration-style tests (`test_phase_a.py`, `test_phase_b.py`, and future
`tcb/inventory.py` coverage) need real Postgres/PostgREST behavior to mean anything — FIFO
lot consumption, `v_sku_live_cogs`, RLS-guarded writes are exactly the kind of logic a
hand-written mock would silently drift from, giving false confidence on the repo's most
business-critical code.

The answer isn't "mock it anyway" and isn't "provision a second hosted Supabase.com project"
(real ongoing cost, another schema to keep in sync via the DB Change Workflow). It's the
**Supabase CLI's local dev stack**: `supabase start` brings up a real, ephemeral
Postgres + PostgREST + GoTrue via Docker, seeded fresh from the repo's already-numbered
`setup/migrations/*.sql` files, and torn down after the CI run. Nothing is hosted between runs,
so there's no ongoing cost and no drift to manage — and it's real Postgres, not a fake.

**Net effect: nothing in CI ever touches the shared dev or prod Supabase project**, while CI
still exercises genuine database behavior for the logic that depends on it.

Options considered and rejected:

| Option | Why rejected |
|---|---|
| Dedicated hosted CI Supabase project | Ongoing cost + another schema to keep synced; unnecessary for a 2–3 person team |
| Mock the DB layer entirely, including FIFO/COGS logic | Risks false confidence — a mock can't verify real Postgres/RLS/view behavior, and this repo's core value (never go OOS) lives in exactly that logic |
| Keep hitting the shared dev DB from CI | What we have today — no isolation, risk of CI runs corrupting or racing against real dev data, especially with concurrent PRs |

### 2.3 Convention for follow-up work

Follow-up tickets writing new tests should:
- Use no DB at all + mocks for pure-logic modules.
- Use the local Supabase stack (not the shared dev project) for anything touching `tcb.db`.

**Open question (not resolved in this issue):** `test_phase_a.py`/`test_phase_b.py`'s existing
fixtures currently point at the real dev project by design (`conftest.py:9`). Repointing them at
a local ephemeral stack instead — and standing up the CI workflow that installs the Supabase CLI,
runs `supabase start`, and applies `setup/migrations/` — is real, non-trivial work, deferred to
the CI-setup follow-up issue below, not done here.

## 3. Coverage Gap Tables

### 3.1 Unit-test gaps (pure logic, no DB, mockable)

| Module | Gap |
|---|---|
| `tcb/replenishment.py` | Zero coverage. ADS math, WH/DS eligibility rollups, target-stock formula — all pure-function candidates. |
| `ingest/blinkit_performance_loader.py` | `match_remark()` — zero coverage despite a documented production bug (`docs/plans/humble-questing-graham.md`) fixed with no accompanying unit test. |
| `ingest/blinkit_wh_resolver.py` | `resolve_wh_code()`/`_wh_code()` — zero coverage, shared by three other modules; highest-leverage single fix. |
| `ingest/utils.py` | `normalise_city`/`normalise_state`, `resolve_amazon_sku`, `resolve_fc_sku`, `_execute_with_retry` (retry/backoff never exercised). |
| `tcb/geo.py` | `pincode_to_city_state()` — calls the India Post API directly; only `city_to_state()` is unit-tested today. Needs the HTTP call mocked. |
| `automation/whatsapp.py`, `automation/email_sender.py` | Zero coverage, but trivially mockable (`requests.post`/`smtplib.SMTP`) — no external service needed. This reclassifies these from "integration" to "unit" relative to how issue #11 originally framed them. |

### 3.2 Integration-test gaps (need real DB behavior — target the local Supabase stack, not shared dev)

| Module | Gap |
|---|---|
| `tcb/inventory.py` | 18 of ~20 public functions untested: `assemble_sku`, `return_sku`, `return_item`, `writeoff_sku`, `writeoff_item`, `receive_item`, `record_outright_transfer`, `finalize_az_cogs`, `finalize_blk_cogs`, `finalize_fnp_fc_cogs`, `consume_sor_sale` (tier-1/tier-2 fallback), `get_reorder_alerts`, and others. This is the largest and most business-critical module in the repo. |

### 3.3 E2E / hard-to-test gaps

| Module | Gap | Why it's hard |
|---|---|---|
| `automation/blinkit_performance_scraper.py` | Zero coverage | Playwright automation against a live external portal with session-state auth; full e2e against the real portal isn't CI-practical. Needs either `page.route()` interception or extraction of pure logic (retry loop, name construction) first. Tracked as a low-priority watchlist item. |
| `ui/tinysteps_app.py`, `ui/growthspurt_app.py` | Zero coverage | Monolithic Streamlit scripts with no separation between pure calculation and widget rendering — testability is blocked until pure logic is extracted first. **Not treated as a watchlist item** — any further change to these apps is otherwise impossible to impact-assess safely, so the extraction is front-loaded (see next steps). |
| `mcp/server.py` | Zero coverage | Not yet built (Phase F). No action needed now beyond noting the gap exists. |

## 4. Next Steps

Five follow-up issues, each blocked by this one via native GitHub issue dependencies (follow-up
4 is additionally blocked by #18, the feature-flag system — it can't start until both #6 and #18
have landed, since its rollout depends on the flag mechanism):

1. **Pure-logic unit tests** — `tcb/replenishment.py`, `blinkit_wh_resolver.py`, `match_remark()`. Narrows issue #10.
2. **`tcb/inventory.py` integration tests** — against the local Supabase stack, covering the 18 untested public functions in 3.2. Narrows issue #10.
3. **CI/pytest setup** — add `pytest`+`pytest-mock` to `requirements.txt`, add `pytest.ini` with a unit/DB-dependent marker split, wire CI to install the Supabase CLI and run `supabase start` (seeded from `setup/migrations/`) for DB-dependent tests.
4. **Streamlit refactor for testability** — extract pure logic from `ui/tinysteps_app.py` and `ui/growthspurt_app.py`, verified via the feature-flag system (issue #18) so the extraction can be checked dev → local → prod in phases, mirroring the auth-wrapper rollout pattern (#20/#21). Front-loaded, not a watchlist item.
5. **[Watchlist] Playwright testability** — route-interception or logic-extraction investigation for `automation/blinkit_performance_scraper.py`.

**On issue #10:** left open as-is. Its scope is now effectively split across follow-ups 1 and 2
above; narrowing or closing it is part of picking up that work next, not part of this doc.

**On issue #11:** no new issue filed — section 3.1 already reclassifies `whatsapp.py`/
`email_sender.py` as straightforward unit-test targets, which is a refinement of #11's existing
scope, not a duplicate.

## 5. Open Questions

- Repointing `test_phase_a.py`/`test_phase_b.py`'s fixtures from the shared dev project to the
  local ephemeral Supabase stack is real fixture-rewrite work — scoped to the CI-setup follow-up,
  not resolved here.
- Whether every current dev-DB integration test can be faithfully reproduced against a local
  stack (e.g. any dev-only extensions, seed data, or manual dev-project configuration not
  captured in `setup/migrations/`) needs verification when that follow-up is picked up.
