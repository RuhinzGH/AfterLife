"""What fixing this device would buy: a better grade, or more work it can handle.

Two different kinds of upgrade, kept apart because they promise different things:

  * `condition`: undo measured wear (a worn battery) or fix the fault the owner
    reported. This moves the *grade*, because the grade is a condition score.
  * `capability`: add memory. This moves which *workload tier* the machine
    meets for its use (afterlife/persona.py). It is the only one of the two
    that can honestly end with "...and then it can do X".

Every number is recomputed through the functions that produced the original
score and tier (blend_score, the deep trust score's battery rule, the persona
tiers), never estimated separately, so an uplift can never promise a grade the
real scorer would not award.
"""
from __future__ import annotations

from typing import Any

from .assessment import blend_score
from .passport import battery_points
from .persona import RAM_TOLERANCE, TIERS, gpu_tier

#: A replacement battery modelled as a fresh cell, not 100%: no part delivers that.
REPLACED_BATTERY_HEALTH = 95.0

#: Below this there is no memory upgrade worth naming.
MIN_USEFUL_RAM_GB = 2


def condition_uplift(hardware_trust: int, eol_risk: float | None, battery_health: float | None,
                     age_years: float | None, fault_described: bool, fault_detail: str | None = None,
                     trust_measured: bool = False, storage: str | None = None,
                     eol_source: str | None = None) -> dict[str, Any] | None:
    """Re-score the device as if its fixable problems were fixed. None when
    nothing fixable is holding the score down (age alone has no honest fix)."""
    def score(trust: int, battery: float | None, fault: bool) -> dict[str, Any]:
        return blend_score(trust, eol_risk, battery, age_years, fault,
                           eol_source=eol_source, fault_detail=fault_detail,
                           trust_measured=trust_measured)

    now = score(hardware_trust, battery_health, fault_described)
    actions: list[dict[str, Any]] = []

    # Battery, only when it costs points (both rules start at 80%). On a deep
    # scan the battery sits inside the measured trust score, so the new battery
    # is re-scored with that same rule; on other scans blend_score handles it.
    trust, battery = hardware_trust, battery_health
    if battery_health is not None and battery_health < 80:
        if trust_measured:
            trust = hardware_trust + battery_points(REPLACED_BATTERY_HEALTH) - battery_points(battery_health)
        battery = REPLACED_BATTERY_HEALTH
        gain = score(trust, battery, fault_described)["combined_score"] - now["combined_score"]
        if gain > 0:
            actions.append({"action": "Replace the battery", "points": gain,
                            "detail": f"it holds {battery_health:.0f}% of its original charge"})

    # The reported fault, only when it was recognised (it costs 5 points). When
    # the only fault named is the battery, the new battery is that fix, so it is
    # one action rather than two.
    if fault_described:
        gain = score(trust, battery, False)["combined_score"] - score(trust, battery, True)["combined_score"]
        battery_fault = (fault_detail or "").strip().lower() == "battery"
        if gain > 0 and battery_fault and actions:
            actions[0]["points"] += gain
            actions[0]["detail"] += ", and it is the fault you reported"
            actions[0]["fixes_fault"] = True
        elif gain > 0:
            actions.append({"action": "Fix the reported fault", "points": gain, "fixes_fault": True,
                            "detail": fault_detail or "the problem you described"})

    # A mechanical disk does not move the score (it measures wear, not speed),
    # so it is offered with no points attached.
    ssd_swap = bool(storage and "hdd" in storage.lower())
    if not actions and not ssd_swap:
        return None

    fault_fixed = any(a.get("fixes_fault") for a in actions)
    after = score(trust, battery, fault_described and not fault_fixed)
    return {
        "current_score": now["combined_score"],
        "current_grade": now["grade"],
        "projected_score": after["combined_score"],
        "projected_grade": after["grade"],
        "grade_changes": after["grade"] != now["grade"],
        "actions": actions,
        "ssd_swap_available": ssd_swap,
    }


def capability_uplift(persona: str | None, cores: int | None, ram_gb: float | None,
                      gpu: str | None, ram_is_lower_bound: bool = False) -> dict[str, Any] | None:
    """The next workload tier more memory alone would unlock. None when the next
    tier also needs more cores or better graphics (fixed on a laptop), when the
    device already meets every tier, or when memory is only known as "8 or more"."""
    tiers = TIERS.get(persona if persona in TIERS else "general")
    if not cores or not ram_gb or ram_is_lower_bound:
        return None
    g, _ = gpu_tier(gpu)
    current, nxt = None, None
    for t in tiers:
        if cores >= t["cores"] and ram_gb >= t["ram_gb"] * RAM_TOLERANCE and g >= t["gpu_tier"]:
            current = t
        else:
            nxt = t
            break
    if not nxt or cores < nxt["cores"] or g < nxt["gpu_tier"]:
        return None
    needed = nxt["ram_gb"] - ram_gb
    if needed < MIN_USEFUL_RAM_GB:
        return None
    return {
        "current_tier": current["name"] if current else None,
        "next_tier": nxt["name"],
        "ram_needed_gb": round(needed),
        "target_ram_gb": nxt["ram_gb"],
    }
