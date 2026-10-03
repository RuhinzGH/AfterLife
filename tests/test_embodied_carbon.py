"""The carbon lookup must match the right device, and say when it hasn't.

A wrong match here is worse than no match: it puts a specific manufacturer's
declared number against a device that isn't theirs, which is a fabricated
measurement wearing a citation. So most of these tests are about what must NOT
match.
"""
from __future__ import annotations

import pytest

from afterlife.embodied_carbon import caveat, class_estimate, lookup


class TestClassEstimate:
    def test_laptop_distribution_is_measured_not_assumed(self):
        c = class_estimate("Laptop")
        assert c["basis"] == "class"
        assert c["n"] > 300, "the whole point is that this rests on many declarations"
        assert c["p25_kg"] < c["median_kg"] < c["p75_kg"]

    def test_manufacturing_dominates_a_laptop_footprint(self):
        """The repair-versus-replace argument depends on this being true."""
        c = class_estimate("Laptop")
        assert c["median_manufacturing_ratio"] > 0.7, (
            "if most of a laptop's carbon were operational, replacing it early "
            "would be defensible and this product's core claim would weaken"
        )

    def test_a_desktop_costs_more_than_a_laptop_than_a_phone(self):
        order = [class_estimate(c)["median_kg"]
                 for c in ("Mobile", "Laptop", "Desktop computer")]
        assert order == sorted(order), f"implausible ordering: {order}"

    def test_unknown_class_returns_nothing_rather_than_guessing(self):
        assert class_estimate("Toaster") is None


class TestLookup:
    @pytest.mark.parametrize("maker, model, expect", [
        ("Dell Inc.", "XPS 13 9300", "XPS 13 9300"),
        ("Dell", "Latitude 5410", "Latitude 5410"),
        ("LENOVO", "ThinkBook 14s", "ThinkBook 14s"),
        ("Hewlett-Packard", "Chromebook x360 14b", "Chromebook x360 14b"),
    ])
    def test_matches_a_real_model(self, maker, model, expect):
        """Manufacturer strings arrive from firmware in vendor-specific forms;
        all of these must fold onto the same key."""
        got = lookup(maker, model, device_class="Laptop")
        assert got["basis"] == "matched", f"{maker} {model} fell back to the class median"
        assert got["model"] == expect
        assert got["gwp_total_kg"] > 0

    def test_falls_back_to_the_class_when_the_model_is_unknown(self):
        got = lookup("Dell Inc.", "Latitude 999999 Imaginary", device_class="Laptop")
        assert got["basis"] == "class", "an unknown model must not be matched to a real one"
        assert got["n"] > 300

    def test_a_cryptic_board_code_uses_the_family_instead(self):
        """Win32_ComputerSystem.Model is often a SKU like '8A78'; SystemFamily
        carries the name a person would recognise."""
        got = lookup("Dell Inc.", "8A78", family="XPS 13 9300", device_class="Laptop")
        assert got["basis"] == "matched"
        assert "XPS" in got["model"]

    def test_never_matches_across_manufacturers(self):
        """The single most damaging failure: Dell's declared figure reported for
        a Lenovo machine."""
        got = lookup("Lenovo", "XPS 13 9300", device_class="Laptop")
        assert got["basis"] == "class", "a Dell model matched against a Lenovo device"

    def test_one_shared_word_is_not_a_match(self):
        """'Latitude' alone is shared by dozens of unrelated Dell models."""
        got = lookup("Dell Inc.", "Latitude", device_class="Laptop")
        assert got["basis"] == "class"

    def test_no_class_and_no_match_returns_nothing(self):
        assert lookup("Nobody", "Nothing") is None

    def test_matched_result_carries_its_own_provenance(self):
        got = lookup("Dell Inc.", "XPS 13 9300", device_class="Laptop")
        assert got["manufacturer"] and got["match_score"] >= 0.6
        assert got["gwp_total_kg"] > 0


def test_the_caveat_travels_with_the_data():
    """Boavizta's guidance is that cross-manufacturer comparison is unsound. If
    that warning lives only on their website it will not reach a reader here."""
    text = caveat().lower()
    assert "manufacturer" in text and ("not" in text or "unsound" in text)
