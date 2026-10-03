"""Who scored a CVE, and what the flattened row says about it.

`_primary_metric` used to return one anonymous dict, so a corpus scored entirely
by vendors was indistinguishable from one scored by NIST. That stopped being
hypothetical in April 2026, when NIST stopped routinely enriching CVEs -- the
Windows 11 corpus is now 84% self-scored by Microsoft.

The selection order is the load-bearing part: it decides which of several
competing severities enters the corpus. These tests pin it against synthetic
payloads, so they exercise the real branches without depending on NVD being up.
"""
from __future__ import annotations

import datetime as dt

import pytest

from afterlife import nvd

NIST = "nvd@nist.gov"
VENDOR = "secure@microsoft.com"


def _entry(source, type_, score=7.5, version="3.1", **data):
    d = {"baseScore": score, "baseSeverity": "HIGH", "attackVector": "NETWORK",
         "privilegesRequired": "NONE", "userInteraction": "NONE",
         "scope": "UNCHANGED", "version": version}
    d.update(data)
    return {"source": source, "type": type_, "cvssData": d}


class TestWhoScoredIt:
    def test_nist_wins_even_when_a_vendor_entry_comes_first(self):
        """NIST's own score is preferred wherever it exists. The vendor's
        rating of its own product is a different claim."""
        metrics = {"cvssMetricV31": [_entry(VENDOR, "Primary", 4.0),
                                     _entry(NIST, "Secondary", 9.0)]}
        data, meta = nvd._primary_metric(metrics)
        assert data["baseScore"] == 9.0
        assert meta["source"] == NIST

    def test_primary_wins_when_nist_is_absent(self):
        metrics = {"cvssMetricV31": [_entry("a@b.c", "Secondary", 3.0),
                                     _entry(VENDOR, "Primary", 8.0)]}
        _, meta = nvd._primary_metric(metrics)
        assert meta["source"] == VENDOR
        assert meta["type"] == "Primary"

    def test_falls_back_to_the_first_entry(self):
        metrics = {"cvssMetricV31": [_entry("only@one.c", "Secondary", 6.0)]}
        data, meta = nvd._primary_metric(metrics)
        assert data["baseScore"] == 6.0
        assert meta["source"] == "only@one.c"

    def test_newer_cvss_containers_are_preferred(self):
        metrics = {"cvssMetricV30": [_entry(NIST, "Primary", 3.0, version="3.0")],
                   "cvssMetricV40": [_entry(NIST, "Primary", 9.0, version="4.0")]}
        data, meta = nvd._primary_metric(metrics)
        assert data["baseScore"] == 9.0
        assert meta["version"] == "4.0"

    def test_no_metrics_returns_empty_rather_than_none(self):
        """The caller unpacks two values unconditionally; returning None here
        would make every unscored CVE a TypeError instead of a blank row."""
        data, meta = nvd._primary_metric({})
        assert data == {} and meta == {}

    def test_an_empty_container_is_skipped_not_selected(self):
        metrics = {"cvssMetricV40": [], "cvssMetricV31": [_entry(NIST, "Primary", 5.5)]}
        data, _ = nvd._primary_metric(metrics)
        assert data["baseScore"] == 5.5


class TestNistScoredFlag:
    @pytest.mark.parametrize("source,expected", [
        (NIST, True), ("NVD@NIST.GOV", True),        # case must not matter
        (VENDOR, False), ("adp:cisa-adp", False), (None, False), ("", False),
    ])
    def test_flag_tracks_the_source(self, source, expected):
        assert nvd.Vuln(cve_id="CVE-1", published=None, description="",
                        base_score=1.0, severity="LOW", attack_vector="LOCAL",
                        privileges_required="LOW", user_interaction="NONE",
                        scope="UNCHANGED", metric_source=source).nist_scored is expected


class TestFlatten:
    def _raw(self, **over):
        cve = {
            "id": "CVE-2026-1234",
            "published": "2026-03-14T10:00:00.000",
            "descriptions": [{"lang": "es", "value": "no"}, {"lang": "en", "value": "yes"}],
            "metrics": {"cvssMetricV31": [_entry(NIST, "Primary")]},
            "configurations": [{"nodes": [{"cpeMatch": [
                {"vulnerable": True, "criteria": "cpe:2.3:o:microsoft:windows_10"}]}]}],
        }
        cve.update(over)
        return {"cve": cve}

    def test_provenance_reaches_the_row(self):
        v = nvd._flatten(self._raw())
        assert v.metric_source == NIST
        assert v.metric_version == "3.1"
        assert v.nist_scored is True

    def test_english_description_is_chosen(self):
        assert nvd._flatten(self._raw()).description == "yes"

    def test_published_date_is_parsed(self):
        assert nvd._flatten(self._raw()).published == dt.date(2026, 3, 14)

    def test_an_unparseable_date_is_none_not_a_crash(self):
        v = nvd._flatten(self._raw(published="not-a-date"))
        assert v.published is None

    def test_non_vulnerable_cpes_are_ignored(self):
        """A CPE listed as not vulnerable describes what the flaw needs to be
        present, not what it affects -- counting it would misclassify the row."""
        raw = self._raw(configurations=[{"nodes": [{"cpeMatch": [
            {"vulnerable": False, "criteria": "cpe:2.3:a:microsoft:office"}]}]}])
        assert nvd._flatten(raw).cpe_parts == set()

    def test_unscored_cve_flattens_to_blanks_not_an_error(self):
        """56 rows in the Windows 10 corpus genuinely carry no CVSS. They must
        survive flattening -- an unknown row is not a low-risk one, but it is
        also not a crash."""
        v = nvd._flatten(self._raw(metrics={}))
        assert v.base_score is None and v.attack_vector is None
        assert v.metric_source is None and v.nist_scored is False


class TestReachabilityProperties:
    """These drive mitigation.classify, and the product's central claim rests
    on the local/remote split being right."""

    def _v(self, **kw):
        base = dict(cve_id="C", published=None, description="", base_score=7.0,
                    severity="HIGH", attack_vector="NETWORK",
                    privileges_required="NONE", user_interaction="NONE",
                    scope="UNCHANGED")
        base.update(kw)
        return nvd.Vuln(**base)

    @pytest.mark.parametrize("vector,remote", [
        ("NETWORK", True), ("ADJACENT_NETWORK", True),
        ("LOCAL", False), ("PHYSICAL", False), (None, False),
    ])
    def test_remote_reachability(self, vector, remote):
        v = self._v(attack_vector=vector)
        assert v.remotely_reachable is remote
        if vector in ("LOCAL", "PHYSICAL"):
            assert v.requires_local_access is True

    def test_application_layer_needs_an_app_and_no_os(self):
        """An app CVE is fixable by updating that app, independent of whether
        the OS still gets updates -- so it never justifies new hardware."""
        assert self._v(cpe_parts={"a"}).is_application_layer is True
        assert self._v(cpe_parts={"a", "o"}).is_application_layer is False
        assert self._v(cpe_parts={"o"}).is_application_layer is False
