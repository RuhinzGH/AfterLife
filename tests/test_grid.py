"""The carbon break-even, on the grid the device is actually plugged into.

The research page quotes ~21 years "even on the dirtiest grid". True, and the
conservative framing, but it hides the variable that decides the answer: the
break-even spans an order of magnitude between grids. These tests hold the
per-country version to the properties that make it trustworthy -- above all that
it says which claim it is making, and refuses to dress the world average up as
the user's own grid.
"""
from __future__ import annotations

import pytest

from afterlife import grid


class TestIntensity:
    def test_known_country_resolves_to_its_own_grid(self):
        fr = grid.intensity("FR")
        assert fr["basis"] == "country"
        assert fr["region"] == "France"

    def test_case_is_not_significant(self):
        assert grid.intensity("fr")["region"] == grid.intensity("FR")["region"]

    @pytest.mark.parametrize("code", [None, "", "ZZ", "XX"])
    def test_unknown_country_falls_back_to_the_world_and_says_so(self, code):
        """The fallback must be visible. 'Your grid' and 'the world's grid' are
        different claims, and presenting the second as the first is the bug."""
        g = grid.intensity(code)
        assert g["basis"] == "world"
        assert g["region"] == "World"

    def test_clean_and_dirty_grids_are_ordered_as_expected(self):
        """A sanity check on the data itself, not just the plumbing."""
        assert grid.intensity("FR")["gco2_kwh"] < grid.intensity("IN")["gco2_kwh"]


class TestBreakEven:
    def test_a_dirty_grid_repays_faster_than_a_clean_one(self):
        """The entire reason this is per-country."""
        india = grid.break_even("IN", 300.0)
        france = grid.break_even("FR", 300.0)
        assert india["years"] < france["years"]
        # And by a lot -- if this ever collapses to near-parity the grid data
        # has broken, because these two grids differ by more than 10x.
        assert france["years"] > india["years"] * 5

    def test_a_heavier_device_takes_longer_to_repay(self):
        light = grid.break_even("DE", 200.0)
        heavy = grid.break_even("DE", 400.0)
        assert heavy["years"] > light["years"]

    def test_no_efficiency_gain_never_repays(self):
        """A like-for-like swap saves no energy, so its embodied cost is sunk.

        The honest answer is 'never', not a very large number of years.
        """
        r = grid.break_even("IN", 300.0, old_tdp_w=28.0, new_tdp_w=28.0)
        assert r["repays"] is False
        assert "never repay" in r["headline"]
        assert "years" not in r

    def test_an_implausibly_clean_grid_is_not_treated_as_a_finding(self):
        """Some countries report ~0 gCO2/kWh because almost nothing is measured.

        Dividing by that produces an enormous number that reads like a result.
        """
        clean = [c for c, v in (grid._load().get("countries") or {}).items()
                 if v["gco2_kwh"] < 5.0]
        for code in clean:
            assert grid.break_even(code, 300.0)["repays"] is False


class TestHonesty:
    def test_the_world_fallback_is_not_phrased_as_the_users_grid(self):
        assert "world-average" in grid.break_even(None, 300.0)["headline"]
        assert "On World's grid" not in grid.break_even(None, 300.0)["headline"]

    def test_embodied_basis_is_reported(self):
        """Whether the carbon figure was declared for this model or defaulted."""
        assert grid.break_even("DE", 251.0, embodied_basis="matched")["embodied_basis"] == "matched"
        assert grid.break_even("DE", None)["embodied_basis"] == "default"

    def test_authored_assumptions_travel_with_every_answer(self):
        """The duty cycle decides the result and is a judgement call, so it is
        stated on the response rather than buried in the module."""
        a = grid.break_even("DE", 300.0)["assumptions"]
        assert a["hours_per_year"] == grid.HOURS_PER_YEAR
        assert a["load_factor"] == grid.LOAD_FACTOR
        assert "authored, not measured" in a["note"]

    def test_the_grid_figure_carries_its_year_and_source(self):
        g = grid.break_even("DE", 300.0)["grid"]
        assert g["year"] >= 2020
        assert "Our World in Data" in g["source"]


class TestApiSurface:
    def test_assess_returns_a_break_even_joined_to_declared_carbon(self, client):
        r = client.post("/api/assess", json={
            "hardware_trust": 70, "age_years": 6.0,
            "manufacturer": "Dell", "make_model": "Latitude 5490",
            "product_category": "Laptop",
        }).json()
        ct = r["carbon_tradeoff"]
        assert ct is not None
        assert ct["repays"] is True
        # Boavizta publishes an LCA for this model, so the numerator should be
        # the declared figure rather than the 300 kg default.
        assert ct["embodied_basis"] == "matched"
        assert ct["embodied_kg"] != grid.DEFAULT_EMBODIED_KG


def test_assessment_uses_the_class_median_when_the_model_is_unknown(client):
    """A browser scan cannot name the laptop model, so the class median applies.
    It used to fall back to a flat 300 kg default while labelling it a class figure."""
    from afterlife.embodied_carbon import class_estimate
    r = client.post("/api/assess", json={"hardware_trust": 75, "eol_risk": 0.2,
                                         "age_years": 4, "product_category": "Laptop",
                                         "timezone": "Asia/Kolkata"}).json()
    ct = r["carbon_tradeoff"]
    assert ct["embodied_basis"] == "class"
    assert ct["embodied_kg"] == class_estimate("Laptop")["median_kg"]
