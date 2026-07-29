#!/usr/bin/env bash
# Builds (if needed) and runs any automation/*.py script inside the real
# production container (Dockerfile at repo root) — the same image used for
# local verification of #32/#33/#34, and the eventual Cloud Run deploy (#35).
#
# Usage:
#   TCB_ENV=dev ./scripts/run_in_docker.sh automation/blinkit_scraper.py --dry-run
#   TCB_ENV=dev ./scripts/run_in_docker.sh automation/blinkit_soh_scraper.py
#
# Env vars:
#   TCB_ENV      dev or prod (default: dev — never point this at prod by accident)
#   DATA_DIR     host directory mounted at /app/data (default: ./data)
#   NO_BUILD     set to skip the image rebuild (faster re-runs during iteration)
#
# Real Chrome (needed by the Blinkit scripts) has no Linux ARM64 build —
# this always builds/runs with --platform linux/amd64, which also matches
# Cloud Run's default architecture.

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: TCB_ENV=dev ./scripts/run_in_docker.sh <automation/script.py> [args...]" >&2
  exit 1
fi

cd "$(dirname "$0")/.."

TCB_ENV="${TCB_ENV:-dev}"
DATA_DIR="${DATA_DIR:-$(pwd)/data}"
ENV_FILE=".env"
[ "$TCB_ENV" = "dev" ] && ENV_FILE=".env.dev"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found — needed for SUPABASE_URL/SUPABASE_KEY etc." >&2
  exit 1
fi

mkdir -p "$DATA_DIR"

if [ -z "${NO_BUILD:-}" ]; then
  docker build --platform linux/amd64 -t tcb-automation .
fi

docker run --rm --platform linux/amd64 \
  --env-file "$ENV_FILE" \
  -e TCB_ENV="$TCB_ENV" \
  -v "$DATA_DIR:/app/data" \
  tcb-automation "$@"
