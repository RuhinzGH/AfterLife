"""Tag the classified CVE corpus with CISA's Known Exploited Vulnerabilities.

Why this is worth having: "serious" is CVSS's opinion about how bad a flaw would
be if exploited. KEV is an observation that it *has* been exploited, in the
wild, against real targets. Those are different claims, and the page currently
only makes the weaker one. This is also the operational form of the EPSS finding
in the literature review -- severity alone triages badly.

Adds two columns to each win{major}_cve_classified.csv:

    known_exploited   in CISA's catalogue
    ransomware        CISA has tied it to a known ransomware campaign

Written back in place and idempotent, so re-running after a corpus refresh is
safe. Deliberately does NOT rebuild the corpus -- that means re-querying NVD
across every release variant, which is slow and rate-limited, and nothing about
the NVD data changes here.

    python scripts/enrich_cve_kev.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

FEED = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
APP = ROOT / "app_data"
MAJORS = ("10", "11")
NEW_COLUMNS = ["known_exploited", "ransomware"]


def fetch() -> dict:
    r = requests.get(FEED, headers={"User-Agent": "Afterlife-research/0.1"}, timeout=120)
    r.raise_for_status()
    return r.json()


def main() -> None:
    print(f"GET {FEED}")
    kev = fetch()
    vulns = kev.get("vulnerabilities", [])
    if not vulns:
        raise SystemExit("KEV feed returned no vulnerabilities -- refusing to write")

    exploited = {v["cveID"] for v in vulns}
    ransomware = {v["cveID"] for v in vulns
                  if str(v.get("knownRansomwareCampaignUse", "")).strip().lower() == "known"}
    print(f"catalogue {kev.get('catalogVersion')} "
          f"released {str(kev.get('dateReleased', ''))[:10]}: "
          f"{len(exploited):,} known-exploited, {len(ransomware):,} tied to ransomware")

    summary = {
        "source": "CISA Known Exploited Vulnerabilities Catalog",
        "url": FEED,
        "catalog_version": kev.get("catalogVersion"),
        "date_released": str(kev.get("dateReleased", ""))[:10],
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "kev_total": len(exploited),
        "kev_ransomware": len(ransomware),
        # Counting caveat, stated because it bounds every number downstream: KEV
        # records exploitation that somebody observed and reported. Absence from
        # it is not evidence a flaw is unexploited, only that no report reached
        # CISA. So these counts are a floor, never a total.
        "caveat": "KEV records observed, reported exploitation. Absence is not evidence of "
                  "safety -- treat every count here as a floor, not a total.",
        "by_version": {},
    }

    for major in MAJORS:
        path = APP / f"win{major}_cve_classified.csv"
        if not path.exists():
            print(f"  skip Windows {major}: {path.name} not present")
            continue

        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = [c for c in (reader.fieldnames or []) if c not in NEW_COLUMNS]
            rows = list(reader)

        hits = ransom_hits = serious_hits = 0
        for row in rows:
            cid = row.get("cve_id", "")
            is_kev = cid in exploited
            row["known_exploited"] = "true" if is_kev else "false"
            row["ransomware"] = "true" if cid in ransomware else "false"
            hits += is_kev
            ransom_hits += cid in ransomware
            if is_kev and (row.get("severity") or "").upper() in ("HIGH", "CRITICAL"):
                serious_hits += 1

        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames + NEW_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        summary["by_version"][major] = {
            "total": len(rows),
            "known_exploited": hits,
            "serious_known_exploited": serious_hits,
            "ransomware": ransom_hits,
        }
        print(f"  Windows {major}: {hits:,} of {len(rows):,} known-exploited "
              f"({serious_hits:,} of them serious, {ransom_hits:,} ransomware-linked)")

    out = APP / "kev_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
