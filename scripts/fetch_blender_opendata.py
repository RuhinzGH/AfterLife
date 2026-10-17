"""Pull REAL benchmark data from Blender Open Data's own JSON API (discovered
by watching the SPA's actual network calls -- the static page HTML doesn't
expose it directly). License: Blender's own open-data policy states results
are "license-free" (not copyrightable). Used to build real percentile-based
GPU/CPU performance tiers instead of the hand-picked gpu_tier() keyword bucket.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "blender_opendata.json"
OUT.parent.mkdir(parents=True, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (research script for a course project)"}
BASE = "https://opendata.blender.org/benchmarks/query/"


def fetch(params: dict) -> list:
    r = requests.get(BASE, params={**params, "response_type": "datatables"}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d["rows"]


def main() -> None:
    out = {}
    # CPU device scores
    out["cpu"] = fetch({"blender_version": "5.1.1", "group_by": "device_name", "compute_type": "CPU"})
    print(f"CPU devices: {len(out['cpu'])}")
    # GPU device scores across the common compute backends
    out["gpu"] = fetch({"blender_version": "5.1.1", "group_by": "device_name",
                        "compute_type": ["OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"]})
    print(f"GPU devices: {len(out['gpu'])}")

    OUT.write_text(json.dumps(out, indent=2))
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
