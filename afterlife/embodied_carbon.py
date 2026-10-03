"""Look up a device's declared embodied carbon, and fall back honestly.

Two levels of answer, and the difference between them is stated rather than
smoothed over:

  matched   the manufacturer published an LCA for this exact model
  class     no match, so the median of every declaration for this device class

The second is still a real measurement -- 452 laptop declarations, not a number
quoted from a methodology document -- but it is a different claim, and callers
get told which one they received via the `basis` field.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "app_data" / "embodied_carbon.json"

_NOISE = re.compile(
    r"\b(inch|in|with|and|the|series|gen|generation|edition|laptop|notebook|"
    r"pc|computer|retina|display|cpu|gpu|ssd|hdd|gb|tb|ram|wifi|"
    r"\d+gb|\d+tb)\b", re.I)
_PUNCT = re.compile(r"[^a-z0-9]+")

#: Manufacturer strings arrive from WMI in whatever form the vendor wrote into
#: firmware -- "Dell Inc.", "HP", "Hewlett-Packard", "LENOVO". Boavizta uses one
#: form per vendor, so both sides are folded onto the same key before comparing.
_MAKER_ALIAS = {
    "dell inc": "dell", "dell computer corporation": "dell",
    "hewlett packard": "hp", "hewlett-packard": "hp", "hp inc": "hp",
    "lenovo group limited": "lenovo",
    "apple inc": "apple",
    "microsoft corporation": "microsoft",
    "acer inc": "acer", "asustek computer inc": "asus", "asustek": "asus",
    "samsung electronics": "samsung",
    "google inc": "google",
}

#: A minimum below which a match is a coincidence rather than a match. Two
#: shared tokens because a single shared word ("pro", "book", "x1") is shared by
#: dozens of unrelated models.
_MIN_SCORE = 0.6
_MIN_SHARED = 2


def _tokens(text: str) -> list[str]:
    t = _NOISE.sub(" ", (text or "").lower())
    t = _PUNCT.sub(" ", t)
    return [w for w in t.split() if len(w) > 1]


def _maker_key(name: str) -> str:
    k = _PUNCT.sub(" ", (name or "").lower()).strip()
    k = re.sub(r"\s+", " ", k)
    return _MAKER_ALIAS.get(k, k)


@lru_cache(maxsize=1)
def _load() -> dict:
    if not DATA.exists():
        return {}
    with DATA.open(encoding="utf-8") as fh:
        data = json.load(fh)
    for m in data.get("models", []):
        m["_maker"] = _maker_key(m["manufacturer"])
    return data


def class_estimate(device_class: str) -> dict[str, Any] | None:
    """The observed distribution for a device class, or None if we hold none."""
    stats = _load().get("classes", {}).get(device_class)
    if not stats:
        return None
    return {**stats, "basis": "class", "device_class": device_class}


def lookup(manufacturer: str | None, model: str | None,
           family: str | None = None, device_class: str | None = None) -> dict[str, Any] | None:
    """Best declared figure for this device, or the class median, or None.

    `family` is passed because Win32_ComputerSystem.Model is frequently a board
    SKU like "8A78" while SystemFamily carries the name a human would recognise.
    Both are searched; whichever matches better wins.
    """
    data = _load()
    models = data.get("models", [])
    if not models:
        return None

    maker = _maker_key(manufacturer or "")
    candidates = [m for m in models if m["_maker"] == maker] if maker else []

    best, best_key = None, (0.0, 0)
    if candidates:
        for query in (model, family):
            q = set(_tokens(query or ""))
            # The manufacturer name often repeats inside the model string
            # ("Dell Latitude 5420"); it identifies the vendor, not the model.
            q -= set(_tokens(manufacturer or ""))
            if len(q) < _MIN_SHARED:
                continue
            for cand in candidates:
                cand_tokens = set(cand["tokens"]) - set(_tokens(cand["manufacturer"]))
                shared = q & cand_tokens
                if len(shared) < _MIN_SHARED:
                    continue
                # Tie-break on how much of the candidate is left over. "ThinkBook
                # 14s" scores 1.0 against both "ThinkBook 14s" and "ThinkBook 14s
                # AMD"; the second is a different variant with its own declared
                # footprint, so reporting it would attach the wrong measurement
                # to the device. Fewer unexplained tokens wins.
                key = (len(shared) / len(q), -len(cand_tokens - shared))
                if key > best_key:
                    best, best_key = cand, key

    if best and best_key[0] >= _MIN_SCORE:
        return {
            "basis": "matched",
            "device_class": best["device_class"],
            "manufacturer": best["manufacturer"],
            "model": best["name"],
            "gwp_total_kg": best["gwp_total_kg"],
            "manufacturing_ratio": best["manufacturing_ratio"],
            "error_ratio": best["error_ratio"],
            "lifetime_years": best["lifetime_years"],
            "report_date": best["report_date"],
            "match_score": round(best_key[0], 2),
        }

    return class_estimate(device_class) if device_class else None


def caveat() -> str:
    return _load().get("caveat", "")
