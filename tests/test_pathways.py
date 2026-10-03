"""Lifecycle Pathways -- five futures scored side by side.

The feature exists to stop the product handing down a binary, so the property
that matters is that all five stay live and exactly one is marked best. A
ranking that silently collapsed, or a "recycle" that won on a healthy machine,
would invert the argument the whole product makes.

Every number in the module is a disclosed judgement call rather than a fitted
one, so these tests assert the SHAPE the scoring claims -- direction, ranking,
and the specific reshaping Windows 11 eligibility is supposed to do -- not any
particular score.
"""
from __future__ import annotations

import pytest

from afterlife.pathways import PATHWAYS, compute_pathways

GRADES = ["A - excellent", "B - good", "C - serviceable", "D - limited"]


def _by_key(rows):
    return {r["key"]: r for r in rows}


class TestAllFiveStayLive:
    @pytest.mark.parametrize("grade", GRADES)
    def test_every_pathway_is_always_returned(self, grade):
        """The point of the feature: five options shown, not one verdict. A
        pathway dropping out because it scored badly would quietly turn this
        back into the binary it replaced."""
        rows = compute_pathways(grade)
        assert len(rows) == len(PATHWAYS)
        assert {r["key"] for r in rows} == {p["key"] for p in PATHWAYS}

    @pytest.mark.parametrize("grade", GRADES)
    def test_exactly_one_best_fit(self, grade):
        """Zero would leave the user with no answer; two would be a coin flip
        dressed as a recommendation."""
        rows = compute_pathways(grade)
        assert sum(r["status"] == "best_fit" for r in rows) == 1

    @pytest.mark.parametrize("grade", GRADES)
    def test_the_best_fit_is_the_highest_scoring(self, grade):
        rows = compute_pathways(grade)
        best = next(r for r in rows if r["status"] == "best_fit")
        assert best["fit_score"] == max(r["fit_score"] for r in rows)

    @pytest.mark.parametrize("grade", GRADES)
    def test_scores_stay_in_range(self, grade):
        assert all(0 <= r["fit_score"] <= 100 for r in compute_pathways(grade))

    def test_identity_never_varies_with_the_device(self):
        """Icon and colour are fixed per pathway; only fit and actions move."""
        a = _by_key(compute_pathways("A - excellent"))
        d = _by_key(compute_pathways("D - limited"))
        for k in a:
            assert (a[k]["icon"], a[k]["color"]) == (d[k]["icon"], d[k]["color"])


class TestTheArgumentIsNotInverted:
    """A healthy machine must never be told to recycle, and a dead one must not
    be recommended as a primary device. These are the two failures that would
    contradict the product's entire thesis."""

    def test_recycle_loses_on_a_healthy_device(self):
        rows = _by_key(compute_pathways("A - excellent"))
        assert rows["recycle"]["status"] != "best_fit"
        assert rows["recycle"]["fit_score"] < rows["primary"]["fit_score"]

    def test_primary_loses_on_a_spent_device(self):
        rows = _by_key(compute_pathways("D - limited"))
        assert rows["primary"]["status"] != "best_fit"

    def test_recycle_rises_and_primary_falls_as_the_grade_drops(self):
        primary = [_by_key(compute_pathways(g))["primary"]["fit_score"] for g in GRADES]
        recycle = [_by_key(compute_pathways(g))["recycle"]["fit_score"] for g in GRADES]
        assert primary == sorted(primary, reverse=True)
        assert recycle == sorted(recycle)

    def test_an_excellent_device_is_told_recycling_is_premature(self):
        note = _by_key(compute_pathways("A - excellent"))["recycle"]
        assert "not the right call" in str(note).lower() or "premature" in str(note).lower()


class TestWindows11Reshaping:
    """The narrative hook. A machine failing the gate on a FIXABLE blocker
    should be pushed toward hardening; one permanently blocked should not be
    pushed as hard, because the fix does not exist."""

    def test_ineligible_lowers_keeping_it_as_primary(self):
        base = _by_key(compute_pathways("B - good"))["primary"]["fit_score"]
        gated = _by_key(compute_pathways("B - good", win11_status="NOT ELIGIBLE"))["primary"]["fit_score"]
        assert gated < base

    def test_a_firmware_fixable_block_makes_hardening_the_answer(self):
        rows = _by_key(compute_pathways(
            "B - good", win11_status="NOT ELIGIBLE",
            win11_blockers=["secure_boot"], win11_firmware_fixable=True))
        assert rows["hardening"]["status"] == "best_fit"

    def test_a_permanent_block_lifts_hardening_less_than_a_fixable_one(self):
        fixable = _by_key(compute_pathways(
            "B - good", win11_status="NOT ELIGIBLE", win11_firmware_fixable=True))
        permanent = _by_key(compute_pathways(
            "B - good", win11_status="NOT ELIGIBLE", win11_permanently_blocked=True))
        assert permanent["hardening"]["fit_score"] < fixable["hardening"]["fit_score"]

    def test_eligibility_does_not_touch_the_other_three(self):
        """Whether Windows 11 is reachable says nothing about resale or
        recycling, so it must not quietly move them."""
        base = _by_key(compute_pathways("B - good"))
        gated = _by_key(compute_pathways("B - good", win11_status="NOT ELIGIBLE",
                                         win11_firmware_fixable=True))
        for k in ("repurpose", "sell", "recycle"):
            assert base[k]["fit_score"] == gated[k]["fit_score"]


class TestActions:
    def test_a_fixable_blocker_produces_its_own_instruction(self):
        rows = _by_key(compute_pathways(
            "C - serviceable", win11_status="NOT ELIGIBLE",
            win11_blockers=["tpm", "secure_boot"], win11_firmware_fixable=True))
        actions = " ".join(rows["hardening"]["actions"]).lower()
        assert "tpm" in actions and "secure boot" in actions

    def test_permanent_blockers_produce_no_instruction(self):
        """There is no action to hand someone whose CPU is too old, and
        offering one would waste their afternoon."""
        rows = _by_key(compute_pathways(
            "C - serviceable", win11_status="NOT ELIGIBLE",
            win11_blockers=["cpu_generation"], win11_permanently_blocked=True))
        actions = " ".join(rows["hardening"]["actions"]).lower()
        assert "cpu" not in actions

    def test_an_unknown_tpm_is_not_treated_as_a_finding(self):
        rows = _by_key(compute_pathways(
            "C - serviceable", win11_status="NOT ELIGIBLE",
            win11_blockers=["unknown_tpm"]))
        assert not any("unknown" in a.lower() for a in rows["hardening"]["actions"])

    def test_a_spinning_disk_earns_the_ssd_advice(self):
        rows = _by_key(compute_pathways("C - serviceable", storage="500GB HDD"))
        assert any("ssd" in a.lower() for a in rows["hardening"]["actions"])

    def test_an_ssd_does_not(self):
        rows = _by_key(compute_pathways("C - serviceable", storage="512GB SSD"))
        assert not any("replace the hdd" in a.lower() for a in rows["hardening"]["actions"])

    def test_hardening_always_offers_something(self):
        """Generic hygiene applies whatever the scan found, so this pathway is
        never an empty box."""
        for grade in GRADES:
            assert _by_key(compute_pathways(grade))["hardening"]["actions"]


class TestUnknownGrade:
    def test_an_unrecognised_grade_falls_back_rather_than_failing(self):
        rows = compute_pathways("Z - nonsense")
        assert len(rows) == len(PATHWAYS)
        assert sum(r["status"] == "best_fit" for r in rows) == 1
