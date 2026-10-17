"""Usage fit (S2-07): the usage answer is used, not just collected.

The fit compares cores, memory and graphics with a ladder of tiers per use; the
graphics tier comes from Blender Open Data benchmarks and the years figure from
growth rates fitted to Steam's recommended requirements.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from afterlife.persona import (
    GPU_TIER_YEARS, RAM_GROWTH_GB_PER_YEAR, TIERS, assess_fit, classify_signals, gpu_tier,
)

ROOT = Path(__file__).resolve().parent.parent


def test_growth_rates_are_loaded_from_the_fitted_file_not_typed():
    fitted = json.loads((ROOT / "models" / "requirement_growth.json").read_text(encoding="utf-8"))
    assert RAM_GROWTH_GB_PER_YEAR == fitted["ram_gb_per_year"] > 0
    assert GPU_TIER_YEARS == fitted["gpu_tier_years"] > 0


def test_the_fit_reproduces_from_the_raw_steam_pull():
    raw = ROOT / "data" / "raw" / "steam_requirements.json"
    if not raw.exists():
        pytest.skip("raw Steam pull not on this machine (data/raw is not in the repo)")
    rows = json.loads(raw.read_text(encoding="utf-8"))
    xy = np.array([(r["year"], r["rec_ram_gb"]) for r in rows if r.get("rec_ram_gb")], float)
    assert round(float(np.polyfit(xy[:, 0], xy[:, 1], 1)[0]), 2) == RAM_GROWTH_GB_PER_YEAR


@pytest.mark.parametrize("gpu, tier, basis", [
    ("NVIDIA GeForce RTX 4070 Laptop GPU", 2, "benchmark"),
    ("ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Ti (0x00002489) Direct3D11 vs_5_0 ps_5_0, D3D11)", 2, "benchmark"),
    ("NVIDIA GeForce GTX 1650", 1, "benchmark"),     # a dedicated card is never below entry level
    ("AMD Radeon 780M Graphics", 0, "benchmark"),    # built-in graphics
    ("ANGLE (Intel, Intel(R) UHD Graphics 620 (0x00005917) Direct3D11)", 0, "keyword"),
    (None, 0, "unknown"),
])
def test_graphics_tiers(gpu, tier, basis):
    assert gpu_tier(gpu) == (tier, basis)


def test_the_answer_changes_the_result():
    """Same machine, different use: each use has its own ladder."""
    general = assess_fit(8, 16, "Intel UHD Graphics", "general", "self-reported")
    gamer = assess_fit(8, 16, "Intel UHD Graphics", "gamer", "self-reported")
    assert general["current_tier"] == "Heavy multitasking"
    assert gamer["current_tier"] is None and "stronger graphics" in gamer["gap"]


def test_16_gb_reported_as_15_8_still_meets_a_16_gb_tier():
    assert assess_fit(6, 15.8, None, "coder", "auto-detected")["current_tier"] == "Multi-service / Docker"


def test_browser_memory_is_a_lower_bound_so_no_years_are_claimed():
    fit = assess_fit(8, 8, None, "general", "self-reported")
    assert fit["years_of_headroom"] is None and fit["timeline"] is None
    assert any("up to 8 GB" in c for c in fit["caveats"])
    assert fit["gap"] == ["16+ GB memory (shows 8+)"]


def test_years_of_headroom_use_the_fitted_memory_rate():
    fit = assess_fit(8, 32, None, "coder", "auto-detected")   # the top coding tier needs a GPU
    assert fit["current_tier"] == "Multi-service / Docker"
    assert fit["years_of_headroom"] == round((32 - 16) / RAM_GROWTH_GB_PER_YEAR, 1)


def test_no_specs_no_fit():
    assert assess_fit(None, 8, None, "general") is None
    assert assess_fit(4, None, None, "general") is None


def test_unknown_use_falls_back_to_general():
    assert assess_fit(4, 8, None, "astronaut", "self-reported")["persona"] == "general"


def test_deep_scan_detection_names_its_reasons():
    out = classify_signals({"coder_matches": ["Visual Studio Code"], "wsl_distro_count": 2})
    assert out["persona"] == "coder"
    assert out["reasons"] == ["Visual Studio Code", "2 WSL distributions"]
    assert classify_signals({})["persona"] == "general"
    assert classify_signals({"gamer_matches": ["Steam"], "steam_game_count": 25})["reasons"][-1] == "25 Steam games"


def test_every_use_has_an_ascending_ladder():
    for tiers in TIERS.values():
        assert [t["ram_gb"] for t in tiers] == sorted(t["ram_gb"] for t in tiers)
