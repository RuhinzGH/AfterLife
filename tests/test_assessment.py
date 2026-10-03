"""Assessment: the uplift, the repair evidence, and the OS-gating invariant."""
from __future__ import annotations

import re

import pytest



class TestRepairEvidence:
    def test_evidence_is_a_rate_never_a_prediction(self, client):
        from afterlife.repair_evidence import evidence_block
        b = evidence_block(battery_health=61.0, os_supported=False)
        assert b is not None
        for line in b["lines"]:
            assert "left working" in line, "must read as an observed rate"
            assert "will" not in line.lower().split(), "must not predict this device"

    def test_nothing_matched_means_nothing_shown(self):
        from afterlife.repair_evidence import evidence_block
        assert evidence_block(battery_health=98.0, os_supported=True) is None


class TestAssessEndpoint:
    def test_minimal_payload_is_accepted(self, client):
        """The instant scan sends almost nothing; new optional fields must never
        become required."""
        assert client.post("/api/assess", json={"hardware_trust": 70}).status_code == 200

def _eol_adjustment(blend):
    """The end-of-life term, found by the provenance key only it carries."""
    return next((a for a in blend["adjustments"] if "source" in a), None)


class TestEolProvenance:
    """Two different quantities reach blend_score through one `eol_risk` parameter:
    the published-support-date risk (deep scan) and the repair classifier's
    End-of-life probability (instant scan). Both are 0-1. The score adjustment used
    to be captioned "ML end-of-life risk" for both, so the deep scan -- the tier
    the product sells as "verified" -- reported a model verdict it never computed."""

    def test_support_date_risk_is_not_credited_to_the_model(self, client):
        r = client.post("/api/assess", json={
            "hardware_trust": 80, "os": "Windows 10", "make_model": "Dell Latitude 5490",
        }).json()
        adj = _eol_adjustment(r["blend"])
        assert adj is not None, "an end-of-support OS must still carry its penalty"
        assert adj["source"] == "support"
        assert "ML" not in adj["factor"], "no model ran on this path"

    def test_the_evidence_is_a_date_the_owner_can_check(self, client):
        """"63% risk" is uncheckable; a published end date is not."""
        r = client.post("/api/assess", json={"hardware_trust": 80, "os": "Windows 10"}).json()
        assert re.search(r"\d{4}-\d{2}-\d{2}", _eol_adjustment(r["blend"])["detail"])

    def test_classifier_risk_is_still_named_as_the_model(self, client):
        """The instant scan genuinely does run the classifier, and must keep saying so."""
        r = client.post("/api/assess", json={"hardware_trust": 75, "eol_risk": 0.42}).json()
        adj = _eol_adjustment(r["blend"])
        assert adj["source"] == "ml" and adj["factor"] == "ML end-of-life risk"

    def test_relabelling_never_moved_the_number(self):
        """Provenance is a caption, not a new scoring term."""
        from afterlife.assessment import blend_score
        plain = blend_score(80, 0.4, None, None, False)
        tagged = blend_score(80, 0.4, None, None, False,
                             eol_source="support", eol_detail="security updates ended 2025-10-14")
        assert plain["combined_score"] == tagged["combined_score"]

    def test_unknown_provenance_claims_nothing(self):
        """A caller that does not say where the number came from must not have a
        source invented for it -- that is the bug, one layer down."""
        from afterlife.assessment import blend_score
        adj = _eol_adjustment(blend_score(80, 0.4, None, None, False))
        assert adj["source"] is None and "ML" not in adj["factor"]

    def test_the_weakness_line_inherits_the_honest_label(self, client):
        """key_points derives its text from these adjustments, so a wrong caption
        here reappears verbatim in the user-facing strengths/weaknesses list."""
        r = client.post("/api/assess", json={"hardware_trust": 80, "os": "Windows 10"}).json()
        assert not any("ML end-of-life" in w for w in r["key_points"]["weaknesses"])


class TestKeyPointsDoNotClaimWhatWasNeverMeasured:
    """A strength is a claim about the device. It needs evidence, not silence.

    key_points used to read "no battery-wear penalty" as "battery in good
    health". But blend_score only applies that penalty when a battery reading
    EXISTS and is poor -- an instant scan cannot read the battery at all, so the
    penalty never appeared and every browser scan announced a healthy battery,
    directly beside a passport field saying battery wear was "not exposed".
    Age had the same flaw. Both are the recurring bug in this codebase: absence
    of evidence reported as evidence of absence.
    """

    def _points(self, battery=None, age=None):
        from afterlife.assessment import blend_score, estimate_years, key_points
        blend = blend_score(75, None, battery, age, False)
        years = estimate_years(blend["combined_score"], age, battery)
        return key_points(blend, years, None, battery_health=battery, age_years=age)

    def test_an_unread_battery_is_not_called_healthy(self):
        assert "Battery in good health" not in self._points(battery=None)["strengths"]

    def test_a_measured_healthy_battery_still_is(self):
        assert "Battery in good health" in self._points(battery=92.0, age=2)["strengths"]

    def test_a_measured_worn_battery_is_not(self):
        pts = self._points(battery=55.0, age=5)
        assert "Battery in good health" not in pts["strengths"]
        assert any("battery wear" in w for w in pts["weaknesses"])

    def test_an_unknown_age_is_not_called_prime_years(self):
        assert "Still within its expected prime years" not in self._points(age=None)["strengths"]

    def test_a_known_young_age_still_is(self):
        assert "Still within its expected prime years" in self._points(age=3)["strengths"]

    def test_a_known_old_age_is_not(self):
        assert "Still within its expected prime years" not in self._points(age=9)["strengths"]
