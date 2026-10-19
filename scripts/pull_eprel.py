"""Pull the EPREL smartphone & tablet registry into a runtime artifact.

Source: European Product Registry for Energy Labelling (EPREL), product group
smartphonestablets20231669, Regulation (EU) 2023/1669. Registration has been
mandatory for smartphones and slate tablets placed on the EU market since
20 June 2025, so coverage is a legal obligation rather than a voluntary upload
-- which is exactly why this does not suffer the self-selection that made the
data.gouv.fr repairability publications useless (95% of those rows came from two
manufacturers, and nothing scored below 8.7/10).

Scope note, because it is easy to overclaim: this covers PHONES AND TABLETS
ONLY. Laptop repairability is still pending under ESPR, so nothing here fills
the laptop gap -- see the note in afterlife/passport.py.

Terms. Use is permitted under Article 4 §1 (iii) research and (v) implementation
in applications and comparison tools. Three obligations follow and are honoured
here: the Commission is credited wherever the data appears, the data is never
resold, and a stored copy must be kept current rather than snapshotted once
(Art. 4 §2(f)) -- so this script is re-runnable and stamps its own fetch date.

The key is read from .env and sent in the X-API-KEY header. It is server-side
only: the terms forbid disclosing it to third parties, and EPREL enables CORS
precisely to stop it being called from a browser.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "app_data" / "eprel_devices.json"
GROUP = "smartphonestablets20231669"
API = f"https://eprel.ec.europa.eu/api/products/{GROUP}"

#: The paged endpoint ignores every pagination parameter tried -- offset, page,
#: from, start, and their underscore variants all return the same first 25 hits
#: with offset stuck at 0. exportProducts returns the whole group as a ZIP of
#: JSON instead, which is one request rather than ninety-four and keeps us well
#: inside the 5 req/sec limit.
EXPORT = f"https://eprel.ec.europa.eu/api/exportProducts/{GROUP}"

#: Their documented ceiling is 5 requests/second.
DELAY = 0.4

#: 81 fields come back per model; these are the ones the product can act on.
KEEP = [
    "eprelRegistrationNumber", "modelIdentifier", "supplierOrTrademark", "deviceType",
    "operatingSystem", "isFoldable",
    # repairability
    "repairabilityClass", "repairabilityIndex", "disassemblyDepthScore",
    "fastenersScore", "toolsScore", "sparePartScore", "repairInfoScore",
    # durability
    "repeatedFreeFallReliabilityClass", "fallsWithoutDefect",
    "ingressProtectionRating", "screenScratchResistance",
    # battery
    "batteryUserReplaceable", "batteryEnduranceInCycles", "ratedBatteryCapacity",
    "batteryEndurancePerCycleInHours",
    # support horizon and warranty
    "minYearsSoftwareUpdates", "softwareUpdatesScore", "guaranteeDuration",
    # where the owner can actually go
    "webLinkRepairInstructions", "webLinkInfoSparePartsAvailability",
    "webLinkPretaxPrices",
    "energyClass", "onMarketStartDate", "modelAvailabilityInEUEEACountries",
]


def api_key() -> str:
    env = ROOT / ".env"
    if env.exists():
        m = re.search(r"EPREL_API_KEY=(\S+)", env.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    k = os.environ.get("EPREL_API_KEY")
    if not k:
        raise SystemExit("EPREL_API_KEY not found in .env or the environment")
    return k


def fetch(url: str, key: str, tries: int = 3):
    for i in range(tries):
        req = urllib.request.Request(url, headers={
            "X-API-KEY": key, "Accept": "application/json",
            "User-Agent": "AfterLife-research/1.0 (BCA final-year project)"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:                  # throttled: back off and retry
                time.sleep(2 + 2 * i)
                continue
            if i == tries - 1:
                print(f"    ! HTTP {e.code} on {url}")
                return None
            time.sleep(1.5)
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(1.5)
    return None


def download(url: str, key: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "X-API-KEY": key, "Accept": "application/zip, application/json",
        "User-Agent": "AfterLife-research/1.0 (BCA final-year project)"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def main() -> None:
    import io as _io
    import zipfile

    key = api_key()

    # Headline count, so the export can be checked against what the registry says.
    meta = fetch(API, key) or {}
    total = int(meta.get("size", 0))
    print(f"product group : {GROUP}")
    print(f"registry says : {total:,} models")

    time.sleep(DELAY)
    blob = download(EXPORT, key)
    print(f"export        : {len(blob)/1024:.0f} KB ZIP")

    rows, seen = [], set()
    with zipfile.ZipFile(_io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if n.endswith(".json")]
        print(f"                {len(names)} JSON member(s): {names[:3]}")
        for n in names:
            payload = json.loads(z.read(n))
            hits = payload if isinstance(payload, list) else payload.get("hits", [])
            for h in hits:
                rid = h.get("eprelRegistrationNumber")
                if rid in seen:
                    continue
                seen.add(rid)
                rows.append({k: h.get(k) for k in KEEP})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "European Product Registry for Energy Labelling (EPREL)",
        "attribution": "Data © European Union, European Commission (EPREL). "
                       "Used under the EPREL Public API Terms and Conditions, "
                       "Article 4 §1 (iii) and (v).",
        "regulation": "Regulation (EU) 2023/1669 — smartphones and slate tablets",
        "product_group": GROUP,
        "scope_note": "Phones and tablets only. Laptop repairability is not yet "
                      "in scope under ESPR.",
        "fetched": time.strftime("%Y-%m-%d"),
        "count": len(rows),
        "devices": rows,
    }, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"\nwrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size/1024:.0f} KB)")
    print(f"  models captured : {len(rows):,} of {total:,}")

    import collections
    for f in ["deviceType", "repairabilityClass", "repeatedFreeFallReliabilityClass",
              "minYearsSoftwareUpdates", "batteryUserReplaceable"]:
        c = collections.Counter(r[f] for r in rows if r.get(f) is not None)
        print(f"  {f:<34} {dict(sorted(c.items(), key=lambda kv: str(kv[0]))[:7])}")
    brands = collections.Counter(r["supplierOrTrademark"] for r in rows if r.get("supplierOrTrademark"))
    print(f"  brands: {len(brands)}   top: {dict(brands.most_common(6))}")


if __name__ == "__main__":
    main()
