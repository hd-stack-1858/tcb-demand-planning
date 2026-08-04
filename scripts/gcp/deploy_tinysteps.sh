#!/usr/bin/env bash
# Deploy TinySteps (ui/tinysteps_app.py) to Cloud Run — issue #115 (epic #113).
#
# Usage: ./scripts/gcp/deploy_tinysteps.sh PROJECT_ID ENV
#
#   ENV — required: dev | staging | prod
#
#   ENV       Service name             Image tag           Secrets
#   -------   ----------------------   -----------------   ----------------------------
#   dev       tcb-tinysteps-dev        tinysteps-dev       supabase-url-dev / supabase-key-dev
#   staging   tcb-tinysteps-staging    tinysteps-stg       supabase-url-staging / supabase-key-staging
#   prod      tcb-tinysteps            tinysteps           supabase-url / supabase-key
#
# Builds Dockerfile.webapp for linux/amd64, pushes to Artifact Registry, and
# deploys (or updates) the Cloud Run service for the given environment.
#
# Prerequisites:
#   - gcloud authenticated with permission to push to AR and deploy Cloud Run
#   - Supabase secrets exist in Secret Manager for PROJECT_ID (env-specific names above).
#     Create with: echo -n "VALUE" | gcloud secrets create supabase-url-staging \
#       --data-file=- --project=PROJECT_ID
#   - Docker installed and running
#
# Security: service is deployed --no-allow-unauthenticated (IAM-invoker only)
# until the auth gate (issue #117) lands. Never remove this flag without #117.
set -euo pipefail

PROJECT_ID="${1:?Usage: deploy_tinysteps.sh PROJECT_ID ENV}"
ENV="${2:?ENV is required — pass dev, staging, or prod}"

case "${ENV}" in
  dev)
    SERVICE=tcb-tinysteps-dev
    IMAGE_NAME=tinysteps-dev
    SECRET_URL=supabase-url-dev
    SECRET_KEY=supabase-key-dev
    ;;
  staging)
    SERVICE=tcb-tinysteps-staging
    IMAGE_NAME=tinysteps-stg
    SECRET_URL=supabase-url-staging
    SECRET_KEY=supabase-key-staging
    ;;
  prod)
    SERVICE=tcb-tinysteps
    IMAGE_NAME=tinysteps
    SECRET_URL=supabase-url
    SECRET_KEY=supabase-key
    ;;
  *)
    echo "ERROR: ENV must be one of: dev | staging | prod (got: ${ENV})" >&2
    exit 1
    ;;
esac

REGION=asia-south1
REPO=tcb-spike
IMAGE="asia-south1-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:latest"

# Fail fast: verify that every secret the deploy needs already exists in
# Secret Manager. Without this, `gcloud run deploy` fails mid-deploy with a
# cryptic 404 on the secret ref — wasting a full build+push cycle.
validate_secrets() {
  local missing=()
  for secret in "$@"; do
    if ! gcloud secrets describe "${secret}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
      missing+=("${secret}")
    fi
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "ERROR: missing secrets in Secret Manager (project=${PROJECT_ID}):" >&2
    for s in "${missing[@]}"; do
      echo "  - ${s}" >&2
    done
    echo "" >&2
    echo "Create them with:" >&2
    for s in "${missing[@]}"; do
      echo "  echo -n \"VALUE\" | gcloud secrets create ${s} --data-file=- --project=${PROJECT_ID}" >&2
    done
    exit 1
  fi
  echo "==> Secrets validated: $*"
}

validate_secrets "${SECRET_URL}" "${SECRET_KEY}"

# docker push can die with 'unexpected EOF' mid-large-layer over flaky
# networks to Artifact Registry; completed layers are cached server-side, so
# a retry resumes rather than restarts. Retry up to 3 times with a short pause.
push_with_retry() {
  local image="$1" attempt=1
  while [ "${attempt}" -le 3 ]; do
    echo "==> docker push ${image} (attempt ${attempt}/3)"
    if docker push "${image}"; then
      return 0
    fi
    echo "    push failed; retrying in 5s..."
    sleep 5
    attempt=$((attempt + 1))
  done
  echo "ERROR: docker push failed after 3 attempts" >&2
  return 1
}

echo "==> Deploying TinySteps to env=${ENV}, service=${SERVICE}"
echo "==> Building Dockerfile.webapp for linux/amd64 (Cloud Run arch)"
docker build --platform linux/amd64 -f Dockerfile.webapp -t "${IMAGE}" .

echo "==> Pushing to Artifact Registry: ${IMAGE}"
gcloud auth configure-docker asia-south1-docker.pkg.dev --quiet
push_with_retry "${IMAGE}"

echo "==> Deploying Cloud Run service: ${SERVICE}"
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --port=8080 \
  --set-env-vars=STREAMLIT_APP=tinysteps_app.py \
  --set-secrets="SUPABASE_URL=${SECRET_URL}:latest,SUPABASE_KEY=${SECRET_KEY}:latest" \
  --no-allow-unauthenticated \
  --min-instances=1 \
  --platform=managed

echo "==> Service URL:"
gcloud run services describe "${SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)"

echo ""
echo "==> Smoke test (requires gcloud identity token — you must have run.invoker on the service):"
echo "    URL=\$(gcloud run services describe ${SERVICE} --project=${PROJECT_ID} --region=${REGION} --format='value(status.url)')"
echo "    curl -s -H \"Authorization: Bearer \$(gcloud auth print-identity-token)\" \"\${URL}/_stcore/health\""
echo "    Expected: ok"
