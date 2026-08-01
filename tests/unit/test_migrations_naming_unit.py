"""Unit tests for migration filename sequence validation (issue #41).

No DB, no network — asserts the duplicate-sequence guard in
setup/apply_migrations.py is pure filename logic: two files sharing a sequence
token raise MigrationError before anything runs, and letter-suffixed sequences
(006b) are distinct and sort in the right order.
"""

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from setup import apply_migrations as m  # noqa: E402

pytestmark = pytest.mark.unit


def _migrations_dir(*names: str) -> Path:
    d = Path(tempfile.mkdtemp())
    for name in names:
        (d / name).write_text("")
    return d


def test_sequence_token_extraction():
    assert m._sequence_token("006_add_x.sql") == "006"
    assert m._sequence_token("006b_drop_y.sql") == "006b"
    assert m._sequence_token("010_rename_az.sql") == "010"


def test_duplicate_sequence_raises():
    d = _migrations_dir("006_add_x.sql", "006_drop_y.sql")
    with pytest.raises(m.MigrationError, match="duplicate migration sequence"):
        m.list_migrations(d)


def test_suffixed_sequence_is_distinct_and_ordered():
    d = _migrations_dir("006b_drop_y.sql", "006_add_x.sql")
    assert [f.name for f in m.list_migrations(d)] == [
        "006_add_x.sql",
        "006b_drop_y.sql",
    ]


def test_unique_sequences_pass():
    d = _migrations_dir("001_a.sql", "002_b.sql", "010_c.sql")
    assert [f.name for f in m.list_migrations(d)] == [
        "001_a.sql",
        "002_b.sql",
        "010_c.sql",
    ]
