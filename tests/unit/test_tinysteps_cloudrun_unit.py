"""Contract tests for the TinySteps Cloud Run deploy script (issues #115, #131, epic #113).

Guard the Cloud Run deploy contract for ui/tinysteps_app.py: the deploy
script must exist, be executable, support dev/staging/prod environments with
env-specific service names and secrets, inject STREAMLIT_APP=tinysteps_app.py,
lock down access with --no-allow-unauthenticated, and route secrets via
--set-secrets (never hardcoded). No GCP credentials required — CI catches a
broken deploy shape before it reaches Cloud Run.
"""

import stat
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "gcp" / "deploy_tinysteps.sh"


def _script_text() -> str:
    return DEPLOY_SCRIPT.read_text()


def test_deploy_script_exists():
    assert DEPLOY_SCRIPT.exists(), "scripts/gcp/deploy_tinysteps.sh is missing"


def test_deploy_script_is_executable():
    mode = DEPLOY_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, "deploy_tinysteps.sh must be executable (chmod +x)"


def test_sets_streamlit_app_env_var():
    # STREAMLIT_APP must point to the TinySteps app, not Growth Spurt
    assert "STREAMLIT_APP=tinysteps_app.py" in _script_text()


def test_no_allow_unauthenticated_flag_present():
    # TinySteps is a WMS — real inventory data. Must never be publicly reachable.
    assert "--no-allow-unauthenticated" in _script_text()


def test_port_8080_for_cloud_run():
    assert "--port=8080" in _script_text()


def test_secrets_injected_via_set_secrets_not_hardcoded():
    text = _script_text()
    # Secrets must come from Secret Manager via --set-secrets using variables, not literal values
    assert "--set-secrets" in text
    assert "${SECRET_URL}" in text
    assert "${SECRET_KEY}" in text


def test_builds_for_linux_amd64():
    # Cloud Run is linux/amd64; required on Apple Silicon to avoid arch mismatch
    assert "--platform linux/amd64" in _script_text()


def test_dockerfile_webapp_used_not_automation_dockerfile():
    # Must use the webapp image, not the Playwright/Chrome automation image
    assert "-f Dockerfile.webapp" in _script_text()


def test_region_is_asia_south1():
    assert "REGION=asia-south1" in _script_text()


def test_requires_project_id_argument():
    # Script must fail fast if PROJECT_ID is not supplied
    assert "${1:?" in _script_text()


def test_push_has_retry_loop():
    # docker push can EOF mid-layer on flaky networks; script must retry
    text = _script_text()
    assert "push_with_retry" in text
    assert 'docker push "${image}"' in text
    assert "attempt" in text


def test_env_parameter_accepted():
    # ENV is the second parameter; must default to prod if omitted
    text = _script_text()
    assert "${2:-prod}" in text


def test_prod_env_uses_unqualified_service_name():
    # Backward compat: prod service is tcb-tinysteps (no suffix)
    assert "SERVICE=tcb-tinysteps\n" in _script_text()


def test_staging_env_uses_staging_service_name():
    assert "SERVICE=tcb-tinysteps-staging" in _script_text()


def test_dev_env_uses_dev_service_name():
    assert "SERVICE=tcb-tinysteps-dev" in _script_text()


def test_staging_env_uses_staging_secrets():
    text = _script_text()
    assert "supabase-url-staging" in text
    assert "supabase-key-staging" in text


def test_dev_env_uses_dev_secrets():
    text = _script_text()
    assert "supabase-url-dev" in text
    assert "supabase-key-dev" in text


def test_prod_env_uses_prod_secrets():
    # Prod secrets keep existing unqualified names (backward compat)
    text = _script_text()
    assert "SECRET_URL=supabase-url\n" in text
    assert "SECRET_KEY=supabase-key\n" in text


def test_invalid_env_exits_with_error():
    # Case statement must have a catch-all that prints an error and exits non-zero
    text = _script_text()
    assert "exit 1" in text
