#!/usr/bin/env bash
# Deploy TinySteps (ui/tinysteps_app.py) to Cloud Run — issue #115 (epic #113).
#
# Usage: ./scripts/gcp/deploy_tinysteps.sh PROJECT_ID
#
# Builds Dockerfile.webapp for linux/amd64, pushes to Artifact Registry, and
# deploys (or updates) the tcb-tinysteps Cloud Run service.
#
# Prerequisites:
#   - gcloud authenticated with permission to push to AR and deploy Cloud Run
#   - SUPABASE_URL and SUPABASE_KEY secrets exist in Secret Manager for PROJECT_ID
#     (created by the automation job setup; re-create with:
#      echo -n "VALUE" | gcloud secrets create supabase-url --data-file=- --project=PROJECT_ID)
#   - Docker installed and running
#
# Security: service is deployed --no-allow-unauthenticated (IAM-invoker only)
# until the auth gate (issue #117) lands. Never remove this flag without #117.
set -euo pipefail

PROJECT_ID="${1:?Usage: deploy_tinysteps.sh PROJECT_ID}"

REGION=asia-south1
REPO=tcb-spike
SERVICE=tcb-tinysteps
IMAGE="asia-south1-docker.pkg.dev/${PROJECT_ID}/${REPO}/tinysteps:latest"

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
  --set-secrets=SUPABASE_URL=supabase-url:latest,SUPABASE_KEY=supabase-key:latest \
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
