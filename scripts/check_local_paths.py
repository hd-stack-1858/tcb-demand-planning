#!/usr/bin/env python3
"""
Cross-platform CI guard — scans files for hardcoded local filesystem paths.

Exit codes:
  0 — clean (no violations)
  1 — violations found
  2 — script error (bad args, directory not found)

Usage:
  python scripts/check_local_paths.py <directory> [--exclude PATTERN ...]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Patterns that indicate a hardcoded local filesystem path.
_PATH_PATTERNS = [
    re.compile(r"/Users/"),           # macOS home directories
    re.compile(r"C:\\\\Users"),       # Windows home (escaped backslashes)
    re.compile(r"C:\\Users"),         # Windows home (single backslash)
    re.compile(r"C:/Users"),          # Windows home (forward slash)
    re.compile(r"C:\\\\[A-Za-z0-9]"),  # Windows paths like C:\01Claude\, C:\Projects\, etc.
    re.compile(r"C:/[A-Za-z0-9]"),     # Windows paths with forward slashes
]

# Binary file extensions — skip these entirely.
_BINARY_EXTENSIONS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".gz", ".tar", ".7z",
    ".xlsx", ".xls", ".csv",
    ".exe", ".dll", ".so", ".dylib",
})


def _is_excluded(rel_path: str, exclude_patterns: list[str]) -> bool:
    """Check if a relative path matches any exclusion pattern."""
    for pattern in exclude_patterns:
        if rel_path == pattern or rel_path.startswith(pattern):
            return True
        # Directory exclusion: pattern ends with /
        if pattern.endswith("/") and rel_path.startswith(pattern):
            return True
    return False


def scan_directory(
    root: Path, exclude_patterns: list[str]
) -> list[tuple[str, int, str]]:
    """
    Scan all text files under root for hardcoded local paths.

    Returns list of (relative_path, line_number, matched_line) tuples.
    """
    violations: list[tuple[str, int, str]] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        # Skip binary extensions
        if path.suffix.lower() in _BINARY_EXTENSIONS:
            continue

        rel = str(path.relative_to(root))

        # Check exclusion patterns
        if _is_excluded(rel, exclude_patterns):
            continue

        # Try to read as text; skip binary files that slip through
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        for line_num, line in enumerate(text.splitlines(), start=1):
            for pattern in _PATH_PATTERNS:
                if pattern.search(line):
                    violations.append((rel, line_num, line.strip()))
                    break  # one match per line is enough

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check for hardcoded local filesystem paths."
    )
    parser.add_argument("directory", help="Directory to scan")
    parser.add_argument(
        "--exclude", nargs="*", default=[],
        help="Relative paths or prefixes to skip (e.g. .env.example docs/)",
    )
    args = parser.parse_args()

    root = Path(args.directory).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 2

    violations = scan_directory(root, args.exclude)

    if not violations:
        return 0

    for rel_path, line_num, line_content in violations:
        print(f"{rel_path}:{line_num}: {line_content}")

    print(f"\n{len(violations)} violation(s) found. Hardcoded local paths must be "
          "moved to gitignored files (.env, .env.dev).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
