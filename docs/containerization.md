# Containerized automation (`Dockerfile`, `scripts/run_in_docker.sh`)

First real container for the `automation/` pipeline — part of
[#34](https://github.com/hd-stack-1858/tcb-demand-planning/issues/34), under
the parent migration [#32](https://github.com/hd-stack-1858/tcb-demand-planning/issues/32).

## What's in the image

Base: `mcr.microsoft.com/playwright/python:v1.48.0-jammy`, plus
`requirements.txt` and real Chrome (`playwright install --with-deps chrome`).

Real Chrome specifically — not bundled Chromium — because Blinkit's
Cloudflare bot detection blocks Playwright's bundled Chromium in headless
mode (different TLS/JA3 fingerprint). This is a **browser-level** signal,
not a network-origin one: it's resolved by using real Chrome, regardless of
whether that Chrome runs on a laptop or in a cloud datacenter. Confirmed
twice — once replaying a session from a Mumbai Cloud Run container
(`automation/gcp_spike/`), once running the actual `blinkit_scraper.py` in
this container end-to-end.

**Known follow-up:** the current image is heavier than necessary (bundles
Chromium/Firefox/WebKit it never uses, on top of real Chrome, for every
script even though only the 3 Blinkit scripts need real Chrome) — tracked
separately in [#42](https://github.com/hd-stack-1858/tcb-demand-planning/issues/42),
deliberately not blocking this work.

**No Linux ARM64 build for real Chrome exists.** Cloud Run defaults to
`linux/amd64`, so this is a non-issue there — but on Apple Silicon, always
build/run with `--platform linux/amd64` (Docker emulates it via QEMU,
slower but works). `scripts/run_in_docker.sh` does this automatically.

## Running any automation script in the container

```bash
TCB_ENV=dev ./scripts/run_in_docker.sh automation/blinkit_scraper.py --dry-run
```

- `TCB_ENV` — `dev` (default) or `prod`. Picks `.env.dev` or `.env` for
  credentials. **Never point this at prod without meaning to.**
- `DATA_DIR` — host directory mounted at `/app/data` (default `./data`) —
  where downloaded reports actually land, e.g.
  `$DATA_DIR/blinkit/auto/sales/sales_summary.xlsx`.
- `NO_BUILD=1` — skip the image rebuild for faster iteration once it's
  already built.

Credentials never get baked into the image — `.env`/`.env.dev` are excluded
via `.dockerignore` and passed in only at `docker run` time via `--env-file`.

## Verified so far

Real Blinkit sales report, generated end-to-end in this container:
session loaded from Supabase `portal_sessions` (see
[docs/session_store.md](session_store.md)) → real Chrome logged into the
live Blinkit seller portal → downloaded the actual MTD sales `.xlsx` →
written to the mounted volume → session write-back confirmed → dry-run
ingest parsed 228 rows, 0 DB writes.

FirstCry (`fc_scraper.py`) is deliberately **not yet run this way**: unlike
Blinkit's read-only report download, it takes real actions on the live FC
vendor portal (accepts pending orders) even with `--dry-run` — that flag
only skips *our* DB write and the email send, not the portal-side actions.
Containerizing it needs a deliberate decision about when it's safe to run,
not just a Docker verification pass.

## Deploying to Cloud Run (manual steps used for `tcb-blinkit-report`)

Not yet on a schedule (see [#45](https://github.com/hd-stack-1858/tcb-demand-planning/issues/45)) — this is how the current proof-of-concept job was actually set up, standalone GCP project (`adroitandroidworks` — see [#44](https://github.com/hd-stack-1858/tcb-demand-planning/issues/44) for the eventual move to TCB's real GCP org):

```bash
# Build for linux/amd64 (Cloud Run's default arch — matters on Apple Silicon)
docker build --platform linux/amd64 -t tcb-automation .

# Push to Artifact Registry (reuses the repo created by automation/gcp_spike/01_setup_infra.sh)
gcloud auth configure-docker asia-south1-docker.pkg.dev
docker tag tcb-automation asia-south1-docker.pkg.dev/adroitandroidworks/tcb-spike/blinkit-report:latest
docker push asia-south1-docker.pkg.dev/adroitandroidworks/tcb-spike/blinkit-report:latest

# Secrets (SUPABASE_URL/SUPABASE_KEY already existed from the earlier geo-spike;
# create the Slack ones the same way)
echo -n "<token>"      | gcloud secrets create slack-bot-token   --data-file=- --project=adroitandroidworks
echo -n "<channel-id>"  | gcloud secrets create slack-channel-id --data-file=- --project=adroitandroidworks

# Deploy — no GCS volume mount needed (unlike automation/gcp_spike/'s check_session.py),
# since the session lives in Supabase now, not a mounted file.
gcloud run jobs deploy tcb-blinkit-report \
  --project=adroitandroidworks --region=asia-south1 \
  --image=asia-south1-docker.pkg.dev/adroitandroidworks/tcb-spike/blinkit-report:latest \
  --command="python" \
  --args="automation/run_blinkit_report.py,--dry-run" \
  --set-env-vars="TCB_ENV=dev" \
  --set-secrets="SUPABASE_URL=supabase-url:latest,SUPABASE_KEY=supabase-key:latest,SLACK_BOT_TOKEN=slack-bot-token:latest,SLACK_CHANNEL_ID=slack-channel-id:latest" \
  --memory=1Gi --cpu=1 --task-timeout=300 --max-retries=0

# Run it
gcloud run jobs execute tcb-blinkit-report --project=adroitandroidworks --region=asia-south1 --wait
```

**Verified live from this exact job**, not just locally:
- Real Blinkit sales report → real Slack post, from a Cloud Run execution in `asia-south1`.
- **Error handling confirmed non-silent**, tested against the live job:
  - Bad `SUPABASE_KEY` → clean `401 Unauthorized` from Supabase, caught by `run_blinkit_report.py`'s generic exception handler, **Slack alert sent**, exit code 1.
  - Corrupted/expired Blinkit session (cookies overwritten with garbage, then restored from a backup afterward) → `BlinkitSessionExpired` raised, **Slack alert sent** with a distinct message, exit code 2 — correctly distinguished from the generic-error case.
  - In both cases, Cloud Run reports the execution as failed (non-zero exit) — nothing here can silently succeed while actually broken.
