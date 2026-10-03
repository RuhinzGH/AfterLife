"""Lifecycle Pathways — five parallel futures for one device, not one verdict.

Instead of collapsing everything into a single recommendation, show the
device's genuinely live options side by side, each independently scored, so
"obsolete" reads as a decision informed by multiple axes (security,
performance, economics) rather than a binary the app hands down. Same house
rule as everywhere else in this codebase: every pathway's fit score and
action list is computed here in plain code, and the framing line above the
cards is filled in from the top-ranked pathway.
"""
from __future__ import annotations

from typing import Any


# Fixed identity per pathway (icon/color never change) -- only the *fit*
# score and action list vary per device. Order here is the default display
# order before ranking re-sorts by fit.
PATHWAYS: list[dict[str, str]] = [
    {"key": "primary", "label": "Keep as Primary Device", "icon": "🖥️", "color": "green"},
    {"key": "hardening", "label": "Keep with Hardening", "icon": "🛡️", "color": "amber"},
    {"key": "repurpose", "label": "Repurpose", "icon": "🔁", "color": "brand-light"},
    {"key": "sell", "label": "Sell", "icon": "💰", "color": "brand"},
    {"key": "recycle", "label": "Recycle", "icon": "♻️", "color": "red"},
]

# Base fit score (0-100) by combined-score grade -- explicit and reproducible,
# same spirit as blend_score()'s point table in assessment.py. Every number
# here is a judgment call, disclosed as such rather than dressed up as learned.
_GRADE_FIT: dict[str, dict[str, int]] = {
    "primary":   {"A - excellent": 95, "B - good": 75, "C - serviceable": 45, "D - limited": 15},
    "hardening": {"A - excellent": 30, "B - good": 50, "C - serviceable": 60, "D - limited": 40},
    "repurpose": {"A - excellent": 40, "B - good": 55, "C - serviceable": 75, "D - limited": 60},
    "sell":      {"A - excellent": 80, "B - good": 65, "C - serviceable": 40, "D - limited": 15},
    "recycle":   {"A - excellent": 5,  "B - good": 15, "C - serviceable": 30, "D - limited": 85},
}
_DEFAULT_GRADE = "C - serviceable"

# win11.py's Blocker enum values -> a plain-English fix. Permanent blockers
# (cpu_generation, cpu_spec) and the non-finding unknown_tpm map to None on
# purpose -- there's no action to hand the user for either.
_HARDENING_ACTION_LABELS = {
    "tpm": "Enable TPM (fTPM/PTT) in BIOS/UEFI settings",
    "secure_boot": "Enable Secure Boot in BIOS/UEFI settings",
    "uefi": "Convert the boot drive from legacy BIOS to UEFI/GPT",
    "ram": "Add more RAM",
    "storage": "Upgrade the system drive for more space",
}

_REPURPOSE_IDEAS = {
    "A - excellent": ["Family computer", "Student device", "Linux workstation"],
    "B - good": ["Family computer", "Student device", "Home media PC"],
    "C - serviceable": ["Home media PC", "Linux workstation", "Home server"],
    "D - limited": ["Home server", "Offline / air-gapped use", "Parts donor"],
}

_SELL_NOTE = {
    "A - excellent": "Strong resale candidate — sell sooner rather than later, value only drops from here.",
    "B - good": "Still worth listing; a clean cosmetic condition matters more at this grade.",
    "C - serviceable": "Resale value is modest — worth checking the estimate before deciding vs. repurposing.",
    "D - limited": "Resale value is likely minimal; repurposing or recycling is usually the better outcome.",
}

_RECYCLE_NOTE = {
    "A - excellent": "Not the right call yet — this device has real life left in every other pathway.",
    "B - good": "Premature — hardening or resale both make more sense first.",
    "C - serviceable": "A fallback if the other pathways don't fit your situation, not the first choice.",
    "D - limited": "Hardware is no longer economical to keep servicing — recycling responsibly is the honest call.",
}


def _hardware_actions(win11_blockers: list[str] | None, storage: str | None) -> list[str]:
    actions = [label for b in (win11_blockers or [])
               if (label := _HARDENING_ACTION_LABELS.get(b))]
    if storage and "hdd" in storage.lower():
        actions.append("Replace the HDD with an SSD")
    # Generic hygiene, always relevant regardless of what was detected above.
    actions.append("Use a currently-supported, patched browser")
    actions.append("Remove software no longer receiving security updates")
    if "tpm" not in (win11_blockers or []):
        actions.append("Enable full-disk encryption (BitLocker or equivalent)")
    return actions


def compute_pathways(
    grade: str,
    win11_status: str | None = None,
    win11_blockers: list[str] | None = None,
    win11_permanently_blocked: bool | None = None,
    win11_firmware_fixable: bool | None = None,
    storage: str | None = None,
) -> list[dict[str, Any]]:
    """Score all five pathways for this device and rank them.

    Exactly one pathway is marked "best_fit" (the top score) -- the rest are
    labeled "also_viable" or "not_ideal" by threshold, so the UI can show all
    five as genuinely live options while still answering the question a user
    actually asked. Every score and action list here is explicit and
    reproducible from the inputs; nothing is inferred by an LLM.
    """
    fits = {k: table.get(grade, table[_DEFAULT_GRADE]) for k, table in _GRADE_FIT.items()}

    # Windows 11 eligibility reshapes "primary" and "hardening" specifically --
    # repurpose/sell/recycle don't care whether Windows 11 is reachable.
    if win11_status == "NOT ELIGIBLE":
        fits["primary"] = max(0, fits["primary"] - 25)
        if win11_firmware_fixable:
            fits["hardening"] = max(fits["hardening"], 85)
        elif win11_permanently_blocked:
            fits["hardening"] = max(fits["hardening"], 55)

    best_key = max(fits, key=fits.get)

    out = []
    for p in PATHWAYS:
        key, score = p["key"], fits[p["key"]]
        status = "best_fit" if key == best_key else ("also_viable" if score >= 55 else "not_ideal")

        if key == "hardening":
            actions = _hardware_actions(win11_blockers, storage)
        elif key == "repurpose":
            actions = _REPURPOSE_IDEAS.get(grade, _REPURPOSE_IDEAS[_DEFAULT_GRADE])
        elif key == "sell":
            actions = [_SELL_NOTE.get(grade, _SELL_NOTE[_DEFAULT_GRADE])]
        elif key == "recycle":
            actions = [_RECYCLE_NOTE.get(grade, _RECYCLE_NOTE[_DEFAULT_GRADE])]
        else:  # primary
            actions = (["Meets everyday use comfortably as-is."] if score >= 75
                       else ["Usable as a primary device, but watch for slowdowns as software requirements grow."])

        out.append({**p, "fit_score": score, "status": status, "actions": actions})

    out.sort(key=lambda p: p["fit_score"], reverse=True)
    return out


def narrate_pathways(pathways: list[dict[str, Any]], grade: str) -> dict[str, Any]:
    """One short framing line for the pathways card, built from the top pathway."""
    best = pathways[0]
    return {
        "summary": f"\"{best['label']}\" is the strongest fit today, given this device's "
                   f"\"{grade}\" condition grade — though the other pathways below are real "
                   f"options too, not just runners-up.",
        "source": "fallback",
    }
