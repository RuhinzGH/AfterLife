"""Resale estimate: a transparent depreciation formula, not a trained model.

There is no public dataset of used laptop, desktop or console sale prices by
condition (public laptop datasets price new specifications), so rather than fake
precision, every device type uses the same formula the card shows:

    price new x (1 - yearly loss) ^ age x condition factor x cosmetic factor

The yearly loss per device type and the factor per grade are stated assumptions
(the A/B/C/D steps mirror refurbisher grading); they are listed on the card and
in the assumptions table, and the result is always a +/-15% range, never one
number. The grade is the one the real scorer just awarded, so the price can never
describe a condition the assessment did not find. The scan cannot see a cracked
screen or a dent, so cosmetic condition is the owner's own answer, kept separate.
"""
from __future__ import annotations

from typing import Any

#: Assumed share of value lost per year, by device type.
YEARLY_LOSS = {"Laptop": 0.18, "Desktop computer": 0.17, "Mobile": 0.22,
               "Tablet": 0.20, "Games console": 0.16}
DEFAULT_YEARLY_LOSS = 0.18

#: Assumed share of the age-adjusted value kept at each condition grade.
GRADE_FACTOR = {"A - excellent": 0.90, "B - good": 0.72, "C - serviceable": 0.50, "D - limited": 0.28}
GRADE_LADDER = ["D - limited", "C - serviceable", "B - good", "A - excellent"]

#: The owner's own answer about scratches and dents (unverified).
COSMETIC_FACTOR = {"Like new": 1.05, "Good": 1.0, "Fair": 0.85, "Poor": 0.6}

#: A working device never falls to nothing: the floor share of the new price.
MIN_AGE_FACTOR = 0.12
RANGE = 0.15


def _range(price_new: float, age_factor: float, grade: str, cosmetic_factor: float) -> dict[str, int]:
    mid = price_new * age_factor * GRADE_FACTOR.get(grade, GRADE_FACTOR["C - serviceable"]) * cosmetic_factor
    # A depreciation formula must never value a used device above its new
    # price, which the top of the range could otherwise do for a nearly new,
    # A-grade, "like new" device.
    high = min(mid * (1 + RANGE), price_new)
    mid = min(mid, price_new)
    low = min(mid * (1 - RANGE), high)
    return {"low": round(low), "mid": round(mid), "high": round(high)}


def estimate_resale(price_new: float, product_category: str | None, age_years: float | None,
                    grade: str, cosmetic: str | None = None, currency: str = "USD") -> dict[str, Any]:
    if not price_new or price_new <= 0:
        raise ValueError("price_new must be positive")
    category = product_category if product_category in YEARLY_LOSS else None
    loss = YEARLY_LOSS.get(category, DEFAULT_YEARLY_LOSS)
    age = max(0.0, float(age_years or 0))
    age_factor = max(MIN_AGE_FACTOR, (1 - loss) ** age)
    cosmetic = cosmetic if cosmetic in COSMETIC_FACTOR else "Good"
    cosmetic_factor = COSMETIC_FACTOR[cosmetic]

    potential = None
    if grade in GRADE_LADDER and grade != GRADE_LADDER[-1]:
        up = GRADE_LADDER[GRADE_LADDER.index(grade) + 1]
        potential = {**_range(price_new, age_factor, up, cosmetic_factor), "grade": up}

    return {
        **_range(price_new, age_factor, grade, cosmetic_factor),
        "currency": currency,
        "potential": potential,
        "inputs": {
            "price_new": price_new, "category": category or "Other", "age_years": age,
            "yearly_loss": loss, "age_factor": round(age_factor, 3),
            "grade": grade, "grade_factor": GRADE_FACTOR.get(grade, GRADE_FACTOR["C - serviceable"]),
            "cosmetic": cosmetic, "cosmetic_factor": cosmetic_factor,
        },
    }
