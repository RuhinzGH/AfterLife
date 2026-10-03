"""Build a classified CVE corpus for one Windows major version.

Supersedes the single-CPE pull in analyze_eol_os.py, which quietly undercounts.
NVD does not file Windows CVEs under one product name -- it splits them per
release, so `cpe:2.3:o:microsoft:windows_11` returns 599 records while the
per-release names together hold several thousand. Querying only the base name
looks like it worked and silently misses most of the data.

So: query every release variant, deduplicate by CVE ID (a flaw affecting 22H2,
23H2 and 24H2 is one flaw, not three), then classify each one through
mitigation.classify.

    venv/Scripts/python scripts/build_cve_corpus.py --major 11
    venv/Scripts/python scripts/build_cve_corpus.py --major 10
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from afterlife import vulnrichment
from afterlife.mitigation import classify
from afterlife.nvd import iter_cves

OUT_DIR = ROOT / "app_data"

# Release names NVD actually files under, per major version.
VARIANTS = {
    "10": ["windows_10", "windows_10_1507", "windows_10_1511", "windows_10_1607",
           "windows_10_1703", "windows_10_1709", "windows_10_1803", "windows_10_1809",
           "windows_10_1903", "windows_10_1909", "windows_10_2004", "windows_10_20h2",
           "windows_10_21h1", "windows_10_21h2", "windows_10_22h2"],
    "11": ["windows_11", "windows_11_21h2", "windows_11_22h2", "windows_11_23h2",
           "windows_11_24h2", "windows_11_25h2"],
}

FIELDS = ["cve_id", "published", "severity", "base_score", "attack_vector",
          "privileges_required", "app_layer", "mitigation_class", "component",
          "action", "source", "metric_source", "metric_version"]


def _backfill(rows: list[dict], limit: int | None = None) -> dict[str, int]:
    """Recover vectors NVD never supplied, via CISA's Vulnrichment.

    A row with no attack_vector cannot be classified, so it vanishes from every
    share the research page computes -- silently, because a smaller denominator
    still divides cleanly. Since NIST stopped enriching the backlog in April
    2026 this stops being a rounding error and starts being a trend, so the
    rebuild now tries to fill the gap and *reports* how many it could not.
    """
    unscored = [r for r in rows if not r["attack_vector"]]
    if not unscored:
        return {"attempted": 0, "recovered": 0, "still_missing": 0}

    if limit is not None:
        unscored = unscored[:limit]

    recovered = 0
    print(f"\n  {len(unscored)} rows carry no CVSS vector -- asking Vulnrichment")
    for row in unscored:
        found = vulnrichment.lookup(row["cve_id"])
        if not found or not found.get("attack_vector"):
            continue
        row.update({
            "severity": found["severity"] or "",
            "base_score": found["base_score"] if found["base_score"] is not None else "",
            "attack_vector": found["attack_vector"],
            "privileges_required": found["privileges_required"] or "",
            "metric_source": found["metric_source"],
            "metric_version": found["metric_version"] or "",
        })
        # Only one classification can change when a vector arrives late. The
        # app-layer and service-catalogue branches of mitigation.classify read
        # the description and CPEs, which were always present, so they already
        # gave their final answer. The two branches that read the vector are the
        # last two -- and with os_upgradable=False the only reachable transition
        # is unmitigable -> network_isolate. Re-deriving that here is equivalent
        # to re-running classify, without rebuilding a Vuln from a CSV row.
        if (row["mitigation_class"] == "unmitigable"
                and found["attack_vector"] in ("NETWORK", "ADJACENT_NETWORK")
                and found["privileges_required"] == "NONE"):
            row["mitigation_class"] = "network_isolate"
            row["component"] = "network"
            row["action"] = ("Segment to a restricted VLAN and block inbound access "
                             "at the host firewall")
        recovered += 1

    still = sum(1 for r in rows if not r["attack_vector"])
    print(f"  recovered {recovered}; {still} remain unscored by anyone")
    return {"attempted": len(unscored), "recovered": recovered, "still_missing": still}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--major", default="11", choices=sorted(VARIANTS))
    ap.add_argument("--since", default=None,
                    help="only CVEs published on/after (default: all)")
    ap.add_argument("--max-records", type=int, default=None)
    ap.add_argument("--no-backfill", action="store_true",
                    help="skip the Vulnrichment pass for CVEs NVD never scored")
    args = ap.parse_args()

    import datetime as dt
    since = dt.date.fromisoformat(args.since) if args.since else None

    seen: dict[str, dict] = {}
    for variant in VARIANTS[args.major]:
        cpe = f"cpe:2.3:o:microsoft:{variant}"
        before = len(seen)
        try:
            for v in iter_cves(cpe, published_after=since, max_records=args.max_records):
                if v.cve_id in seen:
                    continue
                # os_upgradable=False is the deliberate worst case: assume the
                # hardware cannot take a newer OS, so "just upgrade" is never
                # counted as an available fix. Anything we report as mitigable is
                # mitigable even on a machine that is stuck where it is.
                m = classify(v, os_upgradable=False)
                seen[v.cve_id] = {
                    "cve_id": v.cve_id,
                    "published": v.published.isoformat() if v.published else "",
                    "severity": v.severity or "",
                    "base_score": v.base_score if v.base_score is not None else "",
                    "attack_vector": v.attack_vector or "",
                    "privileges_required": v.privileges_required or "",
                    "app_layer": v.is_application_layer,
                    "mitigation_class": m.klass.value,
                    "component": m.component or "",
                    "action": m.action,
                    "source": m.source or "",
                    "metric_source": v.metric_source or "",
                    "metric_version": v.metric_version or "",
                }
        except Exception as exc:  # noqa: BLE001
            print(f"  {variant:<22} FAILED: {type(exc).__name__}: {exc}")
            continue
        print(f"  {variant:<22} +{len(seen) - before:>5} new  (running total {len(seen)})")
        time.sleep(1)

    if not seen:
        print("nothing pulled -- aborting rather than writing an empty corpus")
        raise SystemExit(1)

    rows = sorted(seen.values(), key=lambda r: r["cve_id"])

    if not args.no_backfill:
        _backfill(rows)

    out = OUT_DIR / f"win{args.major}_cve_classified.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    serious = [r for r in rows if r["severity"] in ("HIGH", "CRITICAL")]
    dates = sorted(r["published"] for r in rows if r["published"])
    print(f"\nwrote {out.relative_to(ROOT)}")
    print(f"  {len(rows):,} unique CVEs  ({len(serious):,} HIGH/CRITICAL)")
    if dates:
        print(f"  published {dates[0]} -> {dates[-1]}")
    from collections import Counter
    for k, n in Counter(r["mitigation_class"] for r in serious).most_common():
        print(f"    {k:<18} {n:>5}")

    # Who actually scored this corpus. NIST's April 2026 retreat means this
    # ratio will drift, and a drift nobody is looking at is how the last stale
    # corpus survived two years.
    prov = Counter(r["metric_source"] or "(unscored)" for r in rows)
    nist = prov.get("nvd@nist.gov", 0)
    print(f"\n  scored by NIST: {nist:,} of {len(rows):,} ({nist / len(rows):.1%})")
    for src, n in prov.most_common():
        if src != "nvd@nist.gov":
            print(f"    {src:<28} {n:>5}")

    print("\n  NEXT: python scripts/enrich_cve_kev.py "
          "-- the corpus has no known_exploited column until it runs, "
          "and tests/test_findings.py will refuse it.")


if __name__ == "__main__":
    main()
