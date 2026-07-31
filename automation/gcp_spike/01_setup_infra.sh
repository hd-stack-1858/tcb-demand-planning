#!/usr/bin/env bash
# Enables APIs and creates the Artifact Registry repo + GCS bucket used by
# the rest of the gcp_spike scripts. Idempotent — safe to re-run.
#
# Usage:
#   PROJECT_ID=<project> REGION=asia-south1 ./automation/gcp_spike/01_setup_infra.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to the target GCP project}"
REGION="${REGION:-asia-south1}"
BUCKET="gs://tcb-spike-sessions-${PROJECT_ID}"

gcloud config set project "$PROJECT_ID"

# Billing must already be linked — check with:
#   gcloud billing projects describe "$PROJECT_ID"

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  --project="$PROJECT_ID"

gcloud artifacts repositories create tcb-spike \
  --repository-format=docker \
  --location="$REGION" \
  --description="TCB scraper geo-spike images (disposable)" \
  --project="$PROJECT_ID" \
  || echo "Artifact Registry repo already exists — skipping."

gcloud storage buckets create "$BUCKET" \
  --location="$REGION" \
  --uniform-bucket-level-access \
  --project="$PROJECT_ID" \
  || echo "Bucket already exists — skipping."

# Cloud Run Jobs run as the default compute service account unless overridden.
# It needs Secret Manager access to read FNP_USERNAME/FNP_PASSWORD at runtime.
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None \
  >/dev/null

echo "Infra ready. Bucket: $BUCKET"
echo "Granted Secret Accessor to: $RUNTIME_SA"
