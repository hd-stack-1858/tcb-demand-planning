# Local Development Setup

Onboarding guide for new contributors. Covers everything needed to run both Streamlit apps locally.

## Prerequisites

- **Python 3.11** (`python --version` — see `runtime.txt`)
- **Git**
- **Supabase project access** — you need the service_role key from the Supabase dashboard

## 1. Clone the repository

```bash
git clone https://github.com/hd-stack-1858/tcb-demand-planning.git
cd tcb-demand-planning
```

## 2. Create your environment file

```bash
cp .env.example .env.dev
```

Open `.env.dev` and fill in your credentials. The file is gitignored — never commit it.

**Required variables:**

| Variable | Where to find it |
|----------|-----------------|
| `SUPABASE_URL` | Supabase dashboard → Settings → API → Project URL |
| `SUPABASE_KEY` | Supabase dashboard → Settings → API → **service_role** key (NOT anon) |

**Optional variables** (only needed for email/WhatsApp automation):

| Variable | Purpose |
|----------|---------|
| `SMTP_SENDER`, `SMTP_PASSWORD` | Gmail app password for alerts |
| `META_WA_TOKEN`, `META_PHONE_NUMBER_ID` | Meta Cloud API for WhatsApp briefings |

## 3. Set up Python environment

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Windows (CMD)

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

## 4. First-time database setup

Sync a fresh copy of the prod database to your dev environment:

```bash
export TCB_ENV=dev
python setup/sync_dev_to_prod.py
```

This copies the latest prod schema and data into your dev database. All tests run against `TCB_ENV=dev` — never against prod.

### Windows note

Use `set TCB_ENV=dev` in CMD, or `$env:TCB_ENV = "dev"` in PowerShell.

## 5. Run the Streamlit apps

Both apps use the `tcb` Python library. The project root is added to `sys.path` automatically via `pathlib`.

### Sales MIS Dashboard (growthspurt)

```bash
TCB_ENV=dev streamlit run ui/growthspurt_app.py
```

### Warehouse Operations (tinysteps)

```bash
TCB_ENV=dev streamlit run ui/tinysteps_app.py
```

### Windows equivalents

CMD:
```cmd
set TCB_ENV=dev
streamlit run ui\growthspurt_app.py
```

PowerShell:
```powershell
$env:TCB_ENV = "dev"
streamlit run ui\growthspurt_app.py
```

## 6. TCB_ENV convention

The `TCB_ENV` environment variable controls which `.env` file `tcb/db.py` loads:

| Value | Loaded file | Use case |
|-------|------------|----------|
| `dev` (or unset) | `.env.dev` | Local development, tests |
| `prod` | `.env` | Live Streamlit Cloud deployment |

All tests automatically set `TCB_ENV=dev` in `tests/conftest.py` — never run tests against prod.

## 7. Running tests

```bash
export TCB_ENV=dev
pytest tests/ -v
```

The test suite hits the dev database directly. Make sure `setup/sync_dev_to_prod.py` has been run recently so your dev DB reflects the latest prod schema.

### Unit tests (no database required)

```bash
pytest tests/unit/ -v --rootdir=tests/unit
```

## 8. Cross-platform checks

The CI pipeline enforces that no hardcoded local filesystem paths (`/Users/...`, `C:\Users\...`) leak into committed files. You can run this check locally:

```bash
python scripts/check_local_paths.py . \
  --exclude .env .env.dev .env.example \
  --exclude .claude/ .agy/ data/ .venv/ __pycache__/ \
  --exclude .git scripts/ tests/
```

If you need a local path (e.g., for a scraper config), keep it in `.env.dev` — it's gitignored.

## Troubleshooting

### "SUPABASE_URL and SUPABASE_KEY must be set"

You haven't created `.env.dev` yet, or the values are empty. Follow step 2 above.

### `ModuleNotFoundError: No module named 'tcb'`

Make sure you're running from the project root and the virtual environment is activated. The `tcb/` directory is a local package, not installed via pip.

### Streamlit app shows "Connection refused"

Your dev DB may be paused (Supabase free-tier pauses after 7 days of inactivity). Run `python setup/sync_dev_to_prod.py` to reconnect.
