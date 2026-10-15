"""Wipe verification: the checks, and the promises the narration may not make.

This is the highest-stakes surface in the product. A false "clean" tells a seller
their old files are gone when they are not, and the stamp it produces is signed
into a passport a stranger is asked to trust. Every test here is about refusing
to say more than the evidence supports.
"""
from __future__ import annotations

import datetime as dt

import pytest

from afterlife.wipe import _contradicts, _overclaims, check


class TestVerdicts:
    def test_freshly_reset_machine_passes(self, clean_state):
        assert check(clean_state())["status"] == "clean"

    def test_machine_still_in_use_fails(self, clean_state):
        r = check(clean_state(user_profiles=2, user_files=4212, wifi_profiles=9,
                              installed_apps=88, os_install_days=900.0))
        assert r["status"] == "not_clean"
        assert len(r["failures"]) >= 4

    def test_deleting_files_by_hand_is_not_enough(self, clean_state):
        """The anti-fake property. "Reset this PC" rewrites the Windows install
        date, so a machine whose files were merely deleted still fails."""
        r = check(clean_state(user_files=0, os_install_days=800.0))
        assert r["status"] == "not_clean"
        assert "Windows recently reset" in r["failures"]

    def test_unreadable_probe_is_never_a_pass(self, clean_state):
        assert check({"checked": False})["status"] == "unknown"
        assert check(None)["status"] == "unknown"

    def test_partial_read_is_unknown_not_clean(self, clean_state):
        """A single unreadable field must not be certified on the strength of the
        others that happened to work."""
        assert check(clean_state(wifi_profiles=None))["status"] == "unknown"

    def test_verified_date_only_on_a_pass(self, clean_state):
        assert check(clean_state(), today=dt.date(2026, 8, 1))["verified_at"] == "2026-08-01"
        assert check(clean_state(os_install_days=900.0))["verified_at"] is None


class TestPassportStamp:
    def test_stamp_present_only_when_clean(self, client, device, clean_state):
        for cs, expect in [(clean_state(), True),
                           (clean_state(os_install_days=900.0), False),
                           ({"checked": False}, False)]:
            r = client.post("/api/deep-scan/stamp-token-0123456789", json=device(clean_state=cs))
            assert r.status_code == 200
            doc = client.get("/api/deep-scan/stamp-token-0123456789").json()
            assert ("wipe_verified" in doc["payload"]) is expect

    def test_stamped_passport_still_verifies(self, client, device, clean_state):
        """The stamp lives inside the signed payload -- if signing ran before it
        was attached, the passport a buyer scans would come back invalid."""
        client.post("/api/deep-scan/sig-token-0123456789", json=device(clean_state=clean_state()))
        doc = client.get("/api/deep-scan/sig-token-0123456789").json()
        assert doc["payload"]["wipe_verified"]
        assert doc["verified"] is True


class TestNarrationGuards:
    """An instruction to a model is not a control. These are the controls."""

    @pytest.mark.parametrize("text", [
        "Your data has been securely erased.",
        "The files are now unrecoverable.",
        "Everything was permanently deleted.",
        "This is military-grade erasure.",
        "Deletion is guaranteed.",
    ])
    def test_blocks_claims_of_real_erasure(self, text):
        assert _overclaims(text)

    @pytest.mark.parametrize("text", [
        "That is a check of what is visible, not a guarantee that deleted data is unrecoverable.",
        "This does not mean the data is unrecoverable.",
        "It checks visible traces rather than guaranteeing data is destroyed.",
        "No visible traces are left, not that deleted data is gone forever.",
    ])
    def test_allows_the_same_words_when_negated(self, text):
        """The disclaimer this module exists to write is built from the exact
        phrases the guard blocks. A substring match rejected correct output and
        then rejected the fallback it fell back to."""
        assert not _overclaims(text)

    def test_blocks_contradicting_a_passing_verdict(self):
        """On a clean machine the model repeatedly read the details of PASSED
        checks as outstanding work: "clean, but three files remain, remove them
        before selling". A seller acting on that wipes an already-wiped machine."""
        assert _contradicts("Clean, but three files remain and should be removed", "clean")
        assert not _contradicts("The machine is not clean. Files remain.", "not_clean")
