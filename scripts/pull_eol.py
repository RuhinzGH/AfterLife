r"""Download the support-end dates from endoflife.date (S2-15).

Writes data/raw/external/endoflife_support_horizons.csv, which
scripts/build_device_support.py turns into app_data/device_support.json (the
table the site uses for "security updates until ...").

For every product endoflife.date tags as a device, plus the operating systems
that decide a laptop's support, it records each release's dates:
  eoas_from  active support ends (feature updates stop)
  eol_from   security support ends            <- the one AfterLife uses
  eoes_from  extended security ends (Windows ESU)

    venv\Scripts\python scripts\pull_eol.py
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "external" / "endoflife_support_horizons.csv"
BASE = "https://endoflife.date/api/v1"
UA = "AfterLife-research/1.0 (course project)"
OS_PRODUCTS = ["windows", "windows-server", "macos", "android", "ios", "ipados",
               "ubuntu", "chromeos", "linuxmint", "fedora", "debian"]
COLUMNS = ["kind", "product", "product_label", "release", "release_label", "codename",
           "release_date", "eoas_from", "eol_from", "eoes_from", "discontinued_from",
           "is_eol", "is_eoas", "is_maintained", "latest"]


def get(url: str, tries: int = 3) -> dict | None:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as exc:  # noqa: BLE001
            if i == tries - 1:
                print(f"  ! {url}: {type(exc).__name__}")
                return None
            time.sleep(1.5)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    out = ap.parse_args().out
    out.parent.mkdir(parents=True, exist_ok=True)

    cats = get(f"{BASE}/categories/device/")
    devices = [p["name"] for p in cats["result"]] if cats else []
    print(f"device products: {len(devices)}, operating systems: {len(OS_PRODUCTS)}")

    rows = []
    for kind, products in (("device", devices), ("os", OS_PRODUCTS)):
        for prod in products:
            d = get(f"{BASE}/products/{prod}/")
            if not d:
                continue
            res = d.get("result", {})
            for r in res.get("releases", []):
                rows.append({
                    "kind": kind, "product": prod, "product_label": res.get("label", prod),
                    "release": r.get("name"), "release_label": r.get("label"), "codename": r.get("codename"),
                    "release_date": r.get("releaseDate"), "eoas_from": r.get("eoasFrom"),
                    "eol_from": r.get("eolFrom"), "eoes_from": r.get("eoesFrom"),
                    "discontinued_from": r.get("discontinuedFrom"), "is_eol": r.get("isEol"),
                    "is_eoas": r.get("isEoas"), "is_maintained": r.get("isMaintained"),
                    "latest": (r.get("latest") or {}).get("name") if isinstance(r.get("latest"), dict) else r.get("latest"),
                })
            time.sleep(0.25)          # be polite to a free public API

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    have_eol = sum(1 for r in rows if r["eol_from"])
    print(f"wrote {out} ({len(rows)} releases, {have_eol} with a security-end date)")


if __name__ == "__main__":
    main()
