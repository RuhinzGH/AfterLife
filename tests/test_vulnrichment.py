"""Recovering a CVSS vector for CVEs NVD never scored.

This module was written to survive NIST's April 2026 retreat from enrichment,
and it shipped with no tests at all. That is the wrong way round for code whose
entire job is to be correct about provenance: it decides which severities enter
the corpus and what `metric_source` says about them, and a silent mistake here
would mislabel rows rather than fail.

The tests are deliberately offline. Every branch that matters is pure selection
logic over a CVE record, so synthetic records exercise it exactly and a CI run
does not depend on cveawg.mitre.org being up.
"""
from __future__ import annotations

import pytest

from afterlife import vulnrichment as vr


def _metric(**kw):
    """One CVSS block, defaulting to a complete, valid v3.1 vector."""
    base = {"baseScore": 7.5, "baseSeverity": "high", "attackVector": "network",
            "privilegesRequired": "none", "userInteraction": "none",
            "scope": "unchanged"}
    base.update(kw)
    return base


def _record(cna=None, adp=None):
    rec = {"containers": {}}
    if cna is not None:
        rec["containers"]["cna"] = cna
    if adp is not None:
        rec["containers"]["adp"] = adp
    return rec


def _party(short_name, metrics):
    return {"providerMetadata": {"shortName": short_name}, "metrics": metrics}


class TestVersionPreference:
    def test_newest_cvss_wins(self):
        """Same preference order as afterlife.nvd, so a recovered row is
        comparable with a natively-scored one rather than subtly different."""
        m = {"cvssV3_0": _metric(baseScore=5.0), "cvssV3_1": _metric(baseScore=6.0),
             "cvssV4_0": _metric(baseScore=9.0)}
        data, version = vr._vector_from(m)
        assert data["baseScore"] == 9.0
        assert version == "4.0"

    def test_falls_back_to_older_versions(self):
        data, version = vr._vector_from({"cvssV3_0": _metric(baseScore=5.0)})
        assert (data["baseScore"], version) == (5.0, "3.0")

    def test_a_metric_with_no_base_score_is_not_a_vector(self):
        """A container can exist and carry nothing scoreable."""
        assert vr._vector_from({"cvssV3_1": {"attackVector": "network"}}) is None

    def test_no_cvss_at_all(self):
        assert vr._vector_from({"other": {"baseScore": 9.9}}) is None


class TestContainerPreference:
    def test_cisa_adp_is_preferred_over_the_cna(self):
        """Not because CISA knows the product better -- the vendor obviously
        does -- but because it is the neutral party, which is the question
        `metric_source` exists to answer."""
        rec = _record(cna=_party("microsoft", [{"cvssV3_1": _metric(baseScore=4.0)}]),
                      adp=[_party("cisa-adp", [{"cvssV3_1": _metric(baseScore=8.0)}])])
        first_metric, origin = vr._containers(rec)[0]
        assert origin == "adp:cisa-adp"
        assert first_metric["cvssV3_1"]["baseScore"] == 8.0

    def test_a_non_cisa_adp_does_not_jump_the_cna(self):
        """Only CISA's ADP gets the promotion; other publishers stay in order."""
        rec = _record(cna=_party("fortinet", [{"cvssV3_1": _metric()}]),
                      adp=[_party("someone-else", [{"cvssV3_1": _metric()}])])
        origins = [o for _, o in vr._containers(rec)]
        assert origins[0] != "adp:cisa-adp"
        assert "cna:fortinet" in origins

    def test_missing_provider_name_still_yields_a_usable_origin(self):
        rec = _record(cna={"metrics": [{"cvssV3_1": _metric()}]})
        assert vr._containers(rec)[0][1] == "cna"

    def test_an_empty_record_has_no_containers(self):
        assert vr._containers({}) == []
        assert vr._containers({"containers": {}}) == []


class TestLookupNeverRaises:
    """A lookup failure for one CVE must not abort a corpus rebuild of several
    thousand. That is stated in the module docstring; this holds it to it."""

    def test_network_failure_returns_none(self, monkeypatch):
        def boom(*a, **k):
            raise ConnectionError("no route to host")
        monkeypatch.setattr(vr, "get_json", boom)
        assert vr.lookup("CVE-2026-0001") is None

    def test_malformed_payload_returns_none(self, monkeypatch):
        monkeypatch.setattr(vr, "get_json", lambda *a, **k: {"nonsense": True})
        assert vr.lookup("CVE-2026-0001") is None

    def test_a_record_with_no_scores_returns_none(self, monkeypatch):
        rec = _record(cna=_party("acme", [{"other": {"baseScore": 1.0}}]))
        monkeypatch.setattr(vr, "get_json", lambda *a, **k: rec)
        assert vr.lookup("CVE-2026-0001") is None


class TestReturnedShape:
    @pytest.fixture
    def found(self, monkeypatch):
        rec = _record(adp=[_party("cisa-adp", [{"cvssV3_1": _metric()}])])
        monkeypatch.setattr(vr, "get_json", lambda *a, **k: rec)
        return vr.lookup("CVE-2013-3900")

    def test_fields_match_what_the_corpus_builder_writes(self, found):
        """These key names are the contract with scripts/build_cve_corpus.py --
        a rename here would silently write empty columns."""
        assert set(found) >= {"base_score", "severity", "attack_vector",
                              "privileges_required", "metric_source",
                              "metric_version"}

    def test_enums_are_upper_cased(self, found):
        """NVD yields upper case and the classifier compares against it; the
        CVE record yields lower. Normalising at this boundary is what stops
        every recovered row falling through mitigation.classify."""
        assert found["attack_vector"] == "NETWORK"
        assert found["privileges_required"] == "NONE"
        assert found["severity"] == "HIGH"

    def test_provenance_is_never_laundered(self, found):
        """The whole point: a row recovered here stays distinguishable from one
        NIST scored, forever after."""
        assert found["metric_source"] == "adp:cisa-adp"
        assert found["metric_source"] != "nvd@nist.gov"
        assert found["metric_type"] == "Secondary"
