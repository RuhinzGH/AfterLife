"""Pull REAL game requirement data straight from Steam's own official API --
no Kaggle account needed. Builds a (release_year -> RAM/GPU requirement) table
to measure actual requirement inflation. scripts/fit_requirement_growth.py fits
the yearly growth rates that afterlife/persona.py uses.

AppID list comes from SteamSpy's top100forever (all-time most-owned, skews
toward older evergreen titles) + top100in2weeks (current trending, skews
recent) -- a convenience sample across a real ~15-year spread, not the full
catalog, but real official per-title data, not scraped/stale.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "steam_requirements.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (research script for a course project)"}


def get_appid_pool() -> dict[str, str]:
    pool = {}
    for req in ("top100forever", "top100in2weeks"):
        r = requests.get("https://steamspy.com/api.php", params={"request": req}, headers=HEADERS, timeout=20)
        r.raise_for_status()
        for appid, row in r.json().items():
            pool[appid] = row.get("name", "")
        time.sleep(1)
    return pool


GPU_HIGH = ("rtx 40", "rtx 50", "rx 7", "rx 9", "rtx 30", "rtx 3080", "rtx 3090")
GPU_MID = ("rtx 20", "gtx 16", "rx 6", "rx 5", "gtx 1070", "gtx 1080", "rtx 3060", "rtx 3050")
GPU_LOW = ("gtx", "rx ", "radeon", "nvidia", "geforce")


def gpu_tier_from_text(text: str) -> int:
    s = text.lower()
    if any(k in s for k in GPU_HIGH):
        return 3
    if any(k in s for k in GPU_MID):
        return 2
    if any(k in s for k in GPU_LOW):
        return 1
    return 0


def parse_ram_gb(text: str) -> float | None:
    m = re.search(r"Memory:</strong>\s*([\d.,]+)\s*(GB|MB)", text, re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1).replace(",", ""))
    return round(val / 1024, 2) if m.group(2).upper() == "MB" else val


def parse_gpu(text: str) -> str | None:
    m = re.search(r"Graphics:</strong>\s*([^<]+)", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def parse_year(release_date: dict) -> int | None:
    date_str = (release_date or {}).get("date", "")
    m = re.search(r"(19|20)\d{2}", date_str)
    return int(m.group(0)) if m else None


def main() -> None:
    pool = get_appid_pool()
    print(f"appid pool: {len(pool)} unique games")

    rows = []
    for i, (appid, name) in enumerate(pool.items()):
        try:
            r = requests.get("https://store.steampowered.com/api/appdetails",
                             params={"appids": appid, "cc": "us", "l": "en"}, headers=HEADERS, timeout=15)
            entry = r.json().get(str(appid), {})
            if not entry.get("success"):
                continue
            app = entry["data"]
            year = parse_year(app.get("release_date"))
            reqs = app.get("pc_requirements", {})
            min_text = reqs.get("minimum", "") if isinstance(reqs, dict) else ""
            rec_text = reqs.get("recommended", "") if isinstance(reqs, dict) else ""
            if not year or not min_text:
                continue
            row = {
                "appid": appid, "name": app.get("name", name), "year": year,
                "genres": [g.get("description") for g in (app.get("genres") or [])],
                "min_ram_gb": parse_ram_gb(min_text), "min_gpu_tier": gpu_tier_from_text(min_text),
                "min_gpu_text": parse_gpu(min_text),
                "rec_ram_gb": parse_ram_gb(rec_text), "rec_gpu_tier": gpu_tier_from_text(rec_text),
                "rec_gpu_text": parse_gpu(rec_text),
            }
            rows.append(row)
            print(f"  [{i+1}/{len(pool)}] {row['name']} ({year}): min={row['min_ram_gb']}GB tier{row['min_gpu_tier']}")
        except Exception as exc:
            print(f"  [{i+1}/{len(pool)}] {name} FAILED: {exc}")
        time.sleep(1.2)  # stay well under Steam's informal anonymous rate limit

    OUT.write_text(json.dumps(rows, indent=2))
    print(f"\nsaved {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
