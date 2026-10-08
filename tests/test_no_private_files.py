"""Nothing private may ever be tracked in this repository.

Course documents, sprint records, the live-site signing key and code held for
later sprints live in `_private/`, which is git-ignored. This test fails if any
of it (or a signing key anywhere) is ever added to version control.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = re.compile(r"^_private/|^CLAUDE\.md$|SECRET|^data/keys/|\.key$|^venv/")


def _tracked() -> list[str]:
    r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("not a git checkout")
    return r.stdout.splitlines()


def test_no_private_file_is_tracked():
    assert [f for f in _tracked() if PRIVATE.search(f)] == []


def test_the_private_folder_is_ignored():
    r = subprocess.run(["git", "check-ignore", "-q", "_private/x"], cwd=ROOT)
    assert r.returncode == 0, "_private/ must be listed in .gitignore"
