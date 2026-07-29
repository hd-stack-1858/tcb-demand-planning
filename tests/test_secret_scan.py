"""
Guards against secrets in the repo. Mirrors the CI gitleaks job
(.github/workflows/secret-scan.yml) so a missed CI run is still caught locally.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

# Doesn't touch the DB directly, but tests/conftest.py's autouse fixture
# still requires dev credentials to collect this file — see docs/testing.md
# "Known limitation" for the fix (move under tests/unit/).
pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_gitleaks_config_exists():
    assert (REPO_ROOT / ".gitleaks.toml").exists()


def test_ci_workflow_exists():
    assert (REPO_ROOT / ".github/workflows/secret-scan.yml").exists()


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks not installed locally")
def test_no_secrets_in_full_history():
    result = subprocess.run(
        [
            "gitleaks", "detect",
            "--source", str(REPO_ROOT),
            "--log-opts=--all",
            "--config", str(REPO_ROOT / ".gitleaks.toml"),
            "--no-banner",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"gitleaks found potential secrets:\n{result.stdout}\n{result.stderr}"
    )
