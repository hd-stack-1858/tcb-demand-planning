#!/usr/bin/env bash
# Wires a Cloud Scheduler trigger for the tcb-blinkit-report Cloud Run Job,
# matching the existing local Windows Task Scheduler run (12:01 IST daily) —
# see issue #52. Deliberately does NOT touch --dry-run: this is purely about
# matching the schedule so Himanshu can compare the cloud report against the
# existing local one, side by side. Switching to real DB writes is #53.
#
# Usage:
#   PROJECT_ID=<project> REGION=asia-south1 ./scripts/setup_blinkit_scheduler.sh
#
# Safe to re-run — enabling an already-enabled API, granting an already-held
# IAM role, and updating an existing Scheduler job are all idempotent.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to the target GCP project}"
REGION="${REGION:-asia-south1}"
JOB_NAME="${JOB_NAME:-tcb-blinkit-report}"
SCHEDULER_JOB_NAME="${SCHEDULER_JOB_NAME:-tcb-blinkit-report-daily}"

# 12:01 IST daily. India has no DST, so this UTC offset is fixed: 06:31 UTC.
CRON_SCHEDULE="${CRON_SCHEDULE:-31 6 * * *}"

gcloud services enable cloudscheduler.googleapis.com --project="$PROJECT_ID"

RUNTIME_SA="$(gcloud run jobs describe "$JOB_NAME" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="value(spec.template.spec.template.spec.serviceAccountName)")"

# Cloud Scheduler needs run.invoker on the job's runtime SA to call :run via OAuth.
gcloud run jobs add-iam-policy-binding "$JOB_NAME" \
  --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/run.invoker" \
  >/dev/null

URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"

if gcloud scheduler jobs describe "$SCHEDULER_JOB_NAME" --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$SCHEDULER_JOB_NAME" \
    --project="$PROJECT_ID" --location="$REGION" \
    --schedule="$CRON_SCHEDULE" \
    --uri="$URI" \
    --http-method=POST \
    --oauth-service-account-email="$RUNTIME_SA"
else
  gcloud scheduler jobs create http "$SCHEDULER_JOB_NAME" \
    --project="$PROJECT_ID" --location="$REGION" \
    --schedule="$CRON_SCHEDULE" \
    --uri="$URI" \
    --http-method=POST \
    --oauth-service-account-email="$RUNTIME_SA"
fi

echo "Scheduler job '$SCHEDULER_JOB_NAME' set: $CRON_SCHEDULE (12:01 IST) -> $JOB_NAME"
