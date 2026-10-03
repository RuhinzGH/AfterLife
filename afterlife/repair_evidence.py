"""Match a device's actual condition to real repair outcomes from the ORA corpus.

`scripts/build_repair_evidence.py` computes the table; this reads it and answers
"what happened to other people who brought in a machine like this one?"

The distinction that matters: this never tells anyone what the fix *is*. The
source data records the fault and the outcome, not the work performed, so
claiming to know the repair would be inventing a column. What it can say — and
what a person deciding whether to bother actually wants — is how often that
fault ended with a working device, and what stopped it when it didn't.

Two ways in:
  * `themes_for_device()` — from measured condition (worn battery, failing disk,
    an unsupported OS), used on every scan.
  * `themes_for_text()` — from the fault the user typed in, used on the instant
    scan where "anything wrong?" is free text.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

#: Same app_data-first resolution as hardening.corpus_path: the shipped artifact
#: is the one that exists in the container, and a path that only resolves on a
#: developer's laptop is the worst kind of broken.
_CANDIDATES = (ROOT / "app_data" / "repair_evidence.json",
               ROOT / "data" / "derived" / "repair_evidence.json")


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    for p in _CANDIDATES:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


@lru_cache(maxsize=1)
def _by_key() -> dict[str, dict[str, Any]]:
    return {t["key"]: t for t in load().get("themes", [])}


#: What the *user* might type, in the four languages the source data is written
#: in, mapped to a theme. Deliberately separate from the build script's keyword
#: sets: those exist to mine historical records at high recall, these exist to
#: read one sentence someone typed just now, where a false match is visible and
#: embarrassing rather than statistically absorbed.
_TEXT_HINTS: dict[str, tuple[str, ...]] = {
    "battery": ("battery", "akku", "batterij", "charge", "charging", "swollen", "drains"),
    "power": ("won't turn on", "wont turn on", "no power", "dead", "charger",
              "adapter", "won't start", "wont start", "doesn't boot"),
    "storage": ("hard drive", "harddrive", "disk", "ssd", "hdd", "storage", "space"),
    "screen": ("screen", "display", "cracked", "flicker", "backlight", "dim"),
    "overheating": ("hot", "overheat", "fan", "loud", "noisy", "thermal"),
    "keyboard": ("keyboard", "key ", "keys", "trackpad", "touchpad", "mouse"),
    "software": ("slow", "windows", "update", "virus", "boot", "software",
                 "freezes", "crashes", "lag"),
    "physical": ("hinge", "lid", "case", "broken", "crack"),
    "ports": ("usb", "port", "hdmi", "socket", "jack", "connector"),
}


def themes_for_text(problem: str | None) -> list[dict[str, Any]]:
    """Themes matching a free-text fault description, best-supported first."""
    if not problem or not problem.strip():
        return []
    low = problem.lower()
    hits = [k for k, words in _TEXT_HINTS.items() if any(w in low for w in words)]
    table = _by_key()
    return [table[k] for k in hits if k in table]


def themes_for_device(
    battery_health: float | None = None,
    storage_health: str | None = None,
    drive_wear_pct: float | None = None,
    os_supported: bool | None = None,
    problem: str | None = None,
) -> list[dict[str, Any]]:
    """Themes matching what was actually measured on this machine.

    Only fires on evidence, never on absence: a machine with no battery reading
    is not a machine with a healthy battery, so it contributes no theme rather
    than a reassuring one.
    """
    table = _by_key()
    keys: list[str] = []

    # 80% is the same threshold blend_score() already treats as the first real
    # wear band, so the two never disagree about whether a battery is a finding.
    if battery_health is not None and battery_health < 80:
        keys.append("battery")
    if storage_health and storage_health.upper() not in ("OK", "HEALTHY", "UNKNOWN"):
        keys.append("storage")
    if drive_wear_pct is not None and drive_wear_pct >= 80:
        keys.append("storage")
    if os_supported is False:
        keys.append("software")

    for t in themes_for_text(problem):
        keys.append(t["key"])

    seen, out = set(), []
    for k in keys:
        if k in table and k not in seen:
            seen.add(k)
            out.append(table[k])
    return out


def summarize(themes: list[dict[str, Any]]) -> list[str]:
    """One plain sentence per theme, safe to show a non-technical reader.

    Phrased as an observed rate, never as a promise about this device -- "62% of
    these were repaired" is a fact about a dataset; "yours can be repaired" is a
    claim nobody can support.
    """
    lines = []
    for t in themes:
        line = (f"{t['label']}: of {t['n']:,} computers brought to repair events with "
                f"this fault, {t['fixed_pct']:.0f}% left working.")
        if t.get("top_barrier"):
            line += f" When it couldn't be fixed, the usual reason was \"{t['top_barrier'].lower()}\"."
        lines.append(line)
    return lines


def evidence_block(**kwargs: Any) -> dict[str, Any] | None:
    """The whole payload the API attaches to an assessment, or None if nothing
    about this device matches a theme we hold enough records for."""
    themes = themes_for_device(**kwargs)
    if not themes:
        return None
    meta = load()
    return {
        "themes": themes,
        "lines": summarize(themes),
        "source": meta.get("source"),
        "n_records": meta.get("n_records"),
        "overall_fixed_pct": meta.get("overall_fixed_pct"),
    }
