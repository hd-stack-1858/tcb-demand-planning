"""Contract tests for the TinySteps Cloud Run deploy script (issue #115, epic #113).

Guard the Cloud Run deploy contract for ui/tinysteps_app.py: the deploy
script must exist, be executable, target the correct service name, inject
STREAMLIT_APP=tinysteps_app.py, lock down access with
--no-allow-unauthenticated, and route secrets via --set-secrets (never
hardcoded). No GCP credentials required — CI catches a broken deploy shape
before it reaches Cloud Run.
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


def test_targets_correct_service_name():
    assert "SERVICE=tcb-tinysteps" in _script_text()


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
    # Secrets must come from Secret Manager via --set-secrets, not be literal values
    assert "--set-secrets" in text
    assert "SUPABASE_URL=supabase-url:latest" in text
    assert "SUPABASE_KEY=supabase-key:latest" in text


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
