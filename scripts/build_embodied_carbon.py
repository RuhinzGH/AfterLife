"""Build a per-model embodied-carbon table from Boavizta's manufacturer LCA data.

This exists to retire a limitation the research page states outright: that the
carbon figures are ranges over a class of device and are "not a measurement of
any specific machine". Boavizta collects the LCA figures manufacturers publish
for named models, so for a device we can identify, we can report that model's
declared footprint instead of a class-wide guess.

Two things ship in the artifact:

  models      per-model declared figures, for the lookup
  classes     the observed distribution per device class, for everything else --
              a median and an interquartile range measured from real
              declarations, rather than a range quoted from a methodology doc

Boavizta's own guidance is that these come from manufacturer declarations with
methodologies that are neither uniform nor fully transparent, so they are good
for orders of magnitude and for comparing models from one manufacturer, and bad
for precise cross-manufacturer claims. That caveat travels in the artifact
rather than being left on their website.

    python scripts/build_embodied_carbon.py
"""
from __future__ import annotations

import csv
import io
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

SRC = ("https://raw.githubusercontent.com/Boavizta/environmental-footprint-data/"
       "main/boavizta-data-us.csv")
OUT = ROOT / "app_data" / "embodied_carbon.json"

#: Boavizta subcategory -> the device class this project talks about.
CLASS_OF = {
    "laptop": "Laptop",
    "notebook": "Laptop",
    "desktop": "Desktop computer",
    "workstation": "Desktop computer",
    "tablet": "Tablet",
    "smartphone": "Mobile",
    "mobile": "Mobile",
    "monitor": "Monitor",
    "display": "Monitor",
}

_NOISE = re.compile(
    r"\b(inch|in|with|and|the|series|gen|generation|edition|laptop|notebook|"
    r"pc|computer|retina|display|cpu|gpu|ssd|hdd|gb|tb|ram|wifi|"
    r"\d+gb|\d+tb)\b", re.I)
_PUNCT = re.compile(r"[^a-z0-9]+")


def norm_tokens(text: str) -> list[str]:
    """Model names are written inconsistently across manufacturers and scans.

    "13-inch MacBook Air (M1 CPU) 256GB" and "MacBook Air M1" have to land on
    each other, so strip the things that vary (storage size, marketing words,
    punctuation) and keep the things that identify (family, model, chip).
    """
    t = _NOISE.sub(" ", text.lower())
    t = _PUNCT.sub(" ", t)
    return [w for w in t.split() if len(w) > 1]


def classify(row: dict) -> str | None:
    blob = f"{row.get('subcategory', '')} {row.get('category', '')}".lower()
    for key, cls in CLASS_OF.items():
        if key in blob:
            return cls
    return None


def num(value: str) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def main() -> None:
    print(f"GET {SRC}")
    r = requests.get(SRC, headers={"User-Agent": "Afterlife-research/0.1"}, timeout=120)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    print(f"  {len(rows):,} rows, {len(rows[0])} columns")

    models: list[dict] = []
    for row in rows:
        cls = classify(row)
        gwp = num(row.get("gwp_total", ""))
        if not cls or gwp is None:
            continue
        name = (row.get("name") or "").strip()
        maker = (row.get("manufacturer") or "").strip()
        if not name or not maker:
            continue
        models.append({
            "manufacturer": maker,
            "name": name,
            "device_class": cls,
            "gwp_total_kg": round(gwp, 1),
            # Share of the total that is manufacturing rather than use. This is
            # the number the repair-versus-replace argument actually turns on:
            # a high ratio means replacing the device throws away most of its
            # footprint, whichever grid it is plugged into.
            "manufacturing_ratio": num(row.get("gwp_manufacturing_ratio", "")),
            "error_ratio": num(row.get("gwp_error_ratio", "")),
            "lifetime_years": num(row.get("lifetime", "")),
            "report_date": (row.get("report_date") or "")[:10] or None,
            "tokens": norm_tokens(f"{maker} {name}"),
        })

    classes: dict[str, dict] = {}
    for cls in sorted({m["device_class"] for m in models}):
        vals = sorted(m["gwp_total_kg"] for m in models if m["device_class"] == cls)
        ratios = [m["manufacturing_ratio"] for m in models
                  if m["device_class"] == cls and m["manufacturing_ratio"]]
        q = statistics.quantiles(vals, n=4) if len(vals) >= 4 else [vals[0], vals[0], vals[-1]]
        classes[cls] = {
            "n": len(vals),
            "median_kg": round(statistics.median(vals), 1),
            "p25_kg": round(q[0], 1),
            "p75_kg": round(q[2], 1),
            "min_kg": vals[0],
            "max_kg": vals[-1],
            "median_manufacturing_ratio": round(statistics.median(ratios), 3) if ratios else None,
        }
        print(f"  {cls:<17} n={len(vals):>4}  median {classes[cls]['median_kg']:>6.1f} kg"
              f"  IQR {classes[cls]['p25_kg']:.0f}-{classes[cls]['p75_kg']:.0f}"
              f"  mfg share {classes[cls]['median_manufacturing_ratio']}")

    makers: dict[str, int] = {}
    for m in models:
        makers[m["manufacturer"]] = makers.get(m["manufacturer"], 0) + 1

    payload = {
        "source": "Boavizta environmental-footprint-data (manufacturer LCA declarations)",
        "url": "https://github.com/Boavizta/environmental-footprint-data",
        "n_models": len(models),
        "manufacturers": dict(sorted(makers.items(), key=lambda kv: -kv[1])),
        "classes": classes,
        "caveat": "Manufacturer-declared figures. Boavizta's own guidance is that the underlying "
                  "methodologies are neither uniform nor fully transparent, so these are sound for "
                  "orders of magnitude and for comparing models from one manufacturer, and unsound "
                  "for precise comparison across manufacturers.",
        "models": models,
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}  "
          f"({OUT.stat().st_size / 1024:.0f} KB, {len(models):,} models)")


if __name__ == "__main__":
    main()
