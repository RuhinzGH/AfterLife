"""What a deep scan could actually read -- and the constant that used to lie.

build_deep_passport hardcoded `completeness_pct: 100`, so every deep passport
asserted, inside its signature, that the collector had seen everything. A scan
that could not reach the TPM, could not read SMART and found no battery still
claimed a complete read.

These tests hold the replacement to being a measurement.
"""
from __future__ import annotations

import pytest

from afterlife.scan_coverage import evaluate

FULL = {
    "manufacturer": "Dell", "model": "Latitude 5490",
    "cpu_name": "Intel Core i5-8250U", "ram_gb": 8.0,
    "sysdrive_total_gb": 476.0, "disk_media_type": "SSD",
    "disk_health": "Healthy", "battery_health_pct": 71.0, "battery_present": True,
    "tpm_present": True, "tpm_spec_version": "2.0", "secure_boot_on": True,
    "os_caption": "Microsoft Windows 10 Pro", "os_version": "10.0.19045",
    "collected_elevated": True,
}

UNELEVATED = {**FULL, "collected_elevated": False, "disk_health": None,
              "smart_predict_failure": None, "tpm_present": "UNKNOWN",
              "tpm_spec_version": None, "secure_boot_on": None}


class TestItIsAMeasurement:
    def test_a_complete_scan_reads_100(self):
        assert evaluate(FULL)["completeness_pct"] == 100

    def test_an_incomplete_scan_does_not(self):
        """The bug, stated as a test: this used to be 100 regardless."""
        assert evaluate(UNELEVATED)["completeness_pct"] < 100

    def test_an_empty_payload_is_not_complete(self):
        assert evaluate({})["completeness_pct"] == 0

    def test_the_percentage_matches_the_itemised_list(self):
        """A total that disagrees with the list beside it destroys trust in both."""
        for device in (FULL, UNELEVATED, {}):
            r = evaluate(device)
            applicable = [p for p in r["probes"] if p["ok"] is not None]
            assert r["total"] == len(applicable)
            assert r["read"] == sum(1 for p in applicable if p["ok"])


class TestUnknownSentinel:
    def test_the_collectors_UNKNOWN_string_is_not_data(self):
        """The collector writes "UNKNOWN" rather than null when a probe times
        out. Counting that as a successful read is how a failed TPM query looks
        like a successful one."""
        assert evaluate({**FULL, "tpm_present": "UNKNOWN", "tpm_spec_version": None})[
            "completeness_pct"] < 100

    @pytest.mark.parametrize("blank", [None, "", "   ", "unknown", "UNKNOWN"])
    def test_blank_shapes_all_count_as_unread(self, blank):
        d = {**FULL, "os_caption": blank, "os_version": blank}
        probes = {p["key"]: p for p in evaluate(d)["probes"]}
        assert probes["os"]["ok"] is False


class TestNotApplicable:
    def test_a_desktop_is_not_penalised_for_having_no_battery(self):
        """Collapsing 'not applicable' into 'failed' would mark every desktop
        as an incomplete scan for a fact about its own design."""
        desktop = {**FULL, "battery_health_pct": None, "battery_present": False}
        r = evaluate(desktop)
        assert r["completeness_pct"] == 100
        probes = {p["key"]: p for p in r["probes"]}
        assert probes["battery"]["ok"] is None

    def test_a_laptop_with_an_unread_battery_is_penalised(self):
        """The distinction only holds if the other side of it still counts."""
        laptop = {**FULL, "battery_health_pct": None, "battery_present": True}
        assert evaluate(laptop)["completeness_pct"] < 100

    def test_the_summary_counts_only_applicable_checks(self):
        desktop = {**FULL, "battery_health_pct": None, "battery_present": False}
        r = evaluate(desktop)
        assert f"All {r['total']} checks" in r["summary"]


class TestActionableAdvice:
    def test_an_unelevated_scan_says_elevation_would_help(self):
        r = evaluate(UNELEVATED)
        assert r["rerun_elevated_would_help"] is True
        assert "administrator" in r["summary"]

    def test_an_elevated_scan_does_not_blame_elevation(self):
        """Sending someone to re-run as administrator for a probe that failed
        for another reason wastes their time and discredits the advice."""
        elevated_but_missing = {**FULL, "disk_health": None,
                                "smart_predict_failure": None}
        r = evaluate(elevated_but_missing)
        assert r["completeness_pct"] < 100
        assert r["rerun_elevated_would_help"] is False
        assert "administrator" not in r["summary"]

    def test_every_missing_probe_explains_itself(self):
        for p in evaluate({}) ["probes"]:
            if p["ok"] is False:
                assert p.get("why"), f"{p['key']} fails with no explanation"


class TestSignedPayload:
    def test_a_deep_passport_carries_measured_completeness(self, device):
        from afterlife.passport import build_deep_passport
        doc = build_deep_passport(device(collected_elevated=False, disk_health=None,
                                         tpm_present="UNKNOWN", tpm_spec_version=None,
                                         secure_boot_on=None))
        payload = doc["payload"]
        assert payload["completeness_pct"] < 100
        assert payload["scan_coverage"]["completeness_pct"] == payload["completeness_pct"]

    def test_a_full_deep_passport_still_reads_100(self, device):
        from afterlife.passport import build_deep_passport
        payload = build_deep_passport(device())["payload"]
        assert payload["completeness_pct"] == 100

    def test_coverage_is_inside_the_signature(self, device):
        """It has to be. An unsigned completeness claim is worth nothing, which
        is the same reasoning that puts the wipe stamp inside the payload."""
        from afterlife.passport import build_deep_passport, verify_payload

        # A PARTIAL scan, so that forging it up to 100 is a real edit. Against a
        # complete scan the same assignment is a no-op and the test passes
        # without proving anything -- which is exactly what it did first time.
        doc = build_deep_passport(device(collected_elevated=False, disk_health=None,
                                         tpm_present="UNKNOWN", tpm_spec_version=None,
                                         secure_boot_on=None))
        assert verify_payload(doc) is True
        assert doc["payload"]["completeness_pct"] < 100

        # Forging the coverage claim upward must break the signature, or the
        # number is decoration rather than evidence.
        doc["payload"]["scan_coverage"]["completeness_pct"] = 100
        doc["payload"]["completeness_pct"] = 100
        assert verify_payload(doc) is False
