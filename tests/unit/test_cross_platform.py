"""
TDD tests for scripts/check_local_paths.py — the cross-platform CI guard.

Validates that hardcoded local filesystem paths are caught before they
reach main. Excluded patterns (.env, *.pdf, .claude/, .agy/) are tested
separately to confirm they don't false-positive.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check_local_paths.py"


def _run(tmp_path: Path, files: dict[str, str], exclude: list[str] | None = None) -> subprocess.CompletedProcess:
    """Write files to tmp_path, run the checker, return CompletedProcess."""
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content))

    cmd = [sys.executable, str(SCRIPT), str(tmp_path)]
    if exclude:
        cmd += ["--exclude", *exclude]
    return subprocess.run(cmd, capture_output=True, text=True)


class TestCleanFilesPass:
    """Files with no local paths should return exit code 0."""

    def test_clean_python_file(self, tmp_path):
        result = _run(tmp_path, {"src/main.py": 'print("hello world")\n'})
        assert result.returncode == 0

    def test_clean_subdirectory(self, tmp_path):
        result = _run(tmp_path, {"pkg/util.py": 'x = 1\n'})
        assert result.returncode == 0


class TestHardcodedPathsDetected:
    """Files containing local paths should return exit code 1."""

    def test_unix_home_path(self, tmp_path):
        result = _run(tmp_path, {"src/main.py": 'CONFIG = "/Users/himan/.config"\n'})
        assert result.returncode == 1
        assert "src/main.py" in result.stdout

    def test_windows_home_path(self, tmp_path):
        result = _run(tmp_path, {"src/main.py": 'PATH = "C:\\\\Users\\\\himan\\\\data"\n'})
        assert result.returncode == 1
        assert "src/main.py" in result.stdout

    def test_windows_home_path_forward_slash(self, tmp_path):
        result = _run(tmp_path, {"src/main.py": 'PATH = "C:/Users/himan/data"\n'})
        assert result.returncode == 1
        assert "src/main.py" in result.stdout

    def test_windows_unc_path(self, tmp_path):
        result = _run(tmp_path, {"src/main.py": 'PATH = "C:\\\\01Claude\\\\projects\\\\DemandPlanning"\n'})
        assert result.returncode == 1
        assert "src/main.py" in result.stdout

    def test_windows_single_backslash_path(self, tmp_path):
        result = _run(tmp_path, {"src/main.py": 'PATH = "C:\\01Claude\\projects"\n'})
        assert result.returncode == 1
        assert "src/main.py" in result.stdout

    def test_multiple_violations_single_file(self, tmp_path):
        content = 'a = "/Users/one"\nb = "C:\\\\Users\\\\two"\n'
        result = _run(tmp_path, {"multi.py": content})
        assert result.returncode == 1

    def test_violations_in_multiple_files(self, tmp_path):
        result = _run(tmp_path, {
            "a.py": 'X = "/Users/a"\n',
            "b.py": 'Y = "C:\\\\Users\\\\b"\n',
        })
        assert result.returncode == 1
        assert "a.py" in result.stdout
        assert "b.py" in result.stdout

    def test_docstring_path_flagged(self, tmp_path):
        content = '"""\nExample: C:\\\\Users\\\\himan\\\\project\n"""\n'
        result = _run(tmp_path, {"module.py": content})
        assert result.returncode == 1

    def test_comment_path_flagged(self, tmp_path):
        result = _run(tmp_path, {"module.py": "# see /Users/himan/notes.txt\n"})
        assert result.returncode == 1


class TestExcludedFilesIgnored:
    """Excluded patterns should not trigger violations even if they contain paths."""

    def test_env_example_excluded(self, tmp_path):
        result = _run(
            tmp_path,
            {".env.example": 'SMTP_SENDER=hd@thecradlebox.com\n'},
            exclude=[".env.example"],
        )
        assert result.returncode == 0

    def test_directory_exclusion(self, tmp_path):
        result = _run(
            tmp_path,
            {"docs/old.py": 'path = "/Users/himan"\n'},
            exclude=["docs/"],
        )
        assert result.returncode == 0

    def test_binary_files_skipped(self, tmp_path):
        result = _run(tmp_path, {"image.pdf": b"\x89PNG\r\n".decode("latin-1")})
        assert result.returncode == 0


class TestReportedViolations:
    """Output format should include file path and line number."""

    def test_output_contains_file_and_line(self, tmp_path):
        result = _run(tmp_path, {"bad.py": 'x = "/Users/himan"\n'})
        assert result.returncode == 1
        assert "bad.py:1" in result.stdout

    def test_exit_code_2_on_script_error(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "/nonexistent/path"],
            capture_output=True, text=True,
        )
        assert result.returncode == 2
