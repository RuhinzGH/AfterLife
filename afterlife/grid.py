"""Is replacing this device actually worth the carbon, on THIS grid?

THE ARGUMENT, AND WHY IT NEEDS A GRID
-------------------------------------
Afterlife's sustainability claim is not "reuse always wins" -- that is the naive
version, and it is not always true. Keeping an older machine costs operational
carbon, because it draws more power for the same work. Replacing it costs
embodied carbon up front, roughly an order of magnitude more than a year of use.
Which one wins depends on how dirty the electricity is.

On France's grid the operational penalty is so small that replacing effectively
never repays. On a coal-heavy grid it repays much faster. Quoting one global
break-even hides exactly the variable that decides the answer, and quoting the
dirtiest-grid figure -- which the research page does -- is the conservative
choice but still not the user's.

scripts/carbon_tradeoff.py has computed this properly since July, against five
hardcoded countries, as a research script nothing imported. This makes it a
module the product can call, for the country geo.py already detects and with the
device's own declared embodied carbon where embodied_carbon.py has it.

WHAT IS MEASURED AND WHAT IS AUTHORED
-------------------------------------
Measured:  grid intensity per country (Our World in Data), and the device's
           embodied carbon where the manufacturer published an LCA.
Authored:  the duty cycle below -- hours per year, load factor, and the
           whole-system overhead over CPU TDP. These are the same judgement
           calls carbon_tradeoff.py has always made, carried over unchanged and
           flagged here rather than presented as measurements.

So the break-even is a modelled figure with measured inputs, and `basis` on
every response says which parts were which.
"""
from __future__ import annotations

import json
import pathlib
from functools import lru_cache
from typing import Any

DATA = pathlib.Path(__file__).resolve().parents[1] / "app_data" / "grid_intensity.json"

# --- the duty cycle. Authored, not fitted; unchanged from carbon_tradeoff.py ---
HOURS_PER_YEAR = 8 * 250     # 8h/day, 250 working days
LOAD_FACTOR = 0.40           # average draw as a fraction of TDP under office load
SYSTEM_OVERHEAD = 1.6        # whole laptop vs CPU alone: display, chipset, losses

#: Fallback embodied figure when the device has no declared LCA and no class
#: median is available. Mid-point of the 200-400 kg range in published laptop
#: LCAs; only used when nothing better exists, and `basis` says so.
DEFAULT_EMBODIED_KG = 300.0

#: A grid this clean is a reporting artifact, not a grid -- several small
#: countries report ~0 because almost nothing is measured, and dividing by it
#: yields an infinite break-even that looks like a finding. Below this the
#: answer is "replacement never repays", stated in words rather than as a number.
_MIN_CREDIBLE_INTENSITY = 5.0


@lru_cache(maxsize=1)
def _load() -> dict:
    if not DATA.exists():
        return {}
    with DATA.open(encoding="utf-8") as fh:
        return json.load(fh)


def intensity(country: str | None) -> dict[str, Any] | None:
    """Grid carbon intensity for a country, falling back to the world average.

    `basis` distinguishes the two, because "your grid" and "the world's grid"
    are different claims and the second must not be presented as the first.
    """
    data = _load()
    if not data:
        return None

    rec = (data.get("countries") or {}).get((country or "").upper())
    if rec:
        return {"gco2_kwh": rec["gco2_kwh"], "year": rec["year"],
                "region": rec["name"], "basis": "country",
                "source": data.get("source"), "unit": data.get("unit")}

    world = data.get("world")
    if not world:
        return None
    return {"gco2_kwh": world["gco2_kwh"], "year": world["year"],
            "region": "World", "basis": "world",
            "source": data.get("source"), "unit": data.get("unit")}


def annual_kwh(tdp_w: float) -> float:
    """Yearly electricity for a machine of this TDP, on the duty cycle above."""
    return tdp_w * LOAD_FACTOR * SYSTEM_OVERHEAD * HOURS_PER_YEAR / 1000.0


def break_even(
    country: str | None,
    embodied_kg: float | None = None,
    old_tdp_w: float = 45.0,
    new_tdp_w: float = 28.0,
    embodied_basis: str | None = None,
) -> dict[str, Any] | None:
    """Years of use before replacing repays its own manufacturing carbon.

    Returns None only when no grid data is loaded at all. A grid too clean for
    replacement ever to repay is a real answer, not a missing one, and comes
    back with `repays=False`.
    """
    grid = intensity(country)
    if not grid:
        return None

    embodied = embodied_kg if (embodied_kg and embodied_kg > 0) else DEFAULT_EMBODIED_KG
    saved_kwh = annual_kwh(old_tdp_w) - annual_kwh(new_tdp_w)

    where = _where(grid)

    # A replacement that is no more efficient saves nothing, so its embodied
    # cost is never repaid. Possible with a like-for-like swap, and the honest
    # answer is not a very large number of years -- it is "never". The same
    # branch catches a grid reported as implausibly clean, where the division
    # would produce a number that looks like a finding and is an artifact.
    if saved_kwh <= 0 or grid["gco2_kwh"] < _MIN_CREDIBLE_INTENSITY:
        return {
            "repays": False,
            "grid": grid,
            "embodied_kg": round(embodied, 1),
            "embodied_basis": embodied_basis or ("declared" if embodied_kg else "default"),
            "annual_saving_kg": round(max(0.0, saved_kwh) * grid["gco2_kwh"] / 1000.0, 1),
            "headline": (
                f"{where}, replacing this device would never repay the carbon spent "
                f"building the replacement."),
            "assumptions": _assumptions(old_tdp_w, new_tdp_w),
        }

    annual_saving_kg = saved_kwh * grid["gco2_kwh"] / 1000.0
    years = embodied / annual_saving_kg

    return {
        "repays": True,
        "years": round(years, 1),
        "grid": grid,
        "embodied_kg": round(embodied, 1),
        "embodied_basis": embodied_basis or ("declared" if embodied_kg else "default"),
        "annual_saving_kg": round(annual_saving_kg, 1),
        "annual_kwh_saved": round(saved_kwh, 1),
        "headline": (
            f"{where} ({grid['gco2_kwh']:.0f} gCO₂e/kWh), a replacement would need about "
            f"{years:.1f} years of use to repay the {embodied:.0f} kg of carbon "
            f"spent building it."),
        "assumptions": _assumptions(old_tdp_w, new_tdp_w),
    }


def _where(grid: dict[str, Any]) -> str:
    """Name the grid in a sentence.

    The world average needs different wording from a country: "On World's grid"
    is not English, and more importantly it reads as though it were the user's
    own grid when it is the fallback for not knowing where they are.
    """
    if grid["basis"] == "world":
        return "On the world-average grid"
    return f"On {grid['region']}'s grid"


def _assumptions(old_tdp_w: float, new_tdp_w: float) -> dict[str, Any]:
    """Stated, not buried. Every one of these is a judgement call."""
    return {
        "hours_per_year": HOURS_PER_YEAR,
        "load_factor": LOAD_FACTOR,
        "system_overhead": SYSTEM_OVERHEAD,
        "old_tdp_w": old_tdp_w,
        "new_tdp_w": new_tdp_w,
        "note": "Duty cycle is authored, not measured: 8 hours a day, 250 days a "
                "year, averaging 40% of TDP, with a 1.6x whole-system multiplier "
                "over the CPU alone. Grid intensity and embodied carbon are "
                "measured. Change the duty cycle and the break-even moves.",
    }
