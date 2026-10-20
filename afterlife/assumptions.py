"""Every number AfterLife assumes, with what kind of number it is and why (S2-12).

Each row names the constant it describes ("module:NAME"), and its value is read
from that constant when the page asks, so the table on How it works can never
drift from the code. tests/test_assumptions.py fails if a scoring constant is
added to an audited module without a row here.

Three kinds of number:
  * learned:   fitted to data by a script or a model;
  * looked up: taken from a public dataset or a manufacturer's specification;
  * chosen:    a design decision, stated with its reason and its limit.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent

LEARNED, LOOKED_UP, CHOSEN = "learned", "looked up", "chosen"


def _app_data(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "app_data" / name).read_text(encoding="utf-8"))


def _row(ref: str | Callable[[], Any], name: str, kind: str, why: str, limit: str, source: str,
         unit: str = "") -> dict[str, Any]:
    return {"ref": ref, "name": name, "kind": kind, "why": why, "limit": limit,
            "source": source, "unit": unit}


def _value(ref: str | Callable[[], Any]) -> Any:
    if callable(ref):
        return ref()
    module, _, attr = ref.partition(":")
    return getattr(importlib.import_module(module), attr)


A, P, D, G, C = ("afterlife.assessment", "afterlife.passport", "afterlife.device_support",
                 "afterlife.grid", "afterlife.cpu_power")
W, PE, U, PR = "afterlife.pathways", "afterlife.persona", "afterlife.uplift", "afterlife.pricing"

GROUPS: list[dict[str, Any]] = [
    {"title": "The score and the years", "rows": [
        _row(lambda: round(_app_data("lifecycle_metrics.json")["winner_grouped"]["eol_recall"] * 100),
             "End-of-life model: share of beyond-repair devices it catches", LEARNED,
             "A calibrated Random Forest trained on 23,748 community repair records, tested only on "
             "repair venues it never saw. It catches about two thirds of devices that ended up beyond repair; "
             "after calibration its percentages match observed rates (error "
             f"{_app_data('lifecycle_metrics.json')['calibration']['ece_calibrated']}).",
             "A risk for devices like this one, from community repair data, not a diagnosis of this unit.",
             "app_data/lifecycle_metrics.json (scripts/train_lifecycle.py)", "%"),
        _row(f"{A}:BROWSER_START_TRUST", "Starting score for an instant scan", CHOSEN,
             "A browser cannot measure hardware, so every instant scan starts as 'working, unverified'. "
             "75 sits inside grade B, so an unmeasured device is treated as ordinary until evidence moves it.",
             "Not a measurement; the deep scan replaces it with a measured score.", "Design choice"),
        _row(f"{A}:EOL_WEIGHT", "Points for a 100% end-of-life risk", CHOSEN,
             "Exactly one grade band (bands are 15 points wide), so the model can move a device by at most one "
             "grade on its own: it informs the grade but cannot decide it.",
             "x10 or x20 would move a typical device by under a point.", "Design choice", "points"),
        _row(f"{A}:BATTERY_WEAR_PCT", "Battery counts as worn below", LOOKED_UP,
             "Amazon Renewed only sells refurbished devices whose battery holds at least 80% of its "
             "original capacity; Apple designs its batteries to keep up to 80% after 1,000 cycles.",
             "A browser cannot read the battery, so this applies only to deep scans.",
             "Amazon Renewed battery standard; Apple Battery Service", "%"),
        _row(f"{A}:BATTERY_WEAR_PENALTY", "Points for a worn battery", CHOSEN,
             "A small, visible cost for a fixable problem.", "The size is judgement.", "Design choice", "points"),
        _row(f"{A}:BATTERY_BAD_PCT", "Battery counts as badly worn below", CHOSEN,
             "A second step for a battery that has lost close to half its charge.", "Judgement.", "Design choice", "%"),
        _row(f"{A}:BATTERY_BAD_PENALTY", "Points for a badly worn battery", CHOSEN,
             "Double the worn-battery cost.", "Judgement.", "Design choice", "points"),
        _row(f"{A}:AGE_LIMIT_YEARS", "Age counts against the score above", CHOSEN,
             "A round number, so only clearly old machines are affected.",
             "Age alone does not establish condition.", "Design choice", "years"),
        _row(f"{A}:AGE_PENALTY", "Points for age", CHOSEN,
             "Kept small on purpose: AfterLife's own drive data shows age is a weak predictor of failure "
             "(Spearman rho 0.18).", "Judgement.", "Design choice; The Argument, claim 01", "points"),
        _row(f"{A}:FAULT_PENALTY", "Points for a recognised fault", CHOSEN,
             "A fault named in 'Anything wrong?' makes the score more cautious. Only text that names a real "
             "fault counts (the multilingual fault lexicon), so 'asdf' costs nothing.",
             "One flat cost whatever the fault.", "Design choice", "points"),
        _row(f"{A}:GRADE_CUTOFFS", "Grade cut-offs", CHOSEN,
             "Equal 15-point bands, like school grades, to turn a number into a word.",
             "Interface categories, not scientific boundaries.", "Design choice"),
        _row(f"{A}:YEARS_SCALE", "Years at a perfect score", CHOSEN,
             "Turns the score into something people can picture: remaining years = score / 100 x 8.",
             "Not a lifespan model trained on real device lifetimes, hence 'estimated'.", "Design choice", "years"),
    ]},
    {"title": "The deep scan's measured score", "rows": [
        _row(f"{P}:DEEP_WEIGHTS", "Shares of the 100 points", CHOSEN,
             "Windows 11 readiness weighs most because it decides whether the machine keeps getting security "
             "updates; storage next, because a failing drive loses data; battery and age last. Each fact is "
             "counted once: the support date is applied separately, never inside these.",
             "Weights are judgement.", "Design choice", "points"),
        _row(f"{P}:DEEP_POINTS", "Points within each share", CHOSEN,
             "Full points mean no problem found; a reading that could not be taken scores about half, so "
             "a missing reading is neither a pass nor a fail.", "Judgement.", "Design choice", "points"),
        _row(f"{P}:DRIVE_WEAR_PCT", "Drive counts as heavily worn at", LOOKED_UP,
             "NVMe drives report the share of their rated write life used; at 90% little rated life is left.",
             "Rated life is the maker's warranty figure; drives often outlast it.", "NVMe specification (Percentage Used)", "%"),
        _row(f"{P}:DEEP_AGE_BANDS", "Age bands", CHOSEN,
             "Round years for new, mid-life, older and old.", "Judgement.", "Design choice", "years"),
    ]},
    {"title": "Security support", "rows": [
        _row(lambda: len(_app_data("device_support.json")["devices"]) + len(_app_data("device_support.json")["os"]),
             "Support end dates on file", LOOKED_UP,
             "Published end-of-support dates for device and operating-system releases.",
             "Must be kept current.", "endoflife.date; Microsoft's ESU programme", "releases"),
        _row(f"{D}:FULL_RISK_HORIZON_MONTHS", "Support-risk horizon", CHOSEN,
             "Beyond three years the security clock stops driving the decision; battery, storage or speed "
             "matter first. Also the length of Microsoft's paid ESU for organisations.",
             "A planning window, not a cybersecurity standard.", "Design choice", "months"),
        _row(f"{D}:RISK_FLOOR", "Lowest support risk", CHOSEN,
             "A long-supported device never looks risk-free.", "Judgement.", "Design choice"),
        _row(f"{D}:RISK_CAP", "Highest support risk before the end date", CHOSEN,
             "A soon-unsupported device never looks hopeless before its date.", "Judgement.", "Design choice"),
    ]},
    {"title": "Carbon payback", "rows": [
        _row(lambda: len(_app_data("grid_intensity.json")["countries"]), "Grid carbon intensity", LOOKED_UP,
             "Yearly average carbon per kWh of electricity for each country (India 670, world 458).",
             "A yearly national average; real-time grids vary.", "Our World in Data, 2025", "countries"),
        _row(lambda: _app_data("embodied_carbon.json")["classes"]["Laptop"]["median_kg"],
             "Carbon to make a laptop (median)", LOOKED_UP,
             "A model's own published figure where one exists, otherwise the median of 452 laptop "
             "declarations (middle half 244 to 360 kg).",
             "Manufacturers' methods differ, so good for orders of magnitude.", "Boavizta (manufacturer LCAs)", "kg CO2e"),
        _row(f"{G}:DEFAULT_EMBODIED_KG", "Fallback carbon to make a device", CHOSEN,
             "Only when no published figure or class median exists: mid-point of the 200 to 400 kg range in "
             "published laptop studies.", "Rough; labelled 'fallback estimate'.", "Design choice", "kg CO2e"),
        _row(f"{G}:DEFAULT_OLD_TDP_W", "Old processor power when unknown", LOOKED_UP,
             "The rated power of a typical 2019 performance laptop processor (Intel i7-9750H).",
             "Many older thin laptops use 15 W chips; the deep scan reads the real class.", "Intel specification", "W"),
        _row(f"{G}:DEFAULT_NEW_TDP_W", "Replacement processor power", LOOKED_UP,
             "The base power of a current mainstream thin-and-light processor (Intel i7-1260P). If the old "
             "chip is already lower, the replacement is assumed to be in the same class.",
             "Some new laptops are 15 W.", "Intel specification", "W"),
        _row(f"{C}:INTEL_SUFFIX_W", "Intel laptop power by model suffix", LOOKED_UP,
             "Intel's naming: U thin-and-light 15 W, P 28 W, H 45 W, HX 55 W, and so on.",
             "A class rating, not this machine's measured draw.", "Intel processor numbering", "W"),
        _row(f"{C}:INTEL_ULTRA_H_W", "Intel Core Ultra H power", LOOKED_UP,
             "Core Ultra H parts are rated 28 W base power.", "Class rating.", "Intel specification", "W"),
        _row(f"{C}:INTEL_DESKTOP_W", "Intel desktop power by suffix", LOOKED_UP,
             "Desktop parts: 65 W standard, 35 W T, 125 W K.", "Class rating; older generations differ.",
             "Intel specification", "W"),
        _row(f"{C}:AMD_SUFFIX_W", "AMD laptop power by suffix", LOOKED_UP,
             "AMD's naming: U 15 W, HS 35 W, H 45 W, HX 55 W.", "Class rating.", "AMD processor naming", "W"),
        _row(f"{C}:AMD_DESKTOP_W", "AMD desktop power by suffix", LOOKED_UP,
             "Desktop parts: 65 W standard and G, 105 W X.", "Class rating; models vary.", "AMD specification", "W"),
        _row(f"{G}:SCENARIO_HOURS", "Hours a day: light, typical, heavy", CHOSEN,
             "A metered study of home laptops found 4.8 hours a day on average, so 'light' is close to "
             "measured use and 'typical' (a full working day) is deliberately heavier. More hours make "
             "replacement look better, so if keeping still wins, it wins honestly.",
             "Scenarios, not your measured use.", "Design choice; LBNL field-metering study", "h/day"),
        _row(f"{G}:DAYS_PER_YEAR", "Days of use a year", CHOSEN,
             "Working days in a year.", "Ignores weekend use.", "Design choice", "days"),
        _row(f"{G}:HOURS_PER_YEAR", "Hours a year for 'typical'", CHOSEN,
             "8 hours x 250 days.", "As above.", "Design choice", "hours"),
        _row(f"{G}:USE_SCENARIO", "Which scenario the usage answer picks", CHOSEN,
             "Gaming and editing keep a machine busy for long sessions; everyday use and coding are a working day.",
             "Judgement.", "Design choice"),
        _row(f"{G}:LOAD_FACTOR", "Average draw as a share of rated power", CHOSEN,
             "With the overhead below, average draw is 0.64 x rated power: 58 kWh a year for the old laptop "
             "and 36 for the new, inside the 31 (median) to 75 (mean) kWh measured in the field study.",
             "An engineering simplification.", "Design choice; LBNL field-metering study"),
        _row(f"{G}:SYSTEM_OVERHEAD", "Whole laptop vs processor alone", CHOSEN,
             "Screen, chipset and power losses on top of the processor.", "Simplification.", "Design choice", "x"),
        _row(f"{G}:_MIN_CREDIBLE_INTENSITY", "Cleanest grid treated as real", CHOSEN,
             "Below this a country's figure is a reporting gap, and dividing by it would print a meaningless "
             "number of years; the card says 'never repays' instead.", "Judgement.", "Design choice", "gCO2e/kWh"),
    ]},
    {"title": "Keep, repair, sell or recycle", "rows": [
        _row(f"{W}:GRADE_FIT", "Fit of each option by grade", CHOSEN,
             "A stated policy: better devices lean towards keep or sell, worse ones towards repurpose or recycle.",
             "Relative fit scores, not probabilities.", "Design choice"),
        _row(f"{W}:WIN11_PRIMARY_PENALTY", "Keep-as-primary cut when Windows 11 is out of reach", CHOSEN,
             "A machine that cannot reach Windows 11 is a weaker everyday device.", "Judgement.", "Design choice", "points"),
        _row(f"{W}:HARDENING_IF_FIXABLE", "Hardening fit when a firmware switch unlocks Windows 11", CHOSEN,
             "One setting away from Windows 11, hardening becomes the clear move.", "Judgement.", "Design choice"),
        _row(f"{W}:HARDENING_IF_BLOCKED", "Hardening fit when Windows 11 is permanently blocked", CHOSEN,
             "Hardening stays a live option.", "Judgement.", "Design choice"),
        _row(f"{W}:ALSO_VIABLE_MIN", "Lowest fit labelled 'also viable'", CHOSEN,
             "The same as grade C's lower edge.", "Judgement.", "Design choice"),
    ]},
    {"title": "Usage fit and repair outlook", "rows": [
        _row(f"{PE}:TIERS", "Workload tiers per use", CHOSEN,
             "Reference points from published software requirements (Adobe, DaVinci Resolve, typical "
             "Steam ranges): cores, memory and graphics for each level of work.",
             "Chosen, not learned; the sample behind them is small.", "Published software requirements"),
        _row(f"{PE}:RAM_GROWTH_GB_PER_YEAR", "Memory requirements grow by", LEARNED,
             "A straight-line fit of recommended memory against release year for 77 popular Steam titles.",
             "Popular titles only, so a direction, not a date.",
             "Steam store data (scripts/fit_requirement_growth.py)", "GB/year"),
        _row(f"{PE}:GPU_TIER_YEARS", "Years per graphics tier step", LEARNED,
             "The same fit for recommended graphics tier.", "As above.",
             "Steam store data (scripts/fit_requirement_growth.py)", "years"),
        _row(lambda: _value(f"{PE}:_BENCH").get("gpu_tier_cutoffs"), "Graphics tier cut-offs (benchmark score)", LEARNED,
             "The 25th, 60th and 85th percentile of about 280 GPUs' Blender benchmark scores. A dedicated card "
             "always counts as at least entry level, because Blender ranks render speed.",
             "Benchmark submitters lean towards creative power users.",
             "Blender Open Data (scripts/build_persona_tiers.py)"),
        _row(f"{PE}:RAM_TOLERANCE", "Memory tolerance", CHOSEN,
             "Windows reports usable memory, slightly under the size sold (16 GB shows as about 15.8).",
             "None in practice: memory sizes double.", "Design choice"),
        _row(f"{PE}:BROWSER_RAM_CAP", "Browser memory reading caps at", LOOKED_UP,
             "Chrome reports memory rounded and capped at 8 GB, so 8 means '8 or more'.",
             "Only the deep scan reads the real amount.", "Device Memory API specification", "GB"),
        _row(f"{U}:REPLACED_BATTERY_HEALTH", "A new battery modelled at", CHOSEN,
             "A fresh cell, not 100%: no replacement part delivers that.", "Judgement.", "Design choice", "%"),
        _row(f"{U}:MIN_USEFUL_RAM_GB", "Smallest memory upgrade worth naming", CHOSEN,
             "Anything smaller is a rounding artefact, not a purchase.", "Judgement.", "Design choice", "GB"),
        _row(lambda: _app_data("repair_evidence.json")["min_n"], "Fewest repair records to show a rate", CHOSEN,
             "A fault needs at least this many records before its repair rate is shown.",
             "Rates from 50 records are still rough.", "Design choice (scripts/build_repair_evidence.py)", "records"),
    ]},
    {"title": "Resale estimate", "rows": [
        _row(f"{PR}:YEARLY_LOSS", "Value lost per year, by device type", CHOSEN,
             "Typical depreciation for used electronics; phones lose value fastest.",
             "There is no public dataset of used computer prices by condition to learn these from.", "Design choice"),
        _row(f"{PR}:DEFAULT_YEARLY_LOSS", "Value lost per year, other devices", CHOSEN,
             "The laptop rate.", "As above.", "Design choice"),
        _row(f"{PR}:GRADE_FACTOR", "Share of value kept at each grade", CHOSEN,
             "Mirrors refurbishers' A/B/C/D grading steps.", "As above.", "Design choice"),
        _row(f"{PR}:COSMETIC_FACTOR", "Scratches and dents (your own answer)", CHOSEN,
             "The scan cannot see the outside of the device, so this is the owner's answer, kept separate.",
             "Unverified.", "Design choice"),
        _row(f"{PR}:MIN_AGE_FACTOR", "Lowest share of the new price", CHOSEN,
             "A working device never falls to nothing.", "Judgement.", "Design choice"),
        _row(f"{PR}:RANGE", "Range either side", CHOSEN,
             "Shown as a range, never one confident number.", "Judgement.", "Design choice"),
    ]},
]

#: Module-level constants in the audited modules that are deliberately not rows,
#: each with its reason. Anything else numeric must have a row (see the test).
NOT_ASSUMPTIONS = {
    "afterlife.persona:GROWTH": "the loaded file; its two rates are rows",
    "afterlife.persona:_BENCH": "the loaded benchmark file; its cut-offs are a row",
    "afterlife.pricing:GRADE_LADDER": "the order of the grades, not a number",
    "afterlife.persona:_GPU_NAMES": "the benchmark file re-sorted for matching",
    "afterlife.assessment:_RULES": "the scoring constants above, gathered so the sensitivity analysis can vary them",
}

AUDITED_MODULES = [A, D, G, C, W, PE, U, PR]
AUDITED_PREFIXES = {P: ("DEEP_", "DRIVE_")}


def _display(v: Any) -> str:
    if isinstance(v, dict):
        return " · ".join(f"{k or 'no suffix'} {_display(x)}" for k, x in v.items())
    if isinstance(v, (list, tuple)):
        if v and isinstance(v[0], dict) and "name" in v[0]:
            return " · ".join(f"{t['name']}: {t.get('cores')}+ cores, {t.get('ram_gb')}+ GB" for t in v)
        return ", ".join(_display(x) for x in v)
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def table() -> dict[str, Any]:
    """The table as the page shows it, values read from the code now."""
    groups = []
    for g in GROUPS:
        rows = []
        for r in g["rows"]:
            v = _value(r["ref"])
            rows.append({k: r[k] for k in ("name", "kind", "why", "limit", "source", "unit")}
                        | {"value": _display(v), "code": r["ref"] if isinstance(r["ref"], str) else "data file"})
        groups.append({"title": g["title"], "rows": rows})
    counts: dict[str, int] = {}
    for g in groups:
        for r in g["rows"]:
            counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return {"groups": groups, "counts": counts}
