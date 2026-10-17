r"""Fit how fast game requirements grow, from the Steam pull.

Reads data/raw/steam_requirements.json (made by scripts/fetch_steam_requirements.py)
and fits a straight line of each title's *recommended* requirement against its
release year:

  * RAM: GB of recommended memory added per year;
  * GPU: recommended GPU tier (0-3) per year, reported as years per tier step.

The usage-fit card (afterlife/persona.py) uses these two rates to say how long a
machine keeps meeting the workload tier it meets today. Written to
models/requirement_growth.json, which the Dockerfile ships with the API.

The sample is the SteamSpy top-100 lists (popular titles, about two decades of
release years), not the whole catalogue, so the rates are directional.

    venv\Scripts\python scripts\fit_requirement_growth.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "steam_requirements.json"
OUT = ROOT / "models" / "requirement_growth.json"


def slope(points: list[tuple[float, float]]) -> float:
    xy = np.array(points, dtype=float)
    return float(np.polyfit(xy[:, 0], xy[:, 1], 1)[0])


def main() -> None:
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    ram = [(r["year"], r["rec_ram_gb"]) for r in rows if r.get("rec_ram_gb")]
    # Only titles whose recommended GPU line was actually parsed: a missing line
    # would otherwise count as "integrated graphics" and drag the slope down.
    gpu = [(r["year"], r["rec_gpu_tier"]) for r in rows if r.get("rec_gpu_text")]
    ram_rate = slope(ram)
    gpu_rate = slope(gpu)
    out = {
        "source": "Steam store appdetails API (recommended PC requirements), titles from SteamSpy top-100 lists",
        "titles": len(rows),
        "ram_gb_per_year": round(ram_rate, 2),
        "ram_titles": len(ram),
        "ram_years": [int(min(y for y, _ in ram)), int(max(y for y, _ in ram))],
        "gpu_tier_years": round(1 / gpu_rate, 1) if gpu_rate > 0 else None,
        "gpu_titles": len(gpu),
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
