"""Resolve a device or OS to the date its security updates stop.

Companion to eol.py, which resolves Windows feature updates against the live
endoflife.date API. This module answers the same question for the *device* --
Samsung, Pixel, iPhone, Surface, Xperia and the rest -- from a snapshot built
by scripts/build_device_support.py, so an assessment never blocks on a network
call it does not need.

The point of it. `eol_risk` used to arrive on /api/assess as a float chosen by
the caller. Every other input to blend_score is measured, so the security
pillar was the one guess in an otherwise measurement-driven score. Here it
becomes a lookup against a published date, with the date returned alongside the
number so the user can check it.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
from dataclasses import dataclass, asdict

from . import esu as esu_mod

APP_DATA = pathlib.Path(__file__).resolve().parents[1] / "app_data"
_TABLE: dict | None = None

# Beyond this horizon the security clock stops driving the decision -- something
# else (battery, storage, speed) will decide first. Chosen as a round three years
# rather than fitted; it is a presentation threshold, not a learned parameter.
FULL_RISK_HORIZON_MONTHS = 36
_MIN_RISK, _MAX_RISK = 0.05, 0.95


@dataclass(frozen=True)
class SupportHorizon:
    product: str
    release: str
    eol_from: str                 # security updates stop
    eoas_from: str | None         # feature/OS updates stop (often much earlier)
    months_remaining: float
    is_eol: bool
    eol_risk: float
    matched_on: str               # "device" | "os"
    matched_key: str
    source: str = "endoflife.date"
    # Three-state support, where a boolean used to be. `is_eol` is kept and
    # still means "past ordinary end of support", so every existing caller
    # behaves as before; `support_state` is the finer answer, and is the one to
    # read when the question is "is this machine actually being patched today".
    support_state: str = "supported"      # supported | esu | unsupported
    esu: dict | None = None               # afterlife.esu.describe(), when one applies
    #: Months until the date that actually binds in the CURRENT state. Equal to
    #: months_remaining everywhere except inside ESU, where ordinary support has
    #: already ended and the programme's own end date is what is left.
    months_to_state_end: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def _table() -> dict:
    global _TABLE
    if _TABLE is None:
        p = APP_DATA / "device_support.json"
        _TABLE = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"devices": {}, "os": {}}
    return _TABLE


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _find(index: dict, raw: str | None) -> tuple[str, dict] | None:
    """Exact normalised hit, else the longest indexed key contained in the input.

    Containment rather than fuzzy distance is deliberate: "Samsung Galaxy S21
    Ultra 5G" should resolve to the S21 entry, but a typo should resolve to
    nothing at all. A wrong support date is worse than no support date, because
    the user cannot tell it is wrong.
    """
    key = _norm(raw)
    if not key:
        return None
    if key in index:
        return key, index[key]
    hits = [k for k in index if len(k) >= 6 and k in key]
    if not hits:
        return None
    best = max(hits, key=len)
    return best, index[best]


def risk_from_months(months: float, is_eol: bool) -> float:
    """Months of remaining security support -> 0..1 risk.

    Past end of support is 1.0 with no decay: an unpatched machine does not get
    safer the longer it stays unpatched. Before that the risk falls linearly to
    a floor, so a device with three years left still carries a little.
    """
    if is_eol:
        return 1.0
    frac = 1.0 - (months / FULL_RISK_HORIZON_MONTHS)
    return round(min(_MAX_RISK, max(_MIN_RISK, frac)), 3)


def lookup(make_model: str | None = None, os_name: str | None = None,
           as_of: dt.date | None = None) -> SupportHorizon | None:
    """Device first, OS second.

    The device date wins where both exist. A Pixel running Android 14 stops
    getting patches when Google stops shipping them for that handset, not when
    Android 14 itself goes end of life -- the handset is the binding constraint.
    For a Dell or HP laptop there is no per-model entry, so the OS date is the
    only honest answer available and the response says which was used.
    """
    as_of = as_of or dt.date.today()
    tbl = _table()

    # os_families before the per-release os index: a user reports "Windows 10",
    # not "10 22H2 (W)". The family entry is the consumer cycle whose security
    # support runs longest, which is the date that governs someone still on it.
    for source, index, raw in (("device", tbl.get("devices", {}), make_model),
                               ("os", tbl.get("os_families", {}), os_name),
                               ("os", tbl.get("os", {}), os_name)):
        hit = _find(index, raw)
        if not hit:
            continue
        key, entry = hit
        try:
            eol_date = dt.date.fromisoformat(entry["eol_from"])
        except (ValueError, KeyError):
            continue
        days = (eol_date - as_of).days
        months = round(days / 30.44, 1)
        is_eol = days <= 0
        risk = risk_from_months(months, is_eol)

        # An extended-updates programme, where the vendor runs one. This is the
        # difference between "past end of support" and "actually unpatched",
        # and for Windows 10 -- the population this product exists for -- they
        # are a year apart. Charging full end-of-life risk to a machine that is
        # still receiving security updates was a real over-penalty.
        state = esu_mod.SupportState.UNSUPPORTED if is_eol else esu_mod.SupportState.SUPPORTED
        esu_detail = None
        months_to_state_end = months
        # The table splits the name across two fields -- product "Microsoft
        # Windows", release "10 22H2" -- so neither alone identifies the family.
        # Match on both joined, with the normalised index key as a backstop.
        prog = esu_mod.for_product(
            f"{entry.get('product') or ''} {entry.get('release') or ''} {key}"
        )
        if prog is not None:
            state = prog.state(as_of)
            esu_detail = esu_mod.describe(prog, as_of)
            if state is esu_mod.SupportState.ESU:
                # Inside ESU the binding date is the end of the programme, not
                # the end of ordinary support -- that one is already behind us.
                months_to_state_end = round(prog.days_left(as_of) / 30.44, 1)
                risk = esu_mod.esu_risk(months_to_state_end, risk_from_months)

        return SupportHorizon(
            product=entry.get("product") or "",
            release=entry.get("release") or "",
            eol_from=entry["eol_from"],
            eoas_from=entry.get("eoas_from"),
            months_remaining=months,
            is_eol=is_eol,
            eol_risk=risk,
            matched_on=source,
            matched_key=key,
            support_state=state.value,
            esu=esu_detail,
            months_to_state_end=months_to_state_end,
        )
    return None


def risk_detail(h: SupportHorizon) -> str:
    """The evidence line that rides on the score adjustment this horizon drives.

    Deliberately a date rather than a restatement of the risk as a percentage. A
    user can go and check "security updates ended 2025-10-14"; nobody can check
    "63% risk", which is the number they used to be shown instead.
    """
    if h.support_state == "esu" and h.esu:
        return (f"mainstream support ended {h.eol_from}; "
                f"Extended Security Updates run to {h.esu['esu_end']}")
    if h.is_eol:
        if h.esu:
            return f"Extended Security Updates ended {h.esu['esu_end']}"
        return f"security updates ended {h.eol_from}"
    if h.months_remaining < 24:
        return f"security updates end {h.eol_from} (~{h.months_remaining:.0f} months)"
    return f"security updates run to {h.eol_from}"


def reassess_note(h: SupportHorizon) -> str:
    """The one sentence the assessment could not previously produce."""
    # The ESU case has to come first. This machine IS past `eol_from`, so the
    # branch below would tell a user who is still receiving patches that they
    # stopped a year ago -- confidently, and wrongly, which is the failure mode
    # this project treats as worse than saying nothing.
    if h.support_state == "esu" and h.esu:
        days = h.esu["ends_in_days"]
        when = (f"in {days // 30} months" if days >= 60
                else f"in {days} days" if days > 0 else "imminently")
        note = (f"{h.product} {h.release} passed end of support on {h.eol_from}, "
                f"but Extended Security Updates run to {h.esu['esu_end']} — {when}. "
                f"There is no programme after that one.")
        if not h.esu["enrolment_open"]:
            note += " Enrolment has already closed."
        return note

    if h.is_eol:
        years = abs(h.months_remaining) / 12
        if h.esu:  # the programme existed and has now run out
            return (f"{h.product} {h.release} has had no security updates since "
                    f"{h.esu['esu_end']}, when Extended Security Updates ended. "
                    f"Nothing further is offered.")
        return (f"{h.product} {h.release} stopped receiving security updates on "
                f"{h.eol_from}"
                + (f" — {years:.1f} years ago." if years >= 0.6 else "."))
    if h.months_remaining <= 24:
        return (f"Security updates end {h.eol_from} — about "
                f"{h.months_remaining:.0f} months away. Reassess then.")
    return (f"Security updates run until {h.eol_from}, about "
            f"{h.months_remaining/12:.1f} years away.")
