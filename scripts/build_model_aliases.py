"""Map phone model codes ("SM-S711B") to the names the support table uses.

    set PYTHONPATH=.
    venv\\Scripts\\python scripts\\build_model_aliases.py [path\\to\\supported_devices.csv]

Input : Google Play's supported-devices list (Retail Branding, Marketing Name,
        Device, Model), published by Google at
        https://storage.googleapis.com/play_public/supported_devices.csv
        (UTF-16). Downloaded if no path is given.
Output: app_data/model_aliases.json

Why. Chrome on Android reports a phone's model CODE (navigator.userAgentData
model, e.g. "SM-S711B"), but endoflife.date -- and so app_data/device_support.json
-- lists phones by NAME ("Galaxy S23 FE"). Without this map a current phone got
no support date at all. Only codes whose marketing name matches a device in the
support table are kept, so the file stays small and every alias leads somewhere.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = "https://storage.googleapis.com/play_public/supported_devices.csv"
OUT = ROOT / "app_data" / "model_aliases.json"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_csv(path: str | None) -> str:
    raw = pathlib.Path(path).read_bytes() if path else urllib.request.urlopen(URL, timeout=60).read()
    return raw.decode("utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8")


def main() -> None:
    devices = json.loads((ROOT / "app_data" / "device_support.json").read_text(encoding="utf-8"))["devices"]
    known = set(devices)
    aliases: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(load_csv(sys.argv[1] if len(sys.argv) > 1 else None))):
        brand, name, code = row.get("Retail Branding", ""), row.get("Marketing Name", ""), row.get("Model", "")
        if not (name and code):
            continue
        # The support table keys phones by normalised name, with or without the
        # vendor prefix ("galaxys23fe", "samsungmobilegalaxys23fe", "pixel8").
        # Names that reduce to very little (non-Latin names, "7 Plus") could
        # match the wrong phone, so a key needs 6+ characters, and the alias is
        # stored in the exact form the table holds, so the lookup hits it directly.
        if not name.isascii():
            continue
        for candidate in (f"{brand} {name}".strip(), name):
            if len(norm(candidate)) >= 6 and norm(candidate) in known:
                aliases[norm(code)] = candidate
                break
    OUT.write_text(json.dumps({
        "source": "Google Play supported devices list",
        "url": URL,
        "fetched": dt.date.today().isoformat(),
        "note": "Model code (normalised) -> marketing name, kept only where the name is in device_support.json.",
        "count": len(aliases),
        "aliases": dict(sorted(aliases.items())),
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(aliases)} model codes")


if __name__ == "__main__":
    main()
