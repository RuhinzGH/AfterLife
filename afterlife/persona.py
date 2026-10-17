"""What the device is used for, and whether it is up to that work.

Two ways to know the use:
  * Instant scan: a browser cannot see installed software, so the user picks
    from four uses (general, gaming, coding, video/photo editing). Labelled
    "self-reported".
  * Deep scan: the collector reports which categories of a short keyword list of
    programs are installed (never the program list itself), the number of Steam
    games and WSL distributions. classify_signals() turns that into a use.
    Labelled "auto-detected".

The fit itself compares the device's cores, memory and graphics with a ladder of
workload tiers per use. Where the numbers come from:
  * Tier thresholds: chosen by hand from published requirements (Adobe,
    DaVinci Resolve and typical Steam AAA ranges). Reference points, not learned.
  * Graphics tier: matched against about 280 GPUs benchmarked in Blender Open
    Data, cut at the 25th/60th/85th percentile of their scores
    (scripts/build_persona_tiers.py -> models/persona_tiers.json). GPUs the
    dataset does not list fall back to a keyword rule.
  * How fast requirements grow: a straight-line fit over Steam's recommended
    requirements by release year (scripts/fit_requirement_growth.py ->
    models/requirement_growth.json).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
_TIERS_PATH = ROOT / "models" / "persona_tiers.json"
_GROWTH_PATH = ROOT / "models" / "requirement_growth.json"

PERSONAS = ["general", "gamer", "coder", "editor"]
LABELS = {"general": "General use", "gamer": "Gaming", "coder": "Coding",
          "editor": "Video/photo editing"}
_USE_WORD = {"general": "everyday", "gamer": "gaming", "coder": "coding", "editor": "editing"}

# Each tier: minimum cores / RAM / GPU tier (0 = integrated, 1 = entry discrete,
# 2 = mid discrete, 3 = high-end discrete) to run that workload comfortably.
TIERS: dict[str, list[dict[str, Any]]] = {
    "gamer": [
        {"name": "Light / esports titles", "cores": 4, "ram_gb": 8, "gpu_tier": 1},
        {"name": "Mainstream AAA", "cores": 6, "ram_gb": 16, "gpu_tier": 2},
        {"name": "Cutting-edge AAA", "cores": 8, "ram_gb": 32, "gpu_tier": 3},
    ],
    "coder": [
        {"name": "Scripting & web dev", "cores": 4, "ram_gb": 8, "gpu_tier": 0},
        {"name": "Multi-service / Docker", "cores": 6, "ram_gb": 16, "gpu_tier": 0},
        {"name": "VMs, containers & ML work", "cores": 8, "ram_gb": 32, "gpu_tier": 1},
    ],
    "editor": [
        {"name": "Photo editing", "cores": 4, "ram_gb": 16, "gpu_tier": 1},
        {"name": "1080p video editing", "cores": 6, "ram_gb": 16, "gpu_tier": 2},
        {"name": "4K & color grading", "cores": 8, "ram_gb": 32, "gpu_tier": 3},
    ],
    "general": [
        {"name": "Browsing & office work", "cores": 2, "ram_gb": 8, "gpu_tier": 0},
        {"name": "Heavy multitasking", "cores": 4, "ram_gb": 16, "gpu_tier": 0},
    ],
}

#: Windows reports *usable* memory, a little under the nominal size (a 16 GB
#: machine reports about 15.8). Memory is sold in sizes that double, so a 5%
#: tolerance can never promote a genuinely smaller configuration.
RAM_TOLERANCE = 0.95

#: Chrome reports navigator.deviceMemory rounded and capped at 8 GB, so an
#: instant-scan reading of 8 means "8 GB or more".
BROWSER_RAM_CAP = 8


def _load(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


_BENCH = _load(_TIERS_PATH, {"gpu_lookup": {}})
GROWTH = _load(_GROWTH_PATH, {})
RAM_GROWTH_GB_PER_YEAR: float | None = GROWTH.get("ram_gb_per_year")
GPU_TIER_YEARS: float | None = GROWTH.get("gpu_tier_years")


def _norm(name: str) -> str:
    """Lower-case, without trademark marks and the browser's ANGLE wrapper, so
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Laptop GPU (0x...) Direct3D11...)"
    and "NVIDIA GeForce RTX 3060" can meet."""
    s = name.lower()
    s = re.sub(r"\((r|tm)\)|®|™", " ", s)
    s = re.sub(r"0x[0-9a-f]+|direct3d\S*|vs_\S+|ps_\S+|d3d\S*", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


_GPU_NAMES = sorted(((_norm(k), v["tier"]) for k, v in _BENCH.get("gpu_lookup", {}).items()),
                    key=lambda kv: -len(kv[0]))


def _bench_tier(gpu: str) -> int | None:
    """Tier of the longest benchmarked GPU name found inside this one.

    Longest first, so "rtx 3060 ti" is not read as "rtx 3060". Only whole-word
    containment counts; there is no similarity guess, because a 3060 and a 3070
    are one character apart and two tiers apart.
    """
    s = f" {_norm(gpu)} "
    for known, tier in _GPU_NAMES:
        if known and f" {known} " in s:
            return tier
    return None


def _dedicated(s: str) -> bool:
    return any(k in s for k in ("nvidia", "geforce", "quadro", "radeon rx", "radeon pro", " arc a"))


def gpu_tier(gpu: str | None) -> tuple[int, str]:
    """(tier, how it was found): "benchmark", "keyword" or "unknown"."""
    if not gpu:
        return 0, "unknown"
    s = gpu.lower()
    real = _bench_tier(gpu)
    if real is not None:
        # Blender's percentiles rank render speed among cards people benchmark,
        # which puts older dedicated cards (a GTX 1650, even a GTX 1080) in the
        # bottom quarter. Tier 0 here means built-in graphics, so a dedicated
        # card never ranks below entry level.
        return (max(real, 1) if _dedicated(s) else real), "benchmark"
    if any(k in s for k in ("rtx 40", "rtx 50", "rx 7", "rx 9")):
        return 3, "keyword"
    if any(k in s for k in ("rtx 30", "rtx 20", "gtx 16", "rx 6", "rx 5")):
        return 2, "keyword"
    if any(k in s for k in ("gtx", "radeon rx", "rx ")):
        return 1, "keyword"
    return 0, "keyword"   # integrated graphics (Intel UHD/Iris, Radeon Vega, Apple) or unrecognised


def classify_signals(signals: dict[str, Any] | None) -> dict[str, Any]:
    """Deep-scan detection from the collector's categorised matches."""
    signals = signals or {}
    gamer = list(signals.get("gamer_matches") or [])
    coder = list(signals.get("coder_matches") or [])
    editor = list(signals.get("editor_matches") or [])
    steam_games = int(signals.get("steam_game_count") or 0)
    wsl = int(signals.get("wsl_distro_count") or 0)
    scores = {
        "gamer": len(gamer) + (steam_games >= 5) + (steam_games >= 20),
        "coder": len(coder) + (wsl > 0),
        "editor": len(editor),
    }
    best = max(scores, key=scores.get)
    persona = best if scores[best] > 0 else "general"
    reasons = {"gamer": gamer, "coder": coder, "editor": editor}.get(persona, [])
    if persona == "gamer" and steam_games:
        reasons = reasons + [f"{steam_games} Steam games"]
    if persona == "coder" and wsl:
        reasons = reasons + [f"{wsl} WSL distribution{'s' if wsl != 1 else ''}"]
    return {"persona": persona, "reasons": reasons, "strength": scores.get(persona, 0)}


def _meets(cores: int, ram: float, g: int, tier: dict[str, Any]) -> bool:
    return cores >= tier["cores"] and ram >= tier["ram_gb"] * RAM_TOLERANCE and g >= tier["gpu_tier"]


def assess_fit(cores: int | None, ram_gb: float | None, gpu: str | None, persona: str | None,
               source: str = "measured", reasons: list[str] | None = None) -> dict[str, Any] | None:
    """Compare the device's specs with the ladder of tiers for its use.

    `source` is "self-reported" (instant scan, the user picked the use) or
    "auto-detected" (deep scan). Returns None when cores or memory are unknown:
    a fit with no specs would be a guess.
    """
    persona = persona if persona in TIERS else "general"
    if not cores or not ram_gb:
        return None
    browser = source == "self-reported"
    g, gpu_basis = gpu_tier(gpu)
    tiers = TIERS[persona]
    met = [t for t in tiers if _meets(cores, ram_gb, g, t)]
    current = met[-1] if met else None
    nxt = tiers[len(met)] if len(met) < len(tiers) else None

    gap = []
    if nxt:
        if cores < nxt["cores"]:
            gap.append(f"{nxt['cores']}+ CPU cores (has {cores})")
        if ram_gb < nxt["ram_gb"] * RAM_TOLERANCE:
            shown = f"{ram_gb:g}+" if browser and ram_gb >= BROWSER_RAM_CAP else f"{ram_gb:g}"
            gap.append(f"{nxt['ram_gb']}+ GB memory (shows {shown})")
        if g < nxt["gpu_tier"]:
            gap.append("stronger graphics")

    # How long the device keeps meeting the tier it meets today, as that tier's
    # requirements rise at the measured rates. Headroom is whichever runs out
    # first: spare memory, or spare graphics tiers (only where the tier needs a
    # discrete GPU at all; for an integrated-graphics tier the GPU is not a limit).
    years = None
    if current and RAM_GROWTH_GB_PER_YEAR:
        options = [max(0.0, ram_gb - current["ram_gb"]) / RAM_GROWTH_GB_PER_YEAR]
        if current["gpu_tier"] > 0 and GPU_TIER_YEARS:
            options.append(max(0, g - current["gpu_tier"]) * GPU_TIER_YEARS)
        years = round(min(options), 1)
    # A browser's 8 GB means "8 or more", so the memory headroom is unknown, not zero.
    ram_capped = browser and ram_gb >= BROWSER_RAM_CAP
    if ram_capped:
        years = None

    use = _USE_WORD[persona]
    if nxt is None and current:
        verdict = f"Handles the top {use} tier checked here ({current['name']})."
    elif current is None:
        verdict = f"Falls short of the lightest {use} tier checked here. It would need {', '.join(gap)}."
    else:
        verdict = f"Handles {current['name']}. Short of {nxt['name']} on: {', '.join(gap)}."

    if not current:
        timeline = None
    elif years is None:
        timeline = None
    elif years == 0:
        timeline = (f"It meets {current['name']} with no spare memory, so it will start to fall "
                    f"behind as that kind of work asks for more.")
    else:
        timeline = (f"At the rate recommended requirements have grown, it should keep meeting "
                    f"{current['name']} for about {years:g} more years.")

    caveats = []
    if browser:
        caveats.append("A browser counts logical processors (threads), which can be twice the "
                       "number of physical cores.")
        if ram_capped:
            caveats.append(f"Browsers report memory only up to {BROWSER_RAM_CAP} GB, so this machine "
                           f"may have more; the deep scan reads the real amount.")
    if gpu_basis == "keyword":
        caveats.append("This graphics chip is not in the benchmark list, so its tier comes from its name.")

    return {
        "persona": persona,
        "label": LABELS[persona],
        "source": source,
        "reasons": reasons or [],
        "current_tier": current["name"] if current else None,
        "next_tier": nxt["name"] if nxt else None,
        "meets_top_tier": nxt is None,
        "tiers": [{**t, "met": t in met} for t in tiers],
        "gap": gap,
        "specs": {"cores": cores, "ram_gb": ram_gb, "gpu": gpu, "gpu_tier": g, "gpu_basis": gpu_basis},
        "years_of_headroom": years,
        "verdict": verdict,
        "timeline": timeline,
        "caveats": caveats,
        "growth": {"ram_gb_per_year": RAM_GROWTH_GB_PER_YEAR, "gpu_tier_years": GPU_TIER_YEARS},
    }
