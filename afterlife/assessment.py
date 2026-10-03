"""Combined lifecycle assessment: a deterministic blended score, the lifecycle in
years, and a written summary assembled by fixed rules from those numbers.

  1. The blend combines the hardware score, the ML lifecycle model and the user's
     input -- computed in code, so it is defensible and reproducible.
  2. The lifecycle is described in years -- estimated remaining life and the stage
     pipeline -- plus practical usage suggestions.

Nothing here guesses: every sentence in the summary is filled in from a computed
value, so the words can never disagree with the numbers.
"""
from __future__ import annotations

from typing import Any



#: What an `eol_risk` value actually measures. Two different quantities reach
#: blend_score through that one parameter and they are not interchangeable:
#:
#:   "support"  months until this OS/device stops receiving security updates,
#:              normalised to 0-1 against a published end date (device_support.py).
#:   "ml"       the repair classifier's probability that a device like this one
#:              is beyond saving (predict.py, trained on Open Repair Alliance).
#:
#: Both land in 0-1, which is precisely why the label has to name which one the
#: user got. Unknown provenance gets a neutral label -- never a confident wrong one.
EOL_SOURCE_LABELS = {
    "support": "Security support horizon",
    "ml": "ML end-of-life risk",
}
_EOL_FACTOR_UNLABELLED = "End-of-life risk"


def blend_score(hardware_trust: int, eol_risk: float | None,
                battery_health: float | None, age_years: float | None,
                fault_described: bool, eol_source: str | None = None,
                eol_detail: str | None = None) -> dict[str, Any]:
    """Deterministically fold the end-of-life signal + user signals into the hardware score.

    Starts from the hardware trust score, then applies bounded adjustments so the result
    reflects the end-of-life risk, real battery wear, age, and any reported fault.
    Every term is explicit and reproducible.

    `eol_source` names where `eol_risk` came from (see EOL_SOURCE_LABELS) and
    `eol_detail` is the human-readable evidence for it -- a support end date reads
    as a date the owner can go and check, which "63% risk" never does.
    """
    score = float(hardware_trust)
    adjustments: list[dict[str, Any]] = []

    if eol_risk is not None:
        # Higher end-of-life risk -> pull the score down, up to -15.
        #
        # This adjustment used to be labelled "ML end-of-life risk" unconditionally.
        # That was wrong on the deep-scan path, which is the *more* trusted of the
        # two: a deep scan never runs the repair classifier, so its risk figure is
        # resolved from a published support date -- and the page still reported it
        # as a model verdict the product had not computed. Provenance now travels
        # with the number rather than being assumed.
        delta = -round(eol_risk * 15, 1)
        score += delta
        adjustments.append({"factor": EOL_SOURCE_LABELS.get(eol_source, _EOL_FACTOR_UNLABELLED),
                            "detail": eol_detail or f"{eol_risk*100:.0f}% risk",
                            "delta": delta, "source": eol_source})

    # 80%/60% aren't arbitrary -- 80% is Amazon Renewed's own published
    # battery-health bar for its standard refurb grade (≥90% for Premium), so
    # a device clearing it meets a real, named industry threshold. A browser
    # scan cannot read battery health, so this only applies when it is supplied.
    if battery_health is not None and battery_health < 80:
        delta = -6 if battery_health < 60 else -3
        score += delta
        adjustments.append({"factor": "battery wear", "detail": f"{battery_health:.0f}%",
                            "delta": delta})

    if age_years is not None and age_years > 6:
        score -= 4; adjustments.append({"factor": "age", "detail": f"{age_years:.0f} yr", "delta": -4})

    if fault_described:
        score -= 5; adjustments.append({"factor": "reported fault", "detail": "user-described", "delta": -5})

    score = max(0, min(100, round(score)))
    grade = ("A - excellent" if score >= 85 else "B - good" if score >= 70
             else "C - serviceable" if score >= 55 else "D - limited")
    return {"combined_score": score, "grade": grade,
            "hardware_trust": hardware_trust, "adjustments": adjustments}


def key_points(blend: dict[str, Any], pipeline: dict[str, Any],
               win11_status: str | None = None, *,
               battery_health: float | None = None,
               age_years: float | None = None) -> dict[str, list[str]]:
    """A scannable strengths/weaknesses checklist -- judges and buyers skim, they
    don't read paragraphs. Every line here is derived directly from blend_score's
    own adjustments and estimate_years' own output, so it can never disagree with
    the numbers above it (unlike a free-text LLM summary, which could in principle
    drift even under strict grounding instructions).
    """
    adjustments = blend.get("adjustments", [])
    adj_factors = {a["factor"] for a in adjustments}
    # No .capitalize() -- "ML end-of-life risk" already has real capitalization worth
    # keeping (an acronym), and .capitalize() would flatten it to "Ml end-of-life risk".
    weaknesses = [f"{a['factor']}: {a['detail']}" for a in adjustments]
    strengths: list[str] = []

    # A strength needs a measurement, not merely the absence of a penalty.
    # blend_score only charges battery wear when a reading EXISTS and is poor,
    # and only charges age when an age is KNOWN and high -- so "no penalty" is
    # also what an instant scan produces, where the browser cannot read the
    # battery at all. Reading silence as health put "Battery in good health"
    # beside a passport field saying battery wear was not exposed.
    if battery_health is not None and "battery wear" not in adj_factors:
        strengths.append("Battery in good health")
    if age_years is not None and "age" not in adj_factors:
        strengths.append("Still within its expected prime years")
    if "reported fault" not in adj_factors:
        strengths.append("No reported hardware faults")

    if win11_status == "ELIGIBLE":
        strengths.append("Windows 11 compatible")
    elif win11_status == "NOT ELIGIBLE":
        weaknesses.append("Not eligible for the Windows 11 upgrade")

    remaining = pipeline.get("estimated_remaining_years")
    if isinstance(remaining, (int, float)):
        if remaining >= 3:
            strengths.append(f"~{remaining:g} years of projected life left")
        elif remaining > 0:
            weaknesses.append(f"Only ~{remaining:g} years of projected life left")

    if not strengths:
        strengths.append(f"Hardware trust baseline of {blend.get('hardware_trust')}/100")

    return {"strengths": strengths, "weaknesses": weaknesses}


def estimate_years(combined_score: int, age_years: float | None,
                   battery_health: float | None) -> dict[str, Any]:
    """A transparent remaining-safe-life estimate and a lifecycle stage pipeline."""
    remaining = round(combined_score / 100 * 8)  # 0-100 -> up to ~8 years
    if battery_health is not None and battery_health < 60:
        remaining = max(1, remaining - 1)
    age = age_years or 0
    stages = [
        {"stage": "New", "year": 0, "state": "past"},
        {"stage": "In service", "year": round(age, 1), "state": "past"},
        {"stage": "Now", "year": round(age, 1), "state": "current"},
        {"stage": "Extended use", "year": round(age + remaining, 1), "state": "future"},
        {"stage": "Recycle / harvest", "year": round(age + remaining, 1) + 1, "state": "future"},
    ]
    return {"estimated_remaining_years": remaining,
            "projected_total_life": round(age + remaining, 1), "stages": stages}


# The one-line personality beat under the grade. Picked deterministically in code,
# same as the score itself: reliable, on-brand, and it never touches a number.
_PUNCHLINES = {
    "A - excellent": ["Diagnosis: annoyingly fine.", "Still got it.",
                      "The industry wanted you to upgrade already. Hard pass."],
    "B - good": ["Not dead. Just not trying its hardest.", "One setting away from irrelevant.",
                "Fully capable of outliving its warranty out of spite."],
    "C - serviceable": ["Hanging in there -- technically.", "Retirement-adjacent, not retired.",
                        "Still clocking in. Barely, but still."],
    "D - limited": ["Living on borrowed time, and it knows it.",
                    "The industry already wrote this one off. We're just double-checking."],
}


def _punchline(grade: str, score: int) -> str:
    lines = _PUNCHLINES.get(grade, _PUNCHLINES["C - serviceable"])
    return lines[score % len(lines)]


def narrate(context: dict[str, Any]) -> dict[str, Any]:
    """Turn the computed assessment into a summary + suggestions.

    Returns {summary, lifecycle_note, suggestions:[...], confidence_note, punchline,
    source}. Every field is filled in from the computed numbers by fixed rules;
    `punchline` is a deterministic lookup -- see _PUNCHLINES above.
    """
    grade, score = context.get("grade", "C - serviceable"), context.get("combined_score", 0)
    out = _fallback(context)
    out["punchline"] = _punchline(grade, int(score) if score else 0)
    return out


def _fallback(context: dict[str, Any]) -> dict[str, Any]:
    score = context.get("combined_score", "?")
    yrs = context.get("estimated_remaining_years", "?")
    return {
        "summary": f"This device scores {score}/100 on the combined assessment, blending its "
                   f"hardware condition with the lifecycle model. It has an estimated {yrs} years "
                   f"of safe service life remaining.",
        "lifecycle_note": f"Roughly {yrs} more years of useful life before recycling should be considered.",
        "suggestions": [
            "Keep the OS and browser patched to stay secure without new hardware.",
            "If the battery is worn, a replacement is far cheaper than a new device.",
            "Reassign to lighter-duty or secondary use as it ages rather than retiring it.",
            "Store the signed passport so a future buyer can trust its condition.",
        ],
        "confidence_note": "Based on what a browser can see -- battery wear and disk health "
                           "are not measured in this scan.",
        "source": "fallback",
    }
