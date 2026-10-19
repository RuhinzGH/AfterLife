"""Look up a device's OFFICIAL EU repairability grade, and refuse to guess.

WHAT THIS IS
------------
EPREL is the European Commission's product registry behind the energy and
repairability labels. Since 20 June 2025, registration has been compulsory for
smartphones and slate tablets placed on the EU market under Regulation (EU)
2023/1669 -- so this is not a voluntary dataset with the self-selection that
implies, it is a legal filing.

`scripts/pull_eprel.py` downloads it (2,568 models with an official, per-model
repairability class, fetched 27 August 2026), and `scripts/eda_eprel.py` is the
exploratory analysis of the same file (app_data/eprel_eda.json).

HOW A DEVICE IS FOUND
---------------------
Chrome on Android reports the phone's model code (e.g. "SM-S931B"), which is
the identifier makers register, so `find()` first tries that code; otherwise a
typed brand and model name is matched by `lookup()`. Either way, an unclear
match returns nothing rather than a guess.

WHY IT IS WORTH SURFACING NEXT TO THE ML PREDICTION
---------------------------------------------------
Afterlife already predicts a repair outcome from the Open Repair Alliance
corpus -- what technicians actually managed to fix. EPREL declares what the
manufacturer says the device is designed to allow. Those are different claims
about the same device, and showing them side by side is more interesting than
either alone: a high declared grade with a poor predicted outcome is exactly the
gap between design intent and the repair bench.

THE TWO THINGS THIS MUST NEVER DO
---------------------------------
1. **Answer for a laptop.** The registry covers phones and tablets only.
   Laptop repairability is still pending under ESPR. Afterlife assesses mostly
   laptops, so the tempting move -- fall back to a class median and show
   *something* -- would attach a phone regulation's grade to a device it does
   not cover. `lookup()` returns None for anything that is not a phone or
   tablet, and there is no class-median fallback anywhere in this module. That
   is deliberate and is the difference between this and embodied_carbon, where
   a class median IS a real measurement of the right population.

2. **Present a declaration as an outcome.** A repairability index here is
   declared before sale, by the party with a commercial interest in the grade,
   and scored against a published formula. It is not a measurement of whether
   anybody repaired one. Every response carries that caveat.

Attribution is a condition of use (Art. 4 §2): the European Commission is
credited wherever this data appears, and it is never resold.
"""
from __future__ import annotations

import json
import pathlib
import re
from functools import lru_cache
from typing import Any

DATA = pathlib.Path(__file__).resolve().parents[1] / "app_data" / "eprel_devices.json"

#: Words that identify no model. Mirrors embodied_carbon's noise list, plus the
#: storage/colour suffixes that dominate phone model strings.
_NOISE = re.compile(
    r"\b(the|and|with|series|gen|generation|edition|dual|sim|5g|4g|lte|wifi|"
    r"\d+gb|\d+tb|black|white|blue|green|grey|gray|silver|gold|titanium)\b", re.I)
_PUNCT = re.compile(r"[^a-z0-9]+")

#: Two shared tokens minimum, same reasoning as embodied_carbon: one shared word
#: ("pro", "plus", "note") is shared by dozens of unrelated handsets.
_MIN_SCORE = 0.6
_MIN_SHARED = 2

#: Only these reach the registry. Anything else must return None.
COVERED_TYPES = {"phone", "smartphone", "tablet", "mobile"}

_BRAND_ALIAS = {
    "samsung electronics": "samsung", "samsung electronics co ltd": "samsung",
    "apple inc": "apple",
    "xiaomi communications": "xiaomi", "xiaomi inc": "xiaomi",
    "guangdong oppo": "oppo", "oneplus technology": "oneplus",
    "motorola mobility": "motorola", "lenovo motorola": "motorola",
    "google llc": "google", "google inc": "google",
    "huawei technologies": "huawei", "honor device": "honor",
}


def _tokens(text: str) -> list[str]:
    t = _NOISE.sub(" ", (text or "").lower())
    t = _PUNCT.sub(" ", t)
    return [w for w in t.split() if len(w) > 1]


def _brand_key(name: str) -> str:
    k = _PUNCT.sub(" ", (name or "").lower()).strip()
    k = re.sub(r"\s+", " ", k)
    return _BRAND_ALIAS.get(k, k)


@lru_cache(maxsize=1)
def _load() -> dict:
    if not DATA.exists():
        return {}
    with DATA.open(encoding="utf-8") as fh:
        data = json.load(fh)
    for d in data.get("devices", []):
        d["_brand"] = _brand_key(d.get("supplierOrTrademark") or "")
        d["_tokens"] = set(_tokens(d.get("modelIdentifier") or ""))
        d["_exact"] = _exact_key(d.get("modelIdentifier") or "")
    return data


def _exact_key(text: str) -> str:
    """Everything but letters and digits removed, for identity comparison."""
    return _PUNCT.sub("", (text or "").lower())


def is_covered(device_type: str | None) -> bool:
    """Is this device even in the registry's scope?

    Checked before any matching, because a near-miss against a phone model is
    still the wrong answer for a laptop -- and a confident wrong repairability
    grade is worse than none, since the user cannot tell it is wrong.
    """
    t = (device_type or "").strip().lower()
    return any(k in t for k in COVERED_TYPES)


def _grade_words(cls: str | None, index: float | None) -> str:
    if not cls:
        return "No repairability class registered."
    scale = {"A": "the best of five bands", "B": "above the middle band",
             "C": "the middle band", "D": "below the middle band",
             "E": "the lowest of five bands"}.get(cls.upper(), "")
    idx = f" ({index:.2f} out of 5)" if index is not None else ""
    return f"Class {cls.upper()}{idx} — {scale}." if scale else f"Class {cls.upper()}{idx}."


def lookup(manufacturer: str | None, model: str | None,
           device_type: str | None = None) -> dict[str, Any] | None:
    """The registered EU repairability record for this device, or None.

    None means one of three honest things -- out of scope, not registered, or
    matched too weakly to trust -- and the caller renders nothing rather than a
    hedge. There is deliberately no class-median fallback; see the module
    docstring.
    """
    if not is_covered(device_type):
        return None

    data = _load()
    devices = data.get("devices", [])
    if not devices:
        return None

    # The vendor may arrive on its own field, or folded into the model string
    # ("Samsung Galaxy S21"), depending on which scan produced it.
    #
    # The leading word of the model is only a brand candidate when no explicit
    # manufacturer was sent. Treating it as one regardless was a real bug: for
    # "motorola" + "g05 (XT2523-3)" it made "g05" a brand, and then stripped
    # that same token out of the query, leaving one token to match on and
    # failing every lookup that arrived with both fields populated.
    explicit = _brand_key(manufacturer or "")
    folded = _brand_key((model or "").split()[0]) if (model and not explicit) else ""
    brands = [b for b in (explicit, folded) if b]
    candidates = [d for d in devices if d["_brand"] in brands] if brands else []
    if not candidates:
        return None

    # An exact identity match, before any token scoring.
    #
    # The two-token minimum exists to stop coincidental overlap across a large
    # catalogue, but it also rejects legitimately short registrations -- "T
    # Tablet 2" reduces to a single usable token and could never match itself.
    # An exact string match is not a coincidence at any length, so it is checked
    # first and bypasses the threshold entirely.
    want_exact = _exact_key(model or "")
    if folded:
        want_exact = _exact_key(" ".join((model or "").split()[1:]))
    if want_exact:
        for cand in candidates:
            if cand["_exact"] == want_exact:
                return _record(cand, data, 1.0)

    q = set(_tokens(model or "")) - set(_tokens(manufacturer or ""))
    # Drop the brand word only where it came FROM the model string; the vendor
    # identifies the maker, not the model, and candidate selection used it already.
    if folded:
        q -= {folded}
    if len(q) < _MIN_SHARED:
        return None

    best, best_key = None, (0.0, 0)
    for cand in candidates:
        shared = q & cand["_tokens"]
        if len(shared) < _MIN_SHARED:
            continue
        # Same tie-break as embodied_carbon: fewer unexplained tokens in the
        # candidate wins, so "Galaxy S21" does not resolve to "Galaxy S21 Ultra".
        key = (len(shared) / len(q), -len(cand["_tokens"] - shared))
        if key > best_key:
            best, best_key = cand, key

    if not best or best_key[0] < _MIN_SCORE:
        return None

    return _record(best, data, best_key[0])


def _record(best: dict, data: dict, score: float) -> dict[str, Any]:
    """Shape one registry row into the response. Shared by both match paths so
    an exact hit and a token hit can never return different field sets."""
    return {
        "basis": "matched",
        "registration": best.get("eprelRegistrationNumber"),
        "brand": best.get("supplierOrTrademark"),
        "model": best.get("modelIdentifier"),
        "device_type": best.get("deviceType"),
        "repairability_class": best.get("repairabilityClass"),
        "repairability_index": best.get("repairabilityIndex"),
        "grade_note": _grade_words(best.get("repairabilityClass"),
                                   best.get("repairabilityIndex")),
        # The sub-scores are the interesting part: the published index weights
        # dismantling heavily and battery longevity barely at all, which is a
        # finding the Lab 3 EDA already established on this same registry.
        "disassembly_depth": best.get("disassemblyDepthScore"),
        "fasteners": best.get("fastenersScore"),
        "tools": best.get("toolsScore"),
        "spare_parts": best.get("sparePartScore"),
        "repair_info": best.get("repairInfoScore"),
        "battery_user_replaceable": best.get("batteryUserReplaceable"),
        "battery_cycles": best.get("batteryEnduranceInCycles"),
        "min_years_software_updates": best.get("minYearsSoftwareUpdates"),
        "guarantee_months": best.get("guaranteeDuration"),
        "fall_reliability_class": best.get("repeatedFreeFallReliabilityClass"),
        "ingress_protection": best.get("ingressProtectionRating"),
        "repair_instructions_url": best.get("webLinkRepairInstructions"),
        "spare_parts_url": best.get("webLinkInfoSparePartsAvailability"),
        "match_score": round(score, 2),
        "attribution": data.get("attribution"),
        "regulation": data.get("regulation"),
        "fetched": data.get("fetched"),
        "caveat": ("This is repairability as DECLARED to the EU registry before "
                   "sale, scored against a published formula by the manufacturer. "
                   "It is a design and documentation grade, not a record of "
                   "whether anyone repaired one."),
    }


def coverage() -> dict[str, Any]:
    """What the registry holds, for the research page."""
    data = _load()
    devices = data.get("devices", [])
    classes: dict[str, int] = {}
    for d in devices:
        c = (d.get("repairabilityClass") or "").upper()
        if c:
            classes[c] = classes.get(c, 0) + 1
    return {
        "count": len(devices),
        "classified": sum(classes.values()),
        "classes": dict(sorted(classes.items())),
        "scope": "Smartphones and slate tablets placed on the EU market. "
                 "Laptops are not covered — their repairability requirements "
                 "are still pending under ESPR.",
        "attribution": data.get("attribution"),
        "regulation": data.get("regulation"),
        "fetched": data.get("fetched"),
    }


def lookup_code(code: str | None) -> dict[str, Any] | None:
    """Match a model code as a phone reports it ("SM-S931B"), with no brand.

    Registered identifiers often add a variant suffix ("SM-S931B/DS") or wrap
    the code in a name ("g05 (XT2523-3)"), so a registration matches when it is
    the code, starts with it, or contains it in brackets. If the matches do not
    all carry the same class, the answer is unclear and nothing is returned.
    """
    key = _exact_key(code or "")
    if len(key) < 5:
        return None
    data = _load()
    low = (code or "").strip().lower()
    hits = [d for d in data.get("devices", [])
            if d["_exact"] == key or d["_exact"].startswith(key)
            or f"({low}" in (d.get("modelIdentifier") or "").lower()]
    classes = {(d.get("repairabilityClass") or "").upper() for d in hits}
    if not hits or len(classes) != 1:
        return None
    exact = [d for d in hits if d["_exact"] == key]
    return _record((exact or hits)[0], data, 1.0 if exact else 0.9)


def find(model: str | None, product_category: str | None,
         manufacturer: str | None = None) -> dict[str, Any] | None:
    """The registered grade for a phone or tablet, from a model code or a typed
    "brand model" name. None for laptops and anything unclear."""
    if not is_covered(product_category) or not (model or "").strip():
        return None
    return lookup_code(model) or lookup(manufacturer, model, product_category)


def class_spread() -> dict[str, Any] | None:
    """How the registry's classes are spread (from scripts/eda_eprel.py), so a
    grade can be read against the whole register."""
    path = DATA.parent / "eprel_eda.json"
    try:
        eda = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None
    return {"n": eda.get("n"), "classes": eda.get("repairability_class"),
            "median_index": (eda.get("repairability_index") or {}).get("median")}

