"""Do AfterLife's main conclusions survive a change in its assumptions? (S3-08)

Two questions, both answered by running the site's own functions with one
assumption changed at a time, never by a separate copy of the formulas:

1. Carbon payback. With every other input at its default (a laptop with the
   median declared manufacturing carbon on India's grid, 45 W kept vs 28 W
   replacement, 8 hours a day), how many years does a replacement need to repay
   its manufacturing carbon when ONE input moves to the edge of its plausible
   range? And in the one case that stacks every change in replacement's favour?
2. The score. Across a grid of device inputs (every combination of end-of-life
   risk, battery, age and reported fault for an instant scan, and of measured
   hardware score and support risk for a deep scan, equally weighted, not a
   sample of real devices), how often does the GRADE or the TOP RECOMMENDATION
   change when the end-of-life weight is 10 or 20 instead of 15, or the
   battery, age and fault penalties are halved or doubled?

The ranges tested are stated with each row: hours from the card's own
scenarios, power classes from cpu_power.py, manufacturing carbon from the
middle half of the published laptop figures, grids from the data.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import grid
from .assessment import (
    AGE_PENALTY, BATTERY_BAD_PENALTY, BATTERY_WEAR_PENALTY, BROWSER_START_TRUST, EOL_WEIGHT,
    FAULT_PENALTY, blend_score,
)
from .cpu_power import INTEL_SUFFIX_W
from .pathways import compute_pathways

ROOT = Path(__file__).resolve().parent.parent

#: Edges tested for the two duty-cycle factors that have no data behind them.
LOAD_RANGE = (0.30, 0.50)
OVERHEAD_RANGE = (1.3, 2.0)
#: The end-of-life weights the backlog asks about, and the penalty scalings.
EOL_WEIGHTS = (10, 20)
PENALTY_SCALES = (0.5, 2.0)


def _laptop_carbon() -> dict[str, float]:
    d = json.loads((ROOT / "app_data" / "embodied_carbon.json").read_text(encoding="utf-8"))
    c = d["classes"]["Laptop"]
    return {"median": c["median_kg"], "p25": c["p25_kg"], "p75": c["p75_kg"]}


def _dirtiest_country() -> tuple[str, str, float]:
    d = json.loads(grid.DATA.read_text(encoding="utf-8"))["countries"]
    code, row = max(d.items(), key=lambda kv: kv[1]["gco2_kwh"])
    return code, row["name"], row["gco2_kwh"]


def _years(**kw) -> float | None:
    base = {"country": "IN", "embodied_kg": _laptop_carbon()["median"], "old_tdp_w": grid.DEFAULT_OLD_TDP_W,
            "new_tdp_w": grid.DEFAULT_NEW_TDP_W, "hours_per_year": grid.HOURS_PER_YEAR,
            "load_factor": grid.LOAD_FACTOR, "system_overhead": grid.SYSTEM_OVERHEAD}
    r = grid.break_even(**{**base, **kw})
    return r["years"] if r and r["repays"] else None


def carbon() -> dict[str, Any]:
    emb = _laptop_carbon()
    d_code, d_name, d_g = _dirtiest_country()
    hrs = grid.SCENARIO_HOURS
    rows = [
        ("Hours a day", f"{hrs['light']} h (light)", {"hours_per_year": hrs["light"] * grid.DAYS_PER_YEAR}),
        ("Hours a day", f"{hrs['heavy']} h (heavy)", {"hours_per_year": hrs["heavy"] * grid.DAYS_PER_YEAR}),
        ("Average load", f"{LOAD_RANGE[0]:g} of rated power", {"load_factor": LOAD_RANGE[0]}),
        ("Average load", f"{LOAD_RANGE[1]:g} of rated power", {"load_factor": LOAD_RANGE[1]}),
        ("Whole-laptop overhead", f"x{OVERHEAD_RANGE[0]:g}", {"system_overhead": OVERHEAD_RANGE[0]}),
        ("Whole-laptop overhead", f"x{OVERHEAD_RANGE[1]:g}", {"system_overhead": OVERHEAD_RANGE[1]}),
        ("Old processor", f"{INTEL_SUFFIX_W['U']} W (thin laptop)", {"old_tdp_w": INTEL_SUFFIX_W["U"]}),
        ("Old processor", f"{INTEL_SUFFIX_W['HX']} W (top laptop)", {"old_tdp_w": INTEL_SUFFIX_W["HX"]}),
        ("Replacement processor", f"{INTEL_SUFFIX_W['U']} W (thin laptop)", {"new_tdp_w": INTEL_SUFFIX_W["U"]}),
        ("Carbon to make a laptop", f"{emb['p25']:g} kg (lower quartile)", {"embodied_kg": emb["p25"]}),
        ("Carbon to make a laptop", f"{emb['p75']:g} kg (upper quartile)", {"embodied_kg": emb["p75"]}),
        ("Grid", "France", {"country": "FR"}),
        ("Grid", "World average", {"country": None}),
        ("Grid", f"{d_name} (dirtiest in the data, {d_g:.0f} g/kWh)", {"country": d_code}),
    ]
    out = [{"factor": f, "value": v, "years": _years(**kw)} for f, v, kw in rows]
    stacked = {"hours_per_year": hrs["heavy"] * grid.DAYS_PER_YEAR, "load_factor": LOAD_RANGE[1],
               "system_overhead": OVERHEAD_RANGE[1], "old_tdp_w": INTEL_SUFFIX_W["HX"],
               "new_tdp_w": INTEL_SUFFIX_W["U"], "embodied_kg": emb["p25"], "country": d_code}
    finite = [r["years"] for r in out if r["years"] is not None]
    return {
        "base": {"years": _years(), "grid": "India", "embodied_kg": emb["median"],
                 "old_w": grid.DEFAULT_OLD_TDP_W, "new_w": grid.DEFAULT_NEW_TDP_W,
                 "hours_a_day": grid.HOURS_PER_YEAR / grid.DAYS_PER_YEAR},
        "one_at_a_time": out,
        "range_years": [min(finite), max(finite)] if finite else None,
        "never_repays": [r["value"] for r in out if r["years"] is None],
        "everything_against_keeping": {"years": _years(**stacked),
                                       "what": f"{hrs['heavy']} h a day, load {LOAD_RANGE[1]:g}, overhead x{OVERHEAD_RANGE[1]:g}, "
                                               f"{INTEL_SUFFIX_W['HX']} W kept vs {INTEL_SUFFIX_W['U']} W replacement, "
                                               f"{emb['p25']:g} kg, {d_name}'s grid"},
    }


def _devices() -> list[dict[str, Any]]:
    risks = [i / 20 for i in range(21)]
    instant = [{"hardware_trust": BROWSER_START_TRUST, "eol_risk": e, "battery_health": b, "age_years": a,
                "fault_described": f, "trust_measured": False}
               for e in risks for b in (None, 90, 70, 50) for a in (2, 5, 8) for f in (False, True)]
    deep = [{"hardware_trust": t, "eol_risk": e, "battery_health": None, "age_years": None,
             "fault_described": False, "trust_measured": True}
            for t in range(40, 101, 5) for e in risks]
    return instant + deep


def _top(grade: str) -> str:
    return compute_pathways(grade)[0]["label"]


def score() -> dict[str, Any]:
    devices = _devices()
    base = [blend_score(**d) for d in devices]
    variants = [(f"End-of-life weight {w}", {"EOL_WEIGHT": w}) for w in EOL_WEIGHTS]
    for k in PENALTY_SCALES:
        variants.append((f"Battery, age and fault penalties x{k:g}", {
            "BATTERY_WEAR_PENALTY": BATTERY_WEAR_PENALTY * k, "BATTERY_BAD_PENALTY": BATTERY_BAD_PENALTY * k,
            "AGE_PENALTY": AGE_PENALTY * k, "FAULT_PENALTY": FAULT_PENALTY * k}))
    rows = []
    for name, rules in variants:
        new = [blend_score(**d, rules=rules) for d in devices]
        grade = sum(b["grade"] != n["grade"] for b, n in zip(base, new))
        top = sum(_top(b["grade"]) != _top(n["grade"]) for b, n in zip(base, new))
        shift = sum(abs(b["combined_score"] - n["combined_score"]) for b, n in zip(base, new)) / len(devices)
        rows.append({"change": name, "grade_changes_pct": round(100 * grade / len(devices), 1),
                     "top_option_changes_pct": round(100 * top / len(devices), 1),
                     "mean_points_moved": round(shift, 1),
                     "max_points_moved": max(abs(b["combined_score"] - n["combined_score"]) for b, n in zip(base, new))})
    return {"devices": len(devices), "base_eol_weight": EOL_WEIGHT,
            "grid": "every combination of end-of-life risk (0 to 100% in 5% steps), battery (unread, 90, 70, 50%), "
                    "age (2, 5, 8 years) and reported fault for an instant scan, and of measured hardware score "
                    "(40 to 100) and support risk for a deep scan; equally weighted, not real devices",
            "variants": rows}


@lru_cache(maxsize=1)
def analysis() -> dict[str, Any]:
    return {"carbon": carbon(), "score": score()}
