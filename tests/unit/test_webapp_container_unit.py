"""Contract tests for the Streamlit web-app container (issue #114, epic #113).

Guard the Cloud Run deploy contract for ui/tinysteps_app.py and
ui/growthspurt_app.py: the image must exist, use the python:3.11-slim base
(runtime.txt), expose 8501, probe Streamlit's /_stcore/health, and boot via
scripts/start_webapp.sh. These are file-level assertions (no Docker daemon
needed), so they run anywhere — CI catches a container that regresses to an
un-runnable shape before it reaches Cloud Run.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_dockerfile_webapp_exists():
    assert (REPO_ROOT / "Dockerfile.webapp").exists()


def test_base_image_matches_runtime_txt():
    runtime = (REPO_ROOT / "runtime.txt").read_text().strip()
    assert runtime == "python-3.11"
    assert "FROM python:3.11-slim" in (REPO_ROOT / "Dockerfile.webapp").read_text()


def test_serves_streamlit_on_8501():
    assert "EXPOSE 8501" in (REPO_ROOT / "Dockerfile.webapp").read_text()


def test_healthcheck_probes_stcore_health():
    text = (REPO_ROOT / "Dockerfile.webapp").read_text()
    assert "HEALTHCHECK" in text
    assert "/_stcore/health" in text


def test_boots_via_start_webapp():
    text = (REPO_ROOT / "Dockerfile.webapp").read_text()
    entrypoint = REPO_ROOT / "scripts" / "start_webapp.sh"
    assert "scripts/start_webapp.sh" in text
    assert entrypoint.exists()
    assert "streamlit run" in entrypoint.read_text()


def test_entrypoint_listens_on_port_and_binds_all_interfaces():
    entrypoint = (REPO_ROOT / "scripts" / "start_webapp.sh").read_text()
    assert "--server.port" in entrypoint
    assert "--server.address=\"0.0.0.0\"" in entrypoint


def test_entrypoint_runs_either_app():
    entrypoint = (REPO_ROOT / "scripts" / "start_webapp.sh").read_text()
    assert "STREAMLIT_APP:-tinysteps_app.py" in entrypoint


def test_dockerignore_excludes_streamlit_secrets():
    dockerignore = (REPO_ROOT / ".dockerignore").read_text()
    assert ".streamlit/secrets.toml" in dockerignore
