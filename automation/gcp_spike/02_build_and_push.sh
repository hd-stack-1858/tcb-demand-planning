#!/usr/bin/env bash
# Builds the spike container via Cloud Build and pushes it to Artifact Registry.
#
# Usage:
#   PROJECT_ID=<project> REGION=asia-south1 ./automation/gcp_spike/02_build_and_push.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to the target GCP project}"
REGION="${REGION:-asia-south1}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/tcb-spike/check-session:latest"

cd "$(dirname "$0")"

gcloud builds submit \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --tag="$IMAGE" \
  .

echo "Image pushed: $IMAGE"
