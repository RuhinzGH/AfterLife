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


@pytest.fixture
def device():
    """A worn but serviceable Windows 10 machine, as the collector would report it.

    Returns a factory so a test can vary one field without mutating the fixture
    for everything else in the session.
    """
    def _make(**overrides):
        base = {
            "collected_at": "2026-08-01T12:00:00",
            "manufacturer": "Dell", "model": "Latitude 5490",
            "cpu_name": "Intel Core i5-8250U", "cpu_cores": 4, "cpu_logical": 8,
            "ram_gb": 8.0, "gpu_name": "Intel UHD Graphics 620",
            "sysdrive_total_gb": 476.0, "sysdrive_free_gb": 402.0,
            "disk_media_type": "SSD", "disk_health": "Healthy",
            "battery_present": True, "battery_health_pct": 71.0,
            "os_caption": "Microsoft Windows 10 Pro", "os_version": "10.0.19045",
            "uefi": True, "secure_boot_on": True, "collected_elevated": True,
            "tpm_present": True, "tpm_spec_version": "2.0", "tpm_enabled": True,
        }
        base.update(overrides)
        return base
    return _make


@pytest.fixture
def clean_state():
    """A freshly reset machine's clean-state block."""
    def _make(**overrides):
        base = {
            "checked": True, "user_profiles": 1, "user_files": 3,
            "user_files_capped": False, "wifi_profiles": 1,
            "installed_apps": 19, "os_install_days": 2.0,
        }
        base.update(overrides)
        return base
    return _make
