"""Shared fixtures.

These tests drive the real FastAPI app through TestClient rather than calling
functions directly. That is deliberate: nearly every regression this suite has
actually caught lived in the wiring -- a field not threaded through, a passport
signed before a value was attached, two endpoints disagreeing about the same
corpus -- and unit tests on the functions in isolation would have passed through
all of them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)
