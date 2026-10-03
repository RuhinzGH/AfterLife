"""Build the timezone -> country -> (currency, jurisdiction, evidence coverage) lookup.

Why not IP geolocation. Country could equally be derived from the visitor's IP
using a MaxMind GeoLite2 database, and that was the first idea. Two things ruled
it out. GeoLite2 is MaxMind's proprietary product under their End User Licence,
which contradicts this project's stated scope ("open APIs and datasets only; no
proprietary or paid source"). And an IP address is personal data -- deriving
location from it server-side is processing we would then have to justify, for a
result the browser can hand us directly.

The browser already knows its own timezone, and the IANA timezone database that
maps zones to countries is public domain. `Intl.DateTimeFormat().resolvedOptions()
.timeZone` gives "Asia/Kolkata"; this table turns that into IN. No IP is read,
nothing is stored, and a VPN -- which changes an IP but not a clock -- does not
break it.

Inputs : pytz (IANA tz database, public domain)
         babel (Unicode CLDR, Unicode licence) -- territory names and currencies
         openrepair_202507.csv -- for per-country evidence coverage
Output : app_data/geo_lookup.json

Both libraries are BUILD-time only. The API reads the generated JSON.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pandas as pd
import pytz
from babel import Locale
from babel.numbers import get_territory_currencies

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORA = ROOT / "data" / "raw" / "openrepair_202507.csv"
OUT = ROOT / "app_data" / "geo_lookup.json"

# EU-27 plus the three EEA states. Directive (EU) 2024/1799 and the ecodesign
# regulations apply across the EEA; outside it this project makes no legal claim
# at all, which is why the flag exists.
EU27 = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
        "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
        "SI", "ES", "SE"}
EEA_EXTRA = {"IS", "LI", "NO"}
EEA = EU27 | EEA_EXTRA

# ISO 3166 alpha-3 -> alpha-2, for the ORA `country` column which uses alpha-3.
A3_TO_A2 = {
    "GBR": "GB", "NLD": "NL", "BEL": "BE", "DEU": "DE", "DNK": "DK", "FRA": "FR",
    "CAN": "CA", "NZL": "NZ", "AUS": "AU", "ITA": "IT", "USA": "US", "NOR": "NO",
    "ESP": "ES", "JEY": "JE", "AUT": "AT", "SWE": "SE", "ARG": "AR", "ISR": "IL",
    "HKG": "HK", "IRL": "IE", "TUN": "TN", "CHE": "CH", "ISL": "IS", "TWN": "TW",
    "UGA": "UG", "FIN": "FI", "LUX": "LU", "GUF": "GF", "KOR": "KR", "PRT": "PT",
    "ZAF": "ZA", "BEN": "BJ", "IND": "IN",
}


def main() -> None:
    en = Locale("en")

    # ---- timezone -> country -------------------------------------------
    tz_to_country: dict[str, str] = {}
    for cc, zones in pytz.country_timezones.items():
        for z in zones:
            # First writer wins. A handful of zones are claimed by more than one
            # territory; the disputes are between a country and its dependency,
            # and either answer is fine at the granularity we use this for.
            tz_to_country.setdefault(z, cc)

    # ---- country -> currency, name, jurisdiction ------------------------
    countries: dict[str, dict] = {}
    for cc in sorted(pytz.country_names):
        cur = get_territory_currencies(cc)
        countries[cc] = {
            "name": en.territories.get(cc, pytz.country_names[cc]),
            "currency": cur[0] if cur else "USD",
            "in_eea": cc in EEA,
            "in_eu": cc in EU27,
        }

    # ---- evidence coverage ----------------------------------------------
    # How much of the corpus a model would actually be learning from, for
    # someone in this country. The honest answer for most of the world is
    # "none", and the product should say so rather than imply otherwise.
    df = pd.read_csv(ORA, usecols=["country"], low_memory=False)
    counts = df.country.value_counts()
    total = int(len(df))
    for a3, n in counts.items():
        a2 = A3_TO_A2.get(a3)
        if a2 and a2 in countries:
            countries[a2]["ora_records"] = int(n)
            countries[a2]["ora_share"] = round(float(n) / total * 100, 3)
    for cc, meta in countries.items():
        meta.setdefault("ora_records", 0)
        meta.setdefault("ora_share", 0.0)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "sources": {
            "timezones": "IANA tz database via pytz (public domain)",
            "names_currencies": "Unicode CLDR via babel",
            "evidence": f"Open Repair Alliance, {total} records, Oct 2025 release (CC BY-SA 4.0)",
        },
        "ora_total": total,
        "timezone_to_country": tz_to_country,
        "countries": countries,
    }, indent=1, ensure_ascii=False), encoding="utf-8")

    covered = sum(1 for m in countries.values() if m["ora_records"] > 0)
    print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size/1024:.0f} KB)")
    print(f"  timezones mapped : {len(tz_to_country):,}")
    print(f"  countries        : {len(countries)}  ({covered} with any repair evidence)")
    print(f"  EEA countries    : {sum(1 for m in countries.values() if m['in_eea'])}")
    print("\n  spot checks:")
    for tz in ["Asia/Kolkata", "Europe/London", "America/New_York", "Europe/Berlin",
               "Australia/Sydney", "Asia/Dubai"]:
        cc = tz_to_country.get(tz, "?")
        m = countries.get(cc, {})
        print(f"    {tz:<20} -> {cc}  {m.get('name','?'):<16} {m.get('currency','?')}  "
              f"EEA={str(m.get('in_eea')):<5} evidence={m.get('ora_records',0):>7,} "
              f"({m.get('ora_share',0):.2f}%)")


if __name__ == "__main__":
    main()
