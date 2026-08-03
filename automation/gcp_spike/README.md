# GCP geo-spike — Cloud Run Job

Tests whether the Blinkit / FirstCry / FnP portals accept scraper traffic
(session replay or fresh login) originating from a GCP `asia-south1`
(Mumbai) IP, before committing to Cloud Run as the production host for
`daily_runner.py`.

Currently built against a **standalone project** (`adroitandroidworks`)
because the real TCB GCP org/project (under Himanshu's Workspace domain)
doesn't exist yet. Every script below takes `PROJECT_ID` as an env var —
re-run the same four scripts in order against the real project once it
exists. Nothing else needs to change.

## Re-running against the real TCB project later

```bash
export PROJECT_ID=<real-tcb-project-id>
export REGION=asia-south1          # unchanged unless portals need a different region
./automation/gcp_spike/01_setup_infra.sh
./automation/gcp_spike/02_build_and_push.sh
./automation/gcp_spike/03_deploy_job.sh
./automation/gcp_spike/04_run_check.sh blinkit   # or fc / fnp
```

## What each script does

| Script | Purpose |
|---|---|
| `01_setup_infra.sh` | Enables required APIs, creates the Artifact Registry repo and the GCS bucket that holds session files |
| `02_build_and_push.sh` | Builds the spike container (Playwright + `check_session.py`) via Cloud Build, pushes to Artifact Registry |
| `03_deploy_job.sh` | Creates/updates the Cloud Run Job, wired to the GCS bucket as a mounted volume |
| `04_run_check.sh <portal>` | Executes the job once for `blinkit`, `fc`, or `fnp`, tails the logs, prints the verdict |

## Handing off credentials (never through this repo or chat)

- **Blinkit / FirstCry**: Himanshu runs `blinkit_auth.py` / `fc_auth.py`
  locally as usual, sends the resulting `state.json` over a private
  channel (Signal, not Slack/email in plaintext). Upload it with:
  ```bash
  gcloud storage cp state.json gs://tcb-spike-sessions-$PROJECT_ID/blinkit/state.json
  ```
- **FnP**: no session file needed — it's a plain username/password login
  with no CAPTCHA ([fnp_scraper.py](../fnp_scraper.py)). Store credentials
  as Cloud Run env vars sourced from Secret Manager instead of a bucket
  file (see `03_deploy_job.sh`).

## Teardown

Nothing here runs on a schedule or costs anything while idle — Cloud Run
Jobs only bill for actual execution time. To remove everything:

```bash
gcloud run jobs delete tcb-spike-check --region=$REGION --project=$PROJECT_ID --quiet
gcloud artifacts repositories delete tcb-spike --location=$REGION --project=$PROJECT_ID --quiet
gcloud storage rm -r gs://tcb-spike-sessions-$PROJECT_ID --quiet
```
