# Streamlit web-app container (`Dockerfile.webapp`)

Runtime container for the two internal Streamlit apps —
`ui/tinysteps_app.py` (TinySteps WMS) and `ui/growthspurt_app.py`
(Growth Spurt / Sales MIS). This is the execution host that replaces
Streamlit Community Cloud (issue #114, parent epic #113).

**This is not the automation container.** `Dockerfile` (repo root) is the
Playwright/Chrome base for the scrapers; these apps are pure Streamlit and
only need `python:3.11-slim` (matches `runtime.txt`).

## What the image contains

- Base: `python:3.11-slim`
- `requirements.txt` (pins `streamlit==1.56.0`)
- `scripts/start_webapp.sh` — the entrypoint
- `HEALTHCHECK` on `/_stcore/health` (Streamlit's readiness endpoint)

One image serves either app — `STREAMLIT_APP` picks it at run time.

## Building and running locally

```bash
docker build -f Dockerfile.webapp -t tcb-webapp .
docker run --rm -p 8501:8501 \
  -e STREAMLIT_APP=growthspurt_app.py \
  -e SUPABASE_URL=https://your-project-ref.supabase.co \
  -e SUPABASE_KEY=your-SERVICE-ROLE-key \
  tcb-webapp
```

Then open http://localhost:8501. `STREAMLIT_APP` defaults to
`tinysteps_app.py`; both apps read config from plain env vars
(`tcb/db.py` reads `SUPABASE_URL`/`SUPABASE_KEY`), so no `secrets.toml`
is needed in the container. `.streamlit/secrets.toml` is excluded via
`.dockerignore` so local credentials never enter an image layer.

## Entrypoint behaviour (`scripts/start_webapp.sh`)

```bash
APP="${STREAMLIT_APP:-tinysteps_app.py}"
PORT="${PORT:-8501}"
exec streamlit run "ui/${APP}" \
  --server.port="${PORT}" --server.address="0.0.0.0" \
  --server.headless=true --browser.gatherUsageStats=false
```

- `$PORT` follows the Cloud Run convention (the platform injects `PORT`,
  default 8080). Local runs without `PORT` fall back to 8501.
- `--server.address 0.0.0.0` — bind all interfaces so the platform can reach it.
- `--browser.gatherUsageStats=false` — no telemetry out of the container.

## Health checks

- Docker `HEALTHCHECK` probes `http://127.0.0.1:$PORT/_stcore/health`
  (`$PORT` read at container runtime, so it stays correct under Cloud Run).
- Cloud Run readiness probe: configure it to `GET /_stcore/health` on the
  container's port. Streamlit returns `ok` once the app has finished booting.

## Cloud Run deployment

### Growth Spurt (Sales MIS) — `tcb-growthspurt`

Service: `tcb-growthspurt`, region `asia-south1`, project `adroitandroidworks`
(standalone project until #44 moves to the real TCB GCP org).

```bash
./scripts/gcp/deploy_growthspurt.sh adroitandroidworks
```

The script builds `Dockerfile.webapp` for `linux/amd64`, pushes to Artifact
Registry (`tcb-spike` repo), and deploys with:
- `STREAMLIT_APP=growthspurt_app.py`
- `--set-secrets SUPABASE_URL=supabase-url:latest,SUPABASE_KEY=supabase-key:latest`
- `--no-allow-unauthenticated` — IAM-invoker only until #117
- `--min-instances=1` — keeps the app warm (Streamlit cold starts ~20–30 s)

Smoke test once deployed:

```bash
URL=$(gcloud run services describe tcb-growthspurt \
  --project=adroitandroidworks --region=asia-south1 --format='value(status.url)')
curl -s -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "${URL}/_stcore/health"
# Expected: ok
```

### TinySteps (WMS) — `tcb-tinysteps`

Deploy script lands in issue #115. Same pattern as Growth Spurt with
`STREAMLIT_APP=tinysteps_app.py` and service name `tcb-tinysteps`.

### Consolidated parameterised scripts

Issue #118 will consolidate both deploy scripts into a shared helper. Until
then, each service has its own script under `scripts/gcp/`.

The app must stay IAM-locked (`--no-allow-unauthenticated`) until the
auth gate (issue #117) is live — Cloud Run has no viewer-allowlist
equivalent (see #15).

## Local parity check

Before a deploy is claimed "done", run each app from the container with the
same env vars Cloud Run will inject (no `secrets.toml`) and confirm behaviour
matches the current Streamlit Cloud app.
