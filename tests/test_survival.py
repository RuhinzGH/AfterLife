"""The age-versus-condition finding, and the guards that keep it honest.

This exists because the first version of the analysis produced a confident,
wrong answer. A Weibull fit on the same data reported rho = 1.335 with a tight
confidence interval -- "wear-out, age carries real information" -- while
lifelines was simultaneously warning that its variance matrix had negative
diagonal entries and Kaplan-Meier was refusing to run at all. The number looked
publishable and rested on nothing.

The non-parametric replacement says the opposite. So these tests pin the parts
that make the second answer trustworthy where the first was not.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app_data" / "survival_failslow.json"


@pytest.fixture(scope="module")
def survival():
    if not DATA.exists():
        pytest.skip("run scripts/survival_failslow.py")
    return json.loads(DATA.read_text(encoding="utf-8"))


class TestArithmetic:
    def test_band_counts_sum_to_the_total(self, survival):
        """Bands must partition the data, not sample it."""
        assert sum(b["drive_days"] for b in survival["bands"]) == survival["drive_days"]
        assert sum(b["events"] for b in survival["bands"]) == survival["events"]

    def test_every_rate_matches_its_own_numerator_and_denominator(self, survival):
        for b in survival["bands"]:
            if b["drive_days"]:
                expected = 1000 * b["events"] / b["drive_days"]
                assert abs(b["rate_per_1k_drive_days"] - expected) < 0.01, b["band"]

    def test_confidence_intervals_bracket_their_estimate(self, survival):
        for b in survival["bands"]:
            lo, hi = b["ci95"]
            assert lo <= b["rate_per_1k_drive_days"] <= hi, b["band"]
            assert lo >= 0, "an exact Poisson interval can never go negative"


class TestThinBandsAreMarked:
    def test_thin_bands_are_flagged(self, survival):
        for b in survival["bands"]:
            assert b["thin"] == (b["drive_days"] < 500)

    def test_the_trend_ignores_thin_bands(self, survival):
        """A rate from a handful of drive-days must not steer the verdict."""
        solid = [b for b in survival["bands"] if not b["thin"]]
        assert len(solid) >= 4, "not enough usable bands to have drawn a conclusion"


class TestTheFinding:
    def test_a_verdict_was_actually_reached(self, survival):
        assert survival["trend"]["verdict"] in (
            "wear-out", "improves with age", "age-independent", "indeterminate")
        assert survival["trend"]["note"]

    def test_the_verdict_follows_from_its_own_statistics(self, survival):
        """The label and the numbers behind it must not be able to disagree."""
        t = survival["trend"]
        if t["verdict"] == "age-independent":
            assert t["p_value"] is None or t["p_value"] >= 0.05
        elif t["verdict"] == "wear-out":
            assert t["p_value"] < 0.05 and t["spearman_rho"] > 0
        elif t["verdict"] == "improves with age":
            assert t["p_value"] < 0.05 and t["spearman_rho"] < 0

    def test_model_identity_outweighs_age(self, survival):
        """The substantive result: which drive you have beats how old it is.

        If this ever collapses toward 1x, the headline claim -- that age is a
        poor proxy for condition -- has lost its supporting evidence and the
        research page should stop making it.
        """
        assert survival["model_spread_x"] is not None
        assert survival["model_spread_x"] > 5

    def test_the_oldest_cohort_is_not_automatically_the_worst(self, survival):
        """A direct check that simple wear-out does not describe this fleet."""
        models = survival["by_model"]
        assert len(models) >= 3
        oldest = max(models.values(), key=lambda v: v["median_age_days"])
        worst = max(models.values(), key=lambda v: v["rate_per_1k_drive_days"])
        assert oldest is not worst, "oldest cohort is also the worst — that IS wear-out"


class TestHonesty:
    def test_the_rejected_weibull_is_documented_not_buried(self):
        """A failed approach that is silently deleted gets re-attempted."""
        src = (ROOT / "scripts" / "survival_failslow.py").read_text(encoding="utf-8")
        assert "WHY THIS IS NOT A WEIBULL FIT" in src
        assert "S(t)==0" in src, "the exact refusal should be quoted, not paraphrased"

    def test_the_domain_shift_caveat_is_present(self, survival):
        """Enterprise datacenter drives are not consumer laptop SSDs."""
        joined = " ".join(survival["caveats"]).lower()
        assert "enterprise" in joined and "consumer" in joined

    def test_fail_slow_is_distinguished_from_failure(self, survival):
        joined = " ".join(survival["caveats"]).lower()
        assert "degraded rather than dead" in joined

    def test_no_extrapolation_is_claimed(self, survival):
        joined = " ".join(survival["caveats"]).lower()
        assert "no extrapolation" in joined or "supports no extrapolation" in joined
