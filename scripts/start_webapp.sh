#!/usr/bin/env bash
# Streamlit web-app entrypoint — issue #114 (epic #113).
# Runs one of the Streamlit apps from ui/. One image, either app:
# set STREAMLIT_APP at run/deploy time (default: tinysteps_app.py).
#
# Cloud Run: the platform injects $PORT (default 8080) and expects the
# container to listen on it. Locally $PORT is unset, so fall back to
# Streamlit's default 8501. Bind 0.0.0.0 so the platform can reach it.
set -euo pipefail

APP="${STREAMLIT_APP:-tinysteps_app.py}"
PORT="${PORT:-8501}"

exec streamlit run "ui/${APP}" \
  --server.port="${PORT}" \
  --server.address="0.0.0.0" \
  --server.headless=true \
  --browser.gatherUsageStats=false
