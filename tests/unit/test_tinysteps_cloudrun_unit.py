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
    # ENV is the second parameter; must fail fast if omitted
    text = _script_text()
    assert "${2:?" in text


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


def test_validate_secrets_function_exists():
    # Must have a pre-deploy validation step that checks secrets exist before build+push
    text = _script_text()
    assert "validate_secrets()" in text or "validate_secrets ()" in text


def test_validate_secrets_checks_gcloud_describe():
    # Validation must use `gcloud secrets describe` to verify each secret exists
    text = _script_text()
    assert "gcloud secrets describe" in text


def test_validate_secrets_called_before_docker_build():
    # Validation must run before any docker build/push — fail fast, not mid-deploy
    text = _script_text()
    validate_pos = text.index("validate_secrets \"${SECRET_URL}\"")
    build_pos = text.index("docker build")
    assert validate_pos < build_pos, "validate_secrets must be called before docker build"


def test_validate_secrets_prints_missing_with_create_commands():
    # Error output must list each missing secret and show the gcloud command to create it
    text = _script_text()
    assert "gcloud secrets create" in text
    assert "missing" in text.lower() or "ERROR" in text


def test_validate_ar_repo_function_exists():
    # Must validate the Artifact Registry repo exists before docker build
    text = _script_text()
    assert "validate_ar_repo()" in text or "validate_ar_repo ()" in text


def test_validate_ar_repo_checks_gcloud_artifacts_describe():
    # Must use `gcloud artifacts repositories describe` to verify the repo
    text = _script_text()
    assert "gcloud artifacts repositories describe" in text


def test_validate_ar_repo_called_before_docker_build():
    # AR repo check must run before docker build — fail fast
    text = _script_text()
    ar_pos = text.index("validate_ar_repo")
    build_pos = text.index("docker build")
    assert ar_pos < build_pos, "validate_ar_repo must be called before docker build"


def test_validate_ar_repo_prints_create_command():
    # Error output must show the exact gcloud command to create the missing repo
    text = _script_text()
    assert "gcloud artifacts repositories create" in text
