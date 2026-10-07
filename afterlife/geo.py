"""Where the user is, and what that changes about the answer.

Country is resolved from the browser's own timezone -- not from the visitor's IP.
`Intl.DateTimeFormat().resolvedOptions().timeZone` returns "Asia/Kolkata"; the
IANA database that maps that to IN is public domain. No IP is read, none is
stored, and a VPN (which changes an IP but not a clock) does not defeat it.

Three things depend on the answer, and the third is the one that matters most:

  currency  -- the resale estimate was defaulting to USD for everyone.
  rights    -- repair_rights.py makes claims about EU/EEA law only, and says so
               in its own docstring. Until now the API called it without a
               country, so a user in India was shown entitlements that do not
               exist for them. That is the failure mode that module was
               explicitly written to avoid, reintroduced one layer up.
  evidence  -- the repair corpus covers 32 countries and India is not one of
               them. Someone in Delhi is being advised by a model trained on
               305,649 records, none from their country. The product should say
               so. Detecting the country is what makes saying so possible.

The country is always returned to the caller so the interface can show it and
let the user correct it. A wrong country produces wrong legal information, which
is worse than none, so this must never be silent.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, asdict

APP_DATA = pathlib.Path(__file__).resolve().parents[1] / "app_data"
_TABLE: dict | None = None

#: Below this share of the corpus, the repair-history pillar is reported as
#: thinly evidenced for that country rather than presented at face value.
THIN_EVIDENCE_PCT = 1.0


@dataclass(frozen=True)
class GeoContext:
    country: str                 # ISO 3166-1 alpha-2
    country_name: str
    currency: str
    in_eea: bool
    in_eu: bool
    ora_records: int             # repair records from this country
    ora_share: float             # ...as a % of the corpus
    evidence_level: str          # "none" | "thin" | "represented"
    evidence_note: str
    resolved_from: str           # "override" | "timezone" | "default"

    def as_dict(self) -> dict:
        return asdict(self)


def _table() -> dict:
    global _TABLE
    if _TABLE is None:
        p = APP_DATA / "geo_lookup.json"
        _TABLE = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {
            "timezone_to_country": {}, "countries": {}, "ora_total": 0}
    return _TABLE


def _evidence(name: str, records: int, share: float, total: int) -> tuple[str, str]:
    if records == 0:
        return "none", (
            f"No repair records from {name} in the {total:,}-record corpus. The "
            f"repair-history evidence below is drawn entirely from other countries, "
            f"mostly in north-western Europe — treat it as indicative, not local.")
    if share < THIN_EVIDENCE_PCT:
        return "thin", (
            f"Only {records:,} of {total:,} repair records ({share:.2f}%) come from "
            f"{name}. The repair-history evidence is thin for your country.")
    return "represented", (
        f"{records:,} of {total:,} repair records ({share:.1f}%) come from {name}.")


#: Older IANA names that browsers still report for some zones (Chrome on
#: Windows, for one, reports India as "Asia/Calcutta"). Each maps to the current
#: name the lookup table is keyed on. From the IANA tz database's "backward" file.
LEGACY_TIMEZONES = {
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Dacca": "Asia/Dhaka",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Thimbu": "Asia/Thimphu",
    "Asia/Ulan_Bator": "Asia/Ulaanbaatar",
    "Asia/Macao": "Asia/Macau",
    "Asia/Chongqing": "Asia/Shanghai",
    "Asia/Chungking": "Asia/Shanghai",
    "Asia/Harbin": "Asia/Shanghai",
    "Asia/Kashgar": "Asia/Urumqi",
    "Asia/Tel_Aviv": "Asia/Jerusalem",
    "Asia/Istanbul": "Europe/Istanbul",
    "Europe/Kiev": "Europe/Kyiv",
    "Europe/Uzhgorod": "Europe/Kyiv",
    "Europe/Zaporozhye": "Europe/Kyiv",
    "Europe/Belfast": "Europe/London",
    "Europe/Nicosia": "Asia/Nicosia",
    "Atlantic/Faeroe": "Atlantic/Faroe",
    "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
    "America/Catamarca": "America/Argentina/Catamarca",
    "America/Cordoba": "America/Argentina/Cordoba",
    "America/Indianapolis": "America/Indiana/Indianapolis",
    "America/Louisville": "America/Kentucky/Louisville",
    "America/Godthab": "America/Nuuk",
    "Africa/Asmera": "Africa/Asmara",
    "Africa/Timbuktu": "Africa/Bamako",
    "Australia/Canberra": "Australia/Sydney",
    "Australia/ACT": "Australia/Sydney",
    "Pacific/Truk": "Pacific/Chuuk",
    "Pacific/Ponape": "Pacific/Pohnpei",
    "Pacific/Enderbury": "Pacific/Kanton",
    "US/Eastern": "America/New_York",
    "US/Central": "America/Chicago",
    "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles",
    "GB": "Europe/London",
}


def _zone_country(table: dict, timezone: str) -> str | None:
    """Country for a timezone name, trying its current IANA name if it is an old one."""
    tz = timezone.strip()
    return table.get(tz) or table.get(LEGACY_TIMEZONES.get(tz, ""))


def resolve(timezone: str | None = None, country: str | None = None) -> GeoContext:
    """Country override beats timezone; timezone beats nothing.

    An unrecognised timezone or country falls back to a neutral default rather
    than guessing at a neighbour: the caller can tell, because `resolved_from`
    says "default" and the interface can then ask.
    """
    tbl = _table()
    total = tbl.get("ora_total", 0)
    countries = tbl.get("countries", {})

    cc, how = None, "default"
    if country:
        c = country.strip().upper()
        if c in countries:
            cc, how = c, "override"
    if cc is None and timezone:
        cc = _zone_country(tbl.get("timezone_to_country", {}), timezone)
        if cc:
            how = "timezone"

    if cc is None or cc not in countries:
        # Nothing claimed. No currency assumption beyond the neutral default, no
        # legal claim, and evidence reported against the corpus as a whole.
        return GeoContext(
            country="", country_name="Unknown", currency="USD", in_eea=False,
            in_eu=False, ora_records=0, ora_share=0.0, evidence_level="unknown",
            evidence_note=("Country not detected, so no jurisdiction-specific "
                           "information is shown. Set it to see repair rights and "
                           "local evidence coverage."),
            resolved_from="default")

    m = countries[cc]
    level, note = _evidence(m["name"], m["ora_records"], m["ora_share"], total)
    return GeoContext(
        country=cc, country_name=m["name"], currency=m.get("currency", "USD"),
        in_eea=bool(m.get("in_eea")), in_eu=bool(m.get("in_eu")),
        ora_records=int(m.get("ora_records", 0)), ora_share=float(m.get("ora_share", 0.0)),
        evidence_level=level, evidence_note=note, resolved_from=how)
