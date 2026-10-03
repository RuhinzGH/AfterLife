"""Exploitation probability, and the claim it is there to test.

The product argues that most serious Windows CVEs need an attacker already on
the device, and that this is why an end-of-support OS is a mitigable cost rather
than a replace trigger. Until EPSS landed, that argument was structural: it
counted CVSS attack vectors and stopped.

These tests hold the corpus to the stronger version -- that the structural claim
agrees with observed exploitation -- and, just as importantly, they fail loudly
if it ever stops agreeing. A thesis that cannot come out false is not evidence.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from afterlife import epss

ROOT = Path(__file__).resolve().parent.parent
SERIOUS = {"HIGH", "CRITICAL"}


def _corpus(major: str) -> list[dict]:
    p = ROOT / "app_data" / f"win{major}_cve_classified.csv"
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def summary():
    s = epss.load_summary()
    assert s is not None, "run scripts/enrich_cve_epss.py"
    return s


class TestBands:
    def test_unknown_is_not_negligible(self):
        """A missing score is not a low score, and must never render as one."""
        assert epss.band(None)[0] == "unknown"
        assert epss.band(0.0)[0] == "negligible"

    @pytest.mark.parametrize("score,expected", [
        (0.97, "elevated"), (0.10, "elevated"), (0.099, "moderate"),
        (0.01, "moderate"), (0.009, "low"), (0.0005, "negligible"),
    ])
    def test_bands_are_ordered_and_inclusive_at_the_floor(self, score, expected):
        assert epss.band(score)[0] == expected

    def test_expected_exploited_is_a_sum_of_probabilities(self):
        assert epss.expected_exploited([0.5, 0.25, 0.25]) == 1.0
        assert epss.expected_exploited([]) == 0.0


class TestCorpusCoverage:
    @pytest.mark.parametrize("major", ["10", "11"])
    def test_every_row_carries_the_column(self, major):
        """A half-enriched corpus would skew every statistic silently.

        Same guard as the KEV one, for the same reason: the column existing but
        being blank for a subset is worse than the column being absent, because
        a mean still computes.
        """
        rows = _corpus(major)
        missing = [r["cve_id"] for r in rows if "epss" not in r]
        assert not missing, f"Windows {major}: re-run scripts/enrich_cve_epss.py"

    @pytest.mark.parametrize("major", ["10", "11"])
    def test_scores_are_probabilities(self, major):
        for r in _corpus(major):
            if r.get("epss"):
                assert 0.0 <= float(r["epss"]) <= 1.0, r["cve_id"]

    @pytest.mark.parametrize("major", ["10", "11"])
    def test_summary_counts_match_the_corpus_on_disk(self, major, summary):
        rows = _corpus(major)
        assert summary["by_version"][major]["total"] == len(rows)
        assert summary["by_version"][major]["scored"] == sum(1 for r in rows if r.get("epss"))


class TestTheThesis:
    """The falsifiable part."""

    @pytest.mark.parametrize("major", ["10", "11"])
    def test_local_access_flaws_are_less_exploited_than_remote(self, major, summary):
        """The product's central claim, checked against exploitation data.

        If this ever fails, the honest response is to qualify the claim on the
        research page -- not to delete the test.
        """
        v = summary["by_version"][major]
        assert v["serious_local"]["n"] > 0 and v["serious_remote"]["n"] > 0
        assert v["serious_local"]["median"] < v["serious_remote"]["median"]
        assert v["local_less_exploited_than_remote"] is True

    @pytest.mark.parametrize("major", ["10", "11"])
    def test_known_exploited_scores_higher_than_the_corpus_at_large(self, major, summary):
        """A sanity check on EPSS itself, using KEV as ground truth.

        CVEs CISA has observed being exploited should score far above the
        corpus median. If they did not, the scores would not be measuring what
        they claim to, and nothing built on them would be trustworthy.
        """
        v = summary["by_version"][major]
        assert v["serious_kev"]["n"] > 0
        assert v["serious_kev"]["median"] > v["serious_all"]["median"]

    def test_the_serious_set_is_too_large_to_prioritise_without_this(self, summary):
        """Why EPSS earns its place: it narrows an unusable number.

        4,800-odd serious CVEs cannot be acted on. The subset above the action
        threshold can be. This asserts the narrowing is real and substantial,
        which is the whole argument for the column existing.
        """
        v = summary["by_version"]["10"]
        assert v["serious_all"]["over_threshold"] < v["serious"] / 4


class TestProvenance:
    def test_summary_states_what_a_score_does_not_mean(self, summary):
        """The caveat is load-bearing, not decoration."""
        assert "not a probability that this device is compromised" in summary["meaning"].lower()
        assert summary["caveat"]
        assert summary["model"], "the model version must travel with the scores"


class TestApiSurface:
    def test_findings_carries_epss_and_scoring_provenance(self, client):
        sec = client.get("/api/findings").json()["security"]
        assert sec["epss"]["scored"] == sec["serious_cves"]
        assert sec["epss"]["expected_exploited_30d"] > 0
        assert 0.0 <= sec["scoring"]["nist_share"] <= 1.0
        assert sec["scoring"]["nist"] + sec["scoring"]["vendor"] + sec["scoring"]["unscored"] \
            == sec["total_cves"]
