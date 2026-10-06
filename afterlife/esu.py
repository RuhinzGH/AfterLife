"""Extended Security Updates: the support state between "patched" and "abandoned".

WHY A THIRD STATE
-----------------
Everywhere else in this codebase, security support is a boolean -- `is_eol`,
true or false, patched or not. For most products that is the whole truth.

For the one product Afterlife's entire argument is built on, it is wrong. A
consumer Windows 10 machine passed end of support on 2025-10-14, so
`device_support.lookup()` scores it `is_eol=True, eol_risk=1.0` -- maximum risk,
"no patches". But Microsoft opened a consumer ESU programme the same day, and an
enrolled machine has been receiving security updates ever since. The score says
the device is abandoned while the device is, in fact, being patched.

That is a real over-penalty, and it lands on precisely the population this
product exists to defend: functional Windows 10 laptops that fail the Windows 11
hardware gate. Afterlife has been arguing "security is a mitigable cost, not a
replace trigger" while its own score treated the most common mitigation -- the
vendor's own extended-updates programme -- as if it did not exist.

THE DATES, AND HOW THEY MOVED
-----------------------------
Ordinary support ended on 2025-10-14. The consumer ESU programme was first
announced as one year, ending 2026-10-13. In 2026 Microsoft extended it by a
year: home users are now covered to 2027-10-12, and can enrol at any point
until then. Organisations buy a separate, paid programme of up to three years
after end of support, which runs to 2028-10-10.

ESU is still a countdown with a published end. A device that is defensibly
"keep and harden" during ESU becomes a different recommendation once its
programme ends, so the end date is reported rather than smoothed away. The
original first-year date is kept as `originally_ended`, so the page can say
plainly that the date moved instead of silently showing a new one.

So this module models three states rather than two, and reports the date each
one ends. It never smooths the cliff into a gradient -- the whole value of the
answer is that the date is fixed, published, and checkable.

Every date below is a Patch Tuesday (second Tuesday of the month), which is the
consistency check to run if any of them is ever edited.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from enum import Enum


class SupportState(str, Enum):
    SUPPORTED = "supported"      # ordinary security + quality updates
    ESU = "esu"                  # main support over; security-only, time-boxed, opt-in
    UNSUPPORTED = "unsupported"  # nothing, from anyone


@dataclass(frozen=True)
class ExtendedSupport:
    """One vendor extended-updates programme."""
    product: str
    #: The day ordinary support ended -- also the day ESU begins.
    support_end: dt.date
    #: The day the programme ends for this audience.
    esu_end: dt.date
    #: Last day to join. Equal to esu_end where enrolment stays open throughout.
    enrol_by: dt.date
    #: Who can actually buy it, in the user's terms.
    audience: str
    #: What it does and does not cover.
    scope: str
    source: str
    #: The end date first announced, where Microsoft has since extended it.
    originally_ended: dt.date | None = None

    def state(self, as_of: dt.date) -> SupportState:
        if as_of <= self.support_end:
            return SupportState.SUPPORTED
        if as_of <= self.esu_end:
            return SupportState.ESU
        return SupportState.UNSUPPORTED

    def days_left(self, as_of: dt.date) -> int:
        """Days until the programme ends. Negative once it has."""
        return (self.esu_end - as_of).days


#: Keyed by the normalised product family `device_support` already matches on.
#:
#: Consumer and commercial are separate entries because they are separate
#: programmes with different end dates, and collapsing them would hand a home
#: user three more years they cannot buy. Afterlife assesses consumer hardware
#: by default, so `windows10` resolves to the consumer track; the commercial
#: track is reachable but never assumed.
PROGRAMMES: dict[str, ExtendedSupport] = {
    "windows10": ExtendedSupport(
        product="Windows 10",
        support_end=dt.date(2025, 10, 14),
        esu_end=dt.date(2027, 10, 12),
        enrol_by=dt.date(2027, 10, 12),
        audience="Home users (Home and Pro): free via Windows Backup or Microsoft "
                 "Rewards, or a one-off fee. First announced as one year, to "
                 "13 October 2026; extended in 2026 to 12 October 2027",
        scope="Critical and Important security updates only. No feature updates, "
              "no quality fixes, no new functionality, and no general technical support.",
        source="https://www.microsoft.com/en-us/windows/extended-security-updates",
        originally_ended=dt.date(2026, 10, 13),
    ),
    "windows10-commercial": ExtendedSupport(
        product="Windows 10 (commercial/education)",
        support_end=dt.date(2025, 10, 14),
        # Three annual renewals past end of support; each year costs more than
        # the last, which is deliberate on Microsoft's part and worth saying.
        esu_end=dt.date(2028, 10, 10),
        enrol_by=dt.date(2028, 10, 10),
        audience="Organisations, sold per device per year for up to three years",
        scope="Critical and Important security updates only, at a price that "
              "roughly doubles each renewal year.",
        source="https://learn.microsoft.com/en-us/windows/whats-new/extended-security-updates",
    ),
}


#: Matches the product family anywhere in the string, so both the normalised
#: index key ("windows10") and the human product name ("Microsoft Windows 10")
#: resolve. The trailing (?!\d) is what stops "windows 10" matching a
#: hypothetical "Windows 100" -- and, more usefully today, keeps "Windows 11"
#: from resolving to Windows 10's programme, which would hand every Windows 11
#: machine a support cliff it does not have.
_WINDOWS_10 = re.compile(r"windows\s*10(?!\d)", re.I)


def for_product(key: str | None, commercial: bool = False) -> ExtendedSupport | None:
    """Find the programme covering a product name or normalised key, if any.

    Returns None for everything with no extended-updates programme, which is
    almost everything -- the absence is the normal case and must not be
    mistaken for "supported".
    """
    if not key:
        return None
    if _WINDOWS_10.search(key):
        return PROGRAMMES["windows10-commercial" if commercial else "windows10"]
    return None


def _day(d: dt.date) -> str:
    """'12 October 2027' -- no leading zero, unlike %d."""
    return f"{d.day} {d:%B %Y}"


def _later_programme(prog: ExtendedSupport) -> ExtendedSupport | None:
    """The commercial programme that outlasts a consumer one, if there is one."""
    if prog is PROGRAMMES.get("windows10"):
        return PROGRAMMES.get("windows10-commercial")
    return None


def describe(prog: ExtendedSupport, as_of: dt.date | None = None) -> dict:
    """A JSON-safe account of where a device sits, and what changes when.

    The caller renders this; it decides nothing. Note `ends_in_days` is signed
    on purpose -- a negative value is a programme that has already closed, and
    reading it as "0 days left" would be the friendlier lie.
    """
    as_of = as_of or dt.date.today()
    state = prog.state(as_of)
    left = prog.days_left(as_of)

    later = _later_programme(prog)

    if state is SupportState.SUPPORTED:
        headline = f"{prog.product} still receives ordinary security updates."
    elif state is SupportState.ESU:
        headline = (
            f"{prog.product} reached end of support on {_day(prog.support_end)}. "
            f"Extended Security Updates{' for home users' if later else ''} "
            f"continue to {_day(prog.esu_end)}"
        )
        if prog.originally_ended:
            headline += f" (first announced to end on {_day(prog.originally_ended)})"
        headline += "."
        if later:
            headline += (f" Organisations can buy up to three years of updates, "
                         f"to {later.esu_end:%B %Y}.")
    else:
        headline = (
            f"Extended Security Updates for {prog.product}{' home users' if later else ''} ended on "
            f"{_day(prog.esu_end)}; it no longer receives security updates."
        )
        if later and as_of <= later.esu_end:
            headline += (f" Organisations on the paid programme are covered to "
                         f"{later.esu_end:%B %Y}.")

    return {
        "state": state.value,
        "product": prog.product,
        "support_end": prog.support_end.isoformat(),
        "esu_end": prog.esu_end.isoformat(),
        "originally_ended": prog.originally_ended.isoformat() if prog.originally_ended else None,
        "enrol_by": prog.enrol_by.isoformat(),
        "ends_in_days": left,
        "enrolment_open": as_of <= prog.enrol_by,
        "audience": prog.audience,
        "scope": prog.scope,
        "headline": headline,
        "source": prog.source,
    }


#: How much worse ESU is than ordinary support with the same time left.
#:
#: An authored constant, flagged as such the way the other blend-score
#: adjustments are. It is not zero, because ESU is degraded support: security
#: fixes only, no quality or reliability fixes, and -- unlike an ordinary
#: support window -- nothing follows it. It is small, because the device is
#: genuinely still being patched.
DEGRADED_SUPPORT_PENALTY = 0.10

#: ESU must stay strictly below a machine that receives nothing at all.
MAX_ESU_RISK = 0.95


def esu_risk(months_to_esu_end: float, base_risk_fn) -> float:
    """Risk for a machine inside an extended-support window.

    The first attempt at this scaled the end-of-life risk by a flat factor,
    which produced an incoherent answer: a device six weeks from the ESU cliff
    scored *safer* than the same device fifteen months earlier with four months
    of ordinary support left. That is backwards, and it happened because a flat
    multiplier throws away the one thing that actually varies -- how much time
    is left.

    So risk is computed the same way it is everywhere else, against the date
    that actually binds (the end of ESU, not the end of ordinary support), and
    then nudged up because ESU is worse than ordinary support of equal length.

    `base_risk_fn` is `device_support.risk_from_months`, passed in rather than
    imported to keep the dependency pointing one way.
    """
    base = base_risk_fn(months_to_esu_end, False)
    return round(min(MAX_ESU_RISK, base + DEGRADED_SUPPORT_PENALTY), 3)
