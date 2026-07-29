#!/usr/bin/env bash
# Creates (or updates) the Cloud Run Job, wired to the GCS session bucket and
# FnP credential secrets. Safe to re-run.
#
# Usage:
#   PROJECT_ID=<project> REGION=asia-south1 ./automation/gcp_spike/03_deploy_job.sh
#
# FnP + Supabase secrets are created here with a PENDING placeholder if they
# don't exist yet — update the real values once Himanshu shares them:
#   echo -n "<real-username>"   | gcloud secrets versions add fnp-username    --data-file=- --project=$PROJECT_ID
#   echo -n "<real-password>"   | gcloud secrets versions add fnp-password    --data-file=- --project=$PROJECT_ID
#   echo -n "<supabase-url>"    | gcloud secrets versions add supabase-url    --data-file=- --project=$PROJECT_ID
#   echo -n "<service-role-key>"| gcloud secrets versions add supabase-key   --data-file=- --project=$PROJECT_ID

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to the target GCP project}"
REGION="${REGION:-asia-south1}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/tcb-spike/check-session:latest"
BUCKET="tcb-spike-sessions-${PROJECT_ID}"
JOB_NAME="tcb-spike-check"

create_secret_if_missing() {
  local name="$1"
  if ! gcloud secrets describe "$name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo -n "PENDING" | gcloud secrets create "$name" \
      --data-file=- --project="$PROJECT_ID"
    echo "Created placeholder secret: $name (update it once credentials arrive)"
  fi
}

create_secret_if_missing fnp-username
create_secret_if_missing fnp-password
create_secret_if_missing supabase-url
create_secret_if_missing supabase-key

gcloud beta run jobs deploy "$JOB_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE" \
  --add-volume="name=sessions,type=cloud-storage,bucket=${BUCKET}" \
  --add-volume-mount="volume=sessions,mount-path=/sessions" \
  --set-secrets="FNP_USERNAME=fnp-username:latest,FNP_PASSWORD=fnp-password:latest,SUPABASE_URL=supabase-url:latest,SUPABASE_KEY=supabase-key:latest" \
  --memory=1Gi \
  --cpu=1 \
  --task-timeout=300 \
  --max-retries=0

echo "Job deployed: $JOB_NAME (region $REGION, project $PROJECT_ID)"
