"""Geo resolution, and the jurisdiction gate on repair rights.

The gate is the point of this module. repair_rights only ever describes EU/EEA
law, but /api/assess called it without a country, so an owner in India was shown
European repair entitlements that do not exist for them. That is the exact
failure repair_rights' own docstring says would be "confident, plausible,
actively harmful". These tests exist so it cannot come back.
"""
from __future__ import annotations

import pytest

from afterlife.geo import resolve


class TestResolution:
    @pytest.mark.parametrize("tz,cc,currency", [
        ("Asia/Kolkata", "IN", "INR"),
        ("Europe/Berlin", "DE", "EUR"),
        ("Europe/London", "GB", "GBP"),
        ("America/New_York", "US", "USD"),
    ])
    def test_timezone_resolves_country_and_currency(self, tz, cc, currency):
        g = resolve(tz)
        assert (g.country, g.currency, g.resolved_from) == (cc, currency, "timezone")

    def test_explicit_country_beats_timezone(self):
        """A user on holiday, behind a VPN, or simply corrected by hand."""
        g = resolve("Europe/Berlin", country="IN")
        assert g.country == "IN" and g.resolved_from == "override"

    def test_unknown_input_claims_nothing(self):
        for g in (resolve(None), resolve("Not/AZone"), resolve(None, country="ZZ")):
            assert g.country == "" and g.resolved_from == "default"
            assert g.evidence_level == "unknown"

    def test_uk_is_outside_the_eea(self):
        """Post-Brexit, and easy to get wrong because the UK supplies more of the
        repair corpus than any other country."""
        assert resolve("Europe/London").in_eea is False
        assert resolve("Europe/Dublin").in_eea is True


class TestEvidenceCoverage:
    def test_country_absent_from_the_corpus_is_reported_as_such(self):
        """India contributes 0 of 305,649 records. Advising an Indian owner from
        that corpus without saying so is the quiet version of overclaiming."""
        g = resolve("Asia/Kolkata")
        assert g.ora_records == 0 and g.evidence_level == "none"
        assert "No repair records from India" in g.evidence_note

    def test_well_covered_country_is_reported_as_represented(self):
        g = resolve("Europe/London")
        assert g.evidence_level == "represented" and g.ora_records > 50_000

    def test_thinly_covered_country_is_flagged(self):
        g = resolve("America/New_York")
        assert g.evidence_level == "thin" and 0 < g.ora_share < 1.0
