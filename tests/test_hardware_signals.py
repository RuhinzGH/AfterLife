"""Windows event-log findings, and the distinction that makes them honest.

The collector reports "UNKNOWN" rather than 0 when an event query fails, and the
whole value of this module rests on carrying that through. A machine whose event
log could not be read is not a machine with no faults -- but both look like
"nothing to report" unless something keeps them apart.

The other claim worth holding is the window. Windows caps the System log and
rolls old records out, so a 90-day query routinely covers far less. Reporting
"no errors in the last 90 days" off a log that reaches back thirteen would
overstate the evidence by a factor of seven, in the direction that flatters the
device.
"""
from __future__ import annotations

import pytest

from afterlife.hardware_signals import (
    RELIABILITY_GOOD, RELIABILITY_POOR, _evt, _window_phrase, summarize,
)


class TestUnknownIsNotZero:
    """The single most important behaviour in this module."""

    def test_unknown_count_reads_as_unreadable(self):
        assert _evt({"count": "UNKNOWN"}) == (None, None)

    def test_a_real_zero_reads_as_zero(self):
        assert _evt({"count": 0})[0] == 0

    def test_a_missing_block_is_unreadable_not_clean(self):
        assert _evt(None) == (None, None)

    def test_nonsense_is_unreadable_rather_than_a_crash(self):
        assert _evt({"count": "seventeen"}) == (None, None)

    def test_an_unreadable_log_is_named_in_the_response(self):
        """So the UI can say which probe was denied, rather than implying the
        machine is clean on evidence nobody has."""
        r = summarize({"hardware_errors": {"whea_90d": {"count": "UNKNOWN"}}})
        assert "hardware" in r["unreadable"]
        assert r["counts"]["whea"] is None

    def test_the_summary_admits_when_logs_were_unreadable(self):
        r = summarize({"hardware_errors": {"whea_90d": {"count": "UNKNOWN"}}})
        assert "could not be read" in r["summary"].lower()

    def test_a_fully_readable_clean_machine_says_so_plainly(self):
        r = summarize({"hardware_errors": {
            "whea_90d": {"count": 0}, "disk_90d": {"count": 0},
            "ntfs_90d": {"count": 0}, "gpu_tdr_90d": {"count": 0},
            "unexpected_shutdowns_90d": {"count": 0}},
            "crash_dumps": {"count": 0}})
        assert r["unreadable"] == []
        assert "could not be read" not in r["summary"].lower()


class TestWindowHonesty:
    def test_a_full_window_is_described_as_ninety_days(self):
        assert "90 days" in _window_phrase(90)

    def test_a_truncated_log_says_how_far_it_actually_reaches(self):
        """13 days was the real figure on the dev machine. Calling that 90
        would overstate the evidence sevenfold, in the flattering direction."""
        phrase = _window_phrase(13)
        assert "13 days" in phrase
        assert "retains" in phrase

    def test_an_unknown_window_makes_no_claim_at_all(self):
        for bad in (None, 0, -5, "UNKNOWN"):
            assert _window_phrase(bad) == "in the available event history"


class TestReliabilityBands:
    @pytest.mark.parametrize("index,band", [
        (9.5, "good"), (RELIABILITY_GOOD, "good"),
        (6.2, "fair"), (RELIABILITY_POOR, "fair"),
        (3.0, "poor"), (1.0, "poor"),
    ])
    def test_bands_follow_the_index(self, index, band):
        assert summarize({"reliability_index": index})["reliability"]["band"] == band

    def test_no_index_yields_no_reliability_block(self):
        assert summarize({})["reliability"] is None

    def test_the_scale_is_explained_not_assumed(self):
        """1-10 means nothing to a reader without being told whose scale it is."""
        note = summarize({"reliability_index": 7.0})["reliability"]["note"].lower()
        assert "out of 10" in note and "windows" in note


class TestBattery:
    def test_cycle_count_is_reported_with_context(self):
        """A bare "420 cycles" is unreadable; the rated range is what makes it
        mean something."""
        b = summarize({"battery_cycle_count": 420})["battery"]
        assert b["cycle_count"] == 420
        assert "300" in b["note"]

    def test_no_cycle_count_yields_nothing_rather_than_zero(self):
        """Desktops have no battery, and an unread count is not a new battery."""
        assert summarize({})["battery"] is None


class TestFindings:
    def test_real_errors_become_findings(self):
        r = summarize({"hardware_errors": {"whea_90d": {"count": 5, "window_days": 30}}})
        assert r["findings"]
        assert r["clean"] is False

    def test_clean_only_where_everything_was_readable(self):
        """`clean` is a claim about the machine. It must not be inferred from
        silence that came from a denied probe."""
        unreadable = summarize({"hardware_errors": {"whea_90d": {"count": "UNKNOWN"}}})
        assert unreadable["clean"] is None, (
            "an unreadable log must not read as a clean machine")

    def test_counts_are_returned_so_a_finding_is_checkable(self):
        r = summarize({"hardware_errors": {"whea_90d": {"count": 3, "window_days": 30}}})
        assert r["counts"]["whea"] == 3

    def test_an_empty_device_does_not_crash(self):
        """The browser scan supplies none of these fields at all."""
        r = summarize({})
        assert isinstance(r["findings"], list)
        assert isinstance(r["counts"], dict)
