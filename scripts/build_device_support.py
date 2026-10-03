"""Compact the endoflife.date pull into a runtime lookup the API can read.

Input : data/raw/external/endoflife_support_horizons.csv (scripts/pull_eol.py)
Output: app_data/device_support.json

Why this exists. `eol_risk` on /api/assess arrives from the client as a bare
float -- a number the caller invents. Every other input to blend_score is
measured, so the security pillar was the one guess in an otherwise
measurement-driven score. endoflife.date publishes the date security updates
actually stop for 803 consumer device models, which turns that guess into a
lookup.

Two dates matter and they are not the same thing:
    eoas_from -- active support ends (no more feature/OS upgrades)
    eol_from  -- security support ends  <- the one that drives risk
A phone can stop receiving new Android versions years before it stops
receiving security patches, and only the second changes the keep-or-replace
answer.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "external" / "endoflife_support_horizons.csv"
OUT = ROOT / "app_data" / "device_support.json"


def norm(s: str | None) -> str:
    """Lowercase, strip everything that is not a letter or digit.

    Device names arrive from three naming universes -- marketing names from the
    user ("Galaxy Z Fold3 5G"), slugs from endoflife.date ("galaxy-z-fold3-5g"),
    and SKUs from manufacturers. Stripping separators is the only normalisation
    that survives all three.
    """
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC} -- run scripts/pull_eol.py first")

    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    devices: dict[str, dict] = {}
    os_entries: dict[str, dict] = {}

    for r in rows:
        eol = (r.get("eol_from") or "").strip()
        if not eol:
            # No published security-end date means we cannot say anything
            # defensible about this model. Better absent than guessed.
            continue
        entry = {
            "product": r.get("product_label") or r.get("product"),
            "release": r.get("release_label") or r.get("release"),
            "eol_from": eol,
            "eoas_from": (r.get("eoas_from") or "").strip() or None,
            "release_date": (r.get("release_date") or "").strip() or None,
        }
        label = f"{entry['product']} {entry['release']}"
        target = devices if r.get("kind") == "device" else os_entries

        # Index under both the full "brand + model" string and the model alone.
        # A user typing "Galaxy S21" should resolve as readily as one whose
        # collector reports "Samsung Galaxy S21".
        for key in {norm(label), norm(entry["release"])}:
            if len(key) < 4:
                continue  # "17", "w11" and friends collide with everything
            # First writer wins: rows are in release order, so the earliest
            # match is the base model rather than a later variant.
            target.setdefault(key, entry)

    # ---- OS families -------------------------------------------------------
    # Users say "Windows 10", never "10 22H2 (W)". endoflife.date indexes the
    # feature update, so a family index has to be built: for each OS + major
    # version, the consumer cycle whose security support runs longest. That is
    # the date that actually governs someone still on that OS.
    families: dict[str, dict] = {}
    for entry in os_entries.values():
        rel = entry["release"] or ""
        # Windows leads with the number ("10 22H2"); macOS leads with the
        # codename ("Sequoia 15"). Take a leading number if there is one,
        # otherwise the first standalone number anywhere in the label.
        m = re.match(r"\s*(\d+(?:\.\d+)?)", rel) or re.search(r"\b(\d{1,2})\b", rel)
        if not m:
            continue
        major = m.group(1)
        product = entry["product"] or ""
        # Skip Windows enterprise/LTSC/IoT lines: a home user is not on them and
        # their much longer support windows would flatter the answer. Scoped to
        # Windows deliberately -- Ubuntu's "(LTS)" means the opposite, it is the
        # release ordinary people actually run.
        if "windows" in product.lower() and re.search(r"\((?:E|LTS)\)|IoT|LTSC|LTSB", rel, re.I):
            continue
        # "Android OS" -> "Android", so a reported "Android 14" resolves.
        short = re.sub(r"^(microsoft|apple|google)\s+", "", product, flags=re.I)
        short = re.sub(r"\s+OS$", "", short, flags=re.I)
        for key in {norm(f"{product} {major}"), norm(f"{short} {major}")}:
            if len(key) < 4:
                continue
            cur = families.get(key)
            if cur is None or entry["eol_from"] > cur["eol_from"]:
                families[key] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "endoflife.date",
        "licence": "see endoflife.date; data aggregated from vendor announcements",
        "devices": devices,
        "os": os_entries,
        "os_families": families,
    }, indent=1), encoding="utf-8")

    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  device keys : {len(devices)}")
    print(f"  os keys     : {len(os_entries)}")
    print(f"  os families : {len(families)}")
    for k in ("windows10", "windows11", "android14", "macos15"):
        if k in families:
            f = families[k]
            print(f"    {k:<12} -> {f['release']:<20} eol {f['eol_from']}")
    print(f"  size        : {OUT.stat().st_size/1024:.0f} KB")
    for k in list(devices)[:5]:
        print(f"    {k:<28} -> {devices[k]['product']} {devices[k]['release']} "
              f"eol {devices[k]['eol_from']}")


if __name__ == "__main__":
    main()
