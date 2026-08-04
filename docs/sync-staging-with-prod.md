# Sync staging with prod (`setup/sync_staging_with_prod.py`)

Copies a full snapshot of the prod Supabase database onto the staging Supabase database.
Run this before testing a release on staging so staging has realistic prod data.

## When to run

- Before every staging validation round during a release cycle.
- After migrating a schema change to staging (to reload data in the new shape).
- On demand when staging data has drifted from prod.

## Prerequisites

1. The staging Supabase project exists and has the correct schema applied
   (run all pending migrations against staging first — this script only syncs data).
2. You have the staging DB connection string (Session pooler URL from the Supabase dashboard).

## Setup

Copy `.env.staging.example` to `.env.staging` and fill in the staging DB URL:

```bash
cp .env.staging.example .env.staging
# edit .env.staging — paste your staging Session pooler connection string
```

Get the connection string from:
`Supabase Dashboard → staging project → Settings → Database → Connection string → Session pooler`

Prod credentials are read from the existing `.env` file (`SUPABASE_URL` + `SUPABASE_KEY`).

## Usage

### GitHub Actions (recommended)

Go to **Actions → Sync Staging with Prod → Run workflow** and pick dry-run or live.
Credentials are injected automatically from the `staging` GitHub Environment secrets.

### Local (Unix)

```bash
# Dry run — shows what would happen, writes nothing
python setup/sync_staging_with_prod.py --dry-run

# Full sync — clears staging and loads current prod snapshot
python setup/sync_staging_with_prod.py

# Explicit credentials (skips .env files — useful in ad hoc scenarios)
python setup/sync_staging_with_prod.py \
    --prod-url  https://YOUR_PROD_REF.supabase.co \
    --prod-key  YOUR_PROD_SERVICE_ROLE_KEY \
    --staging-db-url postgresql://postgres.YOUR_STAGING_REF:PASSWORD@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
```

## What it does

| Phase | Action |
|-------|--------|
| 1 — Clear | Truncates all data tables on staging in leaf-first order (avoids FK violations) |
| 2 — Master data | Loads channels, suppliers, SKUs, items, BOM, pricing, partner locations, etc. |
| 3 — Current state | Loads live balances: inventory, item batches, SKU lots, Blinkit DS eligibility |
| 4 — Transactional | Loads full history: orders, txns, Blinkit snapshots + performance detail |
| 5 — Verify | Prints row counts for all key tables to confirm the sync landed |

Unlike `setup/sync_dev_to_prod.py` (which applies schema migrations and copies only 90 days of history),
this script copies **all** transactional history and makes **no schema changes** — staging must already be
schema-correct before running.

## Credentials resolution order

For each credential the script checks, in order:

1. CLI flag (`--prod-url`, `--prod-key`, `--staging-db-url`)
2. Environment variable (`PROD_SUPABASE_URL`, `PROD_SUPABASE_KEY`, `STAGING_DB_URL`)
3. `.env.staging` (for `STAGING_DB_URL`) or `.env` (for prod credentials)

## Security notes

- `.env.staging` is gitignored — never commit it.
- Use the **service-role** key for prod reads (the anon key cannot read all rows).
- The staging DB connection string contains the database password — treat it as a secret.
