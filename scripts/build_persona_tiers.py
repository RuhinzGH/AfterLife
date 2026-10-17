"""Turn the raw Blender Open Data pull into a small lookup artifact: real
device names -> a tier (0-3) computed from real percentile cutoffs in the
actual score distribution, instead of a hand-picked keyword bucket.

This is the "train once, ship the artifact" pattern already used for
lifecycle_model.joblib -- afterlife/persona.py loads the small JSON output
at import time and does a fuzzy name match against it, falling back to the
old keyword heuristic only for hardware this dataset doesn't cover.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "blender_opendata.json"
# models/, not data/ -- the Dockerfile only COPYs models/ into the deployed
# container (data/ is raw/intermediate only), same convention as the existing
# lifecycle_model.joblib.
OUT = ROOT / "models" / "persona_tiers.json"
OUT.parent.mkdir(parents=True, exist_ok=True)


def tier_cutoffs(scores: list[float]) -> tuple[float, float, float]:
    """25th/60th/85th percentile score -> boundaries for tiers 1/2/3."""
    s = sorted(scores)
    n = len(s)
    def pct(p): return s[min(int(n * p), n - 1)]
    return pct(0.25), pct(0.60), pct(0.85)


def tier_for(score: float, cuts: tuple[float, float, float]) -> int:
    lo, mid, hi = cuts
    if score >= hi:
        return 3
    if score >= mid:
        return 2
    if score >= lo:
        return 1
    return 0


def main() -> None:
    d = json.loads(SRC.read_text())
    gpu_rows, cpu_rows = d["gpu"], d["cpu"]

    gpu_cuts = tier_cutoffs([r[1] for r in gpu_rows])
    cpu_cuts = tier_cutoffs([r[1] for r in cpu_rows])
    print(f"GPU tier cutoffs (25/60/85th pct): {[round(c, 1) for c in gpu_cuts]}")
    print(f"CPU tier cutoffs (25/60/85th pct): {[round(c, 1) for c in cpu_cuts]}")

    gpu_lookup = {name.lower(): {"score": round(score, 1), "tier": tier_for(score, gpu_cuts)}
                  for name, score, _n in gpu_rows}
    cpu_lookup = {name.lower(): {"score": round(score, 1), "tier": tier_for(score, cpu_cuts)}
                  for name, score, _n in cpu_rows}

    out = {
        "source": "Blender Open Data (opendata.blender.org), blender_version 5.1.1",
        "gpu_tier_cutoffs": {"t1": round(gpu_cuts[0], 1), "t2": round(gpu_cuts[1], 1), "t3": round(gpu_cuts[2], 1)},
        "cpu_tier_cutoffs": {"t1": round(cpu_cuts[0], 1), "t2": round(cpu_cuts[1], 1), "t3": round(cpu_cuts[2], 1)},
        "gpu_lookup": gpu_lookup,
        "cpu_lookup": cpu_lookup,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"saved {len(gpu_lookup)} GPU + {len(cpu_lookup)} CPU device tiers -> {OUT}")


if __name__ == "__main__":
    main()
