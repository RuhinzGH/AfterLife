"""Extended Security Updates: the state between supported and abandoned.

The bug this guards against is a specific, dated one. Windows 10 passed end of
support on 2025-10-14, so every Windows 10 machine scored `is_eol=True,
eol_risk=1.0` -- "abandoned, maximum risk" -- while Microsoft's consumer ESU
programme was in fact still shipping it security updates. The product told the
population it exists to defend that they were unpatched when they were not.

The window closes on 2026-10-13, so most of these tests are written against
fixed dates on both sides of that cliff rather than against `today`. A test that
passes only until October would be worse than no test.
"""
from __future__ import annotations

import datetime as dt

import pytest

from afterlife import device_support as ds
from afterlife import esu

BEFORE_EOL = dt.date(2025, 6, 1)
IN_ESU = dt.date(2026, 9, 1)
LAST_ESU_DAY = dt.date(2026, 10, 13)
AFTER_ESU = dt.date(2026, 10, 14)


def _win10(as_of):
    h = ds.lookup(os_name="Windows 10", as_of=as_of)
    assert h is not None, "Windows 10 must resolve in the support table"
    return h


class TestStateMachine:
    def test_all_three_states_are_reachable(self):
        assert _win10(BEFORE_EOL).support_state == "supported"
        assert _win10(IN_ESU).support_state == "esu"
        assert _win10(AFTER_ESU).support_state == "unsupported"

    def test_the_cliff_is_a_cliff_not_a_ramp(self):
        """The last day of ESU and the next day are different states.

        The value of this answer is that the date is published and fixed.
        Smoothing the transition into a gradient would be friendlier and wrong.
        """
        assert _win10(LAST_ESU_DAY).support_state == "esu"
        assert _win10(AFTER_ESU).support_state == "unsupported"

    def test_is_eol_still_means_what_it_always_meant(self):
        """Existing callers must not silently change behaviour.

        `is_eol` is "past ordinary end of support" both before and after this
        module existed. Only the new `support_state` field splits it further.
        """
        assert _win10(BEFORE_EOL).is_eol is False
        assert _win10(IN_ESU).is_eol is True
        assert _win10(AFTER_ESU).is_eol is True


class TestRisk:
    def test_esu_is_penalised_less_than_abandonment(self):
        """A machine receiving patches must not score as one receiving none."""
        assert _win10(IN_ESU).eol_risk < _win10(AFTER_ESU).eol_risk

    def test_esu_is_worse_than_ordinary_support_of_the_same_length(self):
        """ESU is security-only and terminal. It is not a clean bill of health.

        Compared like for like -- same months remaining -- rather than against
        an arbitrary earlier date. The first version of this test compared
        different amounts of time left and caught a real bug: a flat risk
        multiplier made a device six weeks from the cliff score *safer* than
        the same device with four months of ordinary support left.
        """
        months = 6.0
        ordinary = ds.risk_from_months(months, False)
        extended = esu.esu_risk(months, ds.risk_from_months)
        assert extended > ordinary

    def test_risk_rises_as_the_cliff_approaches(self):
        """The bug the flat multiplier hid: risk has to track time remaining."""
        early = ds.lookup(os_name="Windows 10", as_of=dt.date(2025, 11, 1))
        late = _win10(IN_ESU)
        assert early.support_state == late.support_state == "esu"
        assert late.eol_risk > early.eol_risk

    def test_abandonment_is_full_risk(self):
        assert _win10(AFTER_ESU).eol_risk == 1.0

    def test_esu_never_reaches_abandoned_risk(self):
        """However close the cliff, a patched machine is not an unpatched one."""
        assert _win10(LAST_ESU_DAY).eol_risk < _win10(AFTER_ESU).eol_risk

    def test_the_binding_date_is_the_one_left(self):
        """Inside ESU the countdown runs to the programme's end, not to eol_from."""
        h = _win10(IN_ESU)
        assert h.months_remaining < 0, "ordinary support is already behind us"
        assert h.months_to_state_end > 0, "the ESU window is still ahead"


class TestNoFalsePositives:
    def test_windows_11_gets_no_programme(self):
        """The regex must not hand Windows 11 a cliff it does not have."""
        h = ds.lookup(os_name="Windows 11", as_of=IN_ESU)
        assert h is not None
        assert h.esu is None
        assert h.support_state == "supported"

    @pytest.mark.parametrize("name", ["Windows 11", "Windows 100", "windows1000"])
    def test_lookalikes_do_not_match(self, name):
        assert esu.for_product(name) is None

    @pytest.mark.parametrize("name", [
        "Windows 10", "windows10", "Microsoft Windows 10 Pro", "Microsoft Windows 10 22H2",
    ])
    def test_real_names_all_match(self, name):
        assert esu.for_product(name) is not None

    def test_most_products_have_no_programme(self):
        """Absence is the normal case and must never read as 'supported'."""
        for name in ("Android 13", "macOS Ventura", "Ubuntu 20.04", ""):
            assert esu.for_product(name) is None


class TestUserFacingText:
    def test_esu_machine_is_not_told_it_is_unpatched(self):
        """The actual bug: a confident, checkable, wrong sentence."""
        h = _win10(IN_ESU)
        note = ds.reassess_note(h).lower()
        assert "stopped receiving security updates" not in note
        assert "extended security updates" in note
        assert h.esu["esu_end"] in ds.reassess_note(h)

    def test_expired_machine_is_told_plainly(self):
        note = ds.reassess_note(_win10(AFTER_ESU)).lower()
        assert "no security updates" in note
        assert "nothing further" in note

    def test_risk_detail_names_the_binding_date(self):
        """A user can check a date. Nobody can check '60% risk'."""
        assert "2026-10-13" in ds.risk_detail(_win10(IN_ESU))
        assert "2026-10-13" in ds.risk_detail(_win10(AFTER_ESU))


class TestProgrammeFacts:
    def test_every_date_is_a_patch_tuesday(self):
        """The consistency check named in the module docstring.

        Microsoft retires products on the second Tuesday of a month. A date that
        is not one has almost certainly been typed in wrong.
        """
        for prog in esu.PROGRAMMES.values():
            for label, date in (("support_end", prog.support_end),
                                ("esu_end", prog.esu_end)):
                assert date.weekday() == 1, f"{prog.product} {label} is not a Tuesday"
                assert 8 <= date.day <= 14, f"{prog.product} {label} is not the 2nd Tuesday"

    def test_consumer_track_is_the_default(self):
        """A home user must not be handed three years they cannot buy."""
        consumer = esu.for_product("Windows 10")
        commercial = esu.for_product("Windows 10", commercial=True)
        assert consumer.esu_end < commercial.esu_end
        assert consumer is esu.PROGRAMMES["windows10"]

    def test_esu_begins_exactly_where_support_ends(self):
        for prog in esu.PROGRAMMES.values():
            assert prog.support_end < prog.esu_end
            assert prog.state(prog.support_end) == esu.SupportState.SUPPORTED
            assert prog.state(prog.support_end + dt.timedelta(days=1)) == esu.SupportState.ESU

    def test_describe_reports_a_signed_countdown(self):
        """Negative days left means closed. Clamping it to zero would be a lie."""
        prog = esu.for_product("Windows 10")
        assert esu.describe(prog, IN_ESU)["ends_in_days"] > 0
        assert esu.describe(prog, AFTER_ESU)["ends_in_days"] < 0
        assert esu.describe(prog, IN_ESU)["enrolment_open"] is True
        assert esu.describe(prog, AFTER_ESU)["enrolment_open"] is False
