"""Secrets and settings, read at run time and never stored in the code.

On the live server they are environment variables (set in Render's dashboard).
On a developer's laptop they can live in a git-ignored `.env` file at the repo
root, one `NAME=value` per line. An environment variable always wins.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, _, value = line.partition("=")
            values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def secret(name: str) -> str:
    """The value of a secret, or "" when it is not configured."""
    return os.environ.get(name, "").strip() or _dotenv().get(name, "")
