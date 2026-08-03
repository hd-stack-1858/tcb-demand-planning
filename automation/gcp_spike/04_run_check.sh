#!/usr/bin/env bash
# Executes the spike job once for a given portal and tails the result.
#
# Usage:
#   PROJECT_ID=<project> REGION=asia-south1 ./automation/gcp_spike/04_run_check.sh blinkit
#   PROJECT_ID=<project> REGION=asia-south1 ./automation/gcp_spike/04_run_check.sh fc
#   PROJECT_ID=<project> REGION=asia-south1 ./automation/gcp_spike/04_run_check.sh fnp

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to the target GCP project}"
REGION="${REGION:-asia-south1}"
JOB_NAME="tcb-spike-check"
PORTAL="${1:?Usage: 04_run_check.sh <blinkit|fc|fnp>}"

EXECUTION=$(gcloud run jobs execute "$JOB_NAME" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --args="$PORTAL" \
  --wait \
  --format="value(metadata.name)")

echo "Execution: $EXECUTION"
echo "--- logs ---"
gcloud logging read \
  "resource.type=cloud_run_job AND resource.labels.job_name=${JOB_NAME} AND labels.\"run.googleapis.com/execution_name\"=${EXECUTION}" \
  --project="$PROJECT_ID" \
  --format="value(textPayload)" \
  --order=asc
