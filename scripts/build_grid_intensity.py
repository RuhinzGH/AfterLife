"""Pull per-country electricity carbon intensity into a runtime artifact.

Source: Our World in Data, "Carbon intensity of electricity generation"
(gCO2e per kWh), which Afterlife already cites for the carbon break-even.

WHY THIS EXISTS
---------------
scripts/carbon_tradeoff.py computes the honest version of the sustainability
argument -- keeping an old laptop costs operational carbon, replacing it costs
embodied carbon, and which one wins depends on how dirty the grid is. But it
carried a hardcoded dict of five countries and only ever ran as a research
script, so the product shipped one global break-even figure for everybody.

The break-even genuinely differs by an order of magnitude between grids. On
France's it is effectively never worth replacing; on a coal-heavy grid the
efficiency gap repays much faster. Afterlife already detects the user's country
for the repair-rights and evidence work, so it can answer this for the grid the
device is actually plugged into rather than for an average nobody lives on.

Keyed by ISO 3166-1 alpha-2 to match afterlife/geo.py, joined to OWID on
country name because OWID publishes alpha-3.

    python scripts/build_grid_intensity.py
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

SRC = ("https://ourworldindata.org/grapher/carbon-intensity-electricity.csv"
       "?v=1&csvType=full&useColumnShortNames=true")
APP = ROOT / "app_data"
OUT = APP / "grid_intensity.json"

#: OWID entity names that differ from the geo table's. Only the ones that
#: actually collide -- a longer list would be guesswork.
_ALIAS = {
    "united states": "united states of america",
    "south korea": "korea republic of",
    "north korea": "korea democratic people's republic of",
    "russia": "russian federation",
    "iran": "iran islamic republic of",
    "vietnam": "viet nam",
    "syria": "syrian arab republic",
    "tanzania": "tanzania united republic of",
    "moldova": "moldova republic of",
    "bolivia": "bolivia plurinational state of",
    "venezuela": "venezuela bolivarian republic of",
    "laos": "lao people's democratic republic",
    "brunei": "brunei darussalam",
    "cape verde": "cabo verde",
    "czechia": "czech republic",
    "turkey": "türkiye",
    "democratic republic of congo": "congo the democratic republic of the",
    "congo": "congo",
    "hong kong": "hong kong",
    "macao": "macao",
    "taiwan": "taiwan province of china",
}


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = _ALIAS.get(s, s)
    return re.sub(r"[^a-z]", "", s)


def main() -> None:
    print(f"GET {SRC}")
    r = requests.get(SRC, headers={"User-Agent": "Afterlife-research/0.1"}, timeout=120)
    r.raise_for_status()

    rows = list(csv.DictReader(io.StringIO(r.text)))
    if not rows:
        raise SystemExit("OWID returned no rows -- refusing to write")

    geo = json.loads((APP / "geo_lookup.json").read_text(encoding="utf-8"))["countries"]
    by_name = {_norm(v["name"]): code for code, v in geo.items()}

    # Latest year per entity. OWID carries partial years and aggregates
    # ("World", "Europe", "High-income countries") in the same file; the
    # aggregates are kept deliberately, because "World" is the honest fallback
    # for a user whose country is unknown or unmatched.
    latest: dict[str, dict] = {}
    for row in rows:
        try:
            year = int(row["year"])
            value = float(row["co2_intensity__gco2_kwh"])
        except (KeyError, TypeError, ValueError):
            continue
        entity = row.get("entity", "")
        prev = latest.get(entity)
        if prev is None or year > prev["year"]:
            latest[entity] = {"year": year, "gco2_kwh": round(value, 1)}

    out_countries: dict[str, dict] = {}
    unmatched: list[str] = []
    for entity, rec in latest.items():
        code = by_name.get(_norm(entity))
        if not code:
            unmatched.append(entity)
            continue
        out_countries[code] = {"name": entity, **rec}

    world = latest.get("World")
    if not world:
        raise SystemExit("no World row -- refusing to write a file with no fallback")

    payload = {
        "source": "Our World in Data — Carbon intensity of electricity generation",
        "url": "https://ourworldindata.org/grapher/carbon-intensity-electricity",
        "unit": "gCO2e per kWh",
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "note": "Latest available year per country; grids decarbonise, so a figure "
                "two or three years old understates how clean a grid is today.",
        "world": world,
        "countries": dict(sorted(out_countries.items())),
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    years = sorted({c["year"] for c in out_countries.values()})
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    print(f"  {len(out_countries)} countries matched to ISO alpha-2")
    print(f"  years present: {years[0]}–{years[-1]}")
    print(f"  World: {world['gco2_kwh']} gCO2e/kWh ({world['year']})")
    cleanest = min(out_countries.items(), key=lambda kv: kv[1]["gco2_kwh"])
    dirtiest = max(out_countries.items(), key=lambda kv: kv[1]["gco2_kwh"])
    print(f"  cleanest: {cleanest[1]['name']} {cleanest[1]['gco2_kwh']}")
    print(f"  dirtiest: {dirtiest[1]['name']} {dirtiest[1]['gco2_kwh']}")
    # Aggregates and territories with no alpha-2 entry are expected; printing
    # the count keeps a silent coverage collapse from going unnoticed.
    print(f"  {len(unmatched)} entities unmatched (aggregates and regions): "
          f"{', '.join(sorted(unmatched)[:6])}...")


if __name__ == "__main__":
    main()
