#!/usr/bin/env bash
# Reusable test runner — same script for local machine, CI, or a sandbox.
# Creates/reuses a venv, installs deps, and runs pytest with a chosen tier.
#
# Usage:
#   ./scripts/run_tests.sh unit          # + integration_mocked — no credentials needed, runs anywhere
#   ./scripts/run_tests.sh integration   # requires .env.dev (real dev Supabase)
#   ./scripts/run_tests.sh all           # both tiers
#
# Env vars:
#   VENV_DIR   Where to create/reuse the virtualenv (default: .venv-test)
#   PYTHON     Python interpreter to use (default: python3)
#
# NO test in this repo may hit prod. Integration tests require TCB_ENV=dev,
# which tests/conftest.py sets automatically — never point this script's
# .env.dev at prod credentials.

set -euo pipefail

TIER="${1:?Usage: run_tests.sh <unit|integration|all>}"
VENV_DIR="${VENV_DIR:-.venv-test}"
PYTHON="${PYTHON:-python3}"

cd "$(dirname "$0")/.."

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install -q -r requirements-dev.txt

case "$TIER" in
  unit)
    "$VENV_DIR/bin/python3" -m pytest tests/unit tests/integration_mocked \
      -m "unit or integration_mocked" -v
    ;;
  integration)
    if [ ! -f .env.dev ]; then
      echo "ERROR: .env.dev not found — integration tests need real dev Supabase credentials." >&2
      echo "Never point .env.dev at prod." >&2
      exit 1
    fi
    "$VENV_DIR/bin/python3" -m pytest tests -m integration -v
    ;;
  all)
    "$0" unit
    "$0" integration
    ;;
  *)
    echo "Unknown tier '$TIER' — expected unit, integration, or all" >&2
    exit 1
    ;;
esac
