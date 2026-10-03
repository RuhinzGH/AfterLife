"""Tag the classified CVE corpus with EPSS exploitation probability.

Adds two columns to each win{major}_cve_classified.csv:

    epss              probability of observed exploitation in the next 30 days
    epss_percentile   where that sits against every scored CVE

and writes app_data/epss_summary.json, which the research page reads.

Idempotent and safe to re-run, exactly like enrich_cve_kev.py, and it runs after
it in the same pipeline. One GET: the full current scoreset is a 2.5 MB gzipped
CSV covering every scored CVE, which is far kinder to FIRST than several
thousand per-CVE API calls and cannot half-succeed.

THE TEST THIS SCRIPT RUNS AGAINST THE PRODUCT'S OWN THESIS
----------------------------------------------------------
Afterlife argues that most serious Windows CVEs need an attacker already on the
device, and that this is why an unsupported OS is a mitigable cost rather than a
replace trigger. That argument is structural -- it counts CVSS attack vectors.

EPSS lets it be checked against exploitation data: do locally-exploitable CVEs
actually get exploited less often than remote ones? The comparison is computed
below and written out whichever way it comes out. If it ever inverts, the
finding is that the thesis needs qualifying, and the page should say so rather
than quietly dropping the number.

    python scripts/enrich_cve_epss.py
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests

from afterlife.epss import ACT_THRESHOLD, expected_exploited

FEED = "https://epss.empiricalsecurity.com/epss_scores-current.csv.gz"
APP = ROOT / "app_data"
MAJORS = ("10", "11")
NEW_COLUMNS = ["epss", "epss_percentile"]
SERIOUS = {"HIGH", "CRITICAL"}

REMOTE = {"NETWORK", "ADJACENT_NETWORK"}
LOCAL = {"LOCAL", "PHYSICAL"}


def fetch() -> tuple[dict[str, tuple[float, float]], str]:
    """Every published EPSS score, plus the model version line."""
    print(f"GET {FEED}")
    r = requests.get(FEED, headers={"User-Agent": "Afterlife-research/0.1"}, timeout=180)
    r.raise_for_status()

    raw = gzip.decompress(r.content).decode("utf-8")
    lines = raw.splitlines()
    # The first line is a comment carrying model version and score date, e.g.
    # "#model_version:v2025.03.14,score_date:2026-08-31T00:00:00+0000"
    meta = lines[0].lstrip("#") if lines and lines[0].startswith("#") else ""

    reader = csv.DictReader(io.StringIO("\n".join(lines[1:])))
    scores: dict[str, tuple[float, float]] = {}
    for row in reader:
        try:
            scores[row["cve"]] = (float(row["epss"]), float(row["percentile"]))
        except (KeyError, TypeError, ValueError):
            continue
    return scores, meta


def _slice(rows: list[dict], predicate) -> dict:
    """Mean/median EPSS over a subset, with the count that produced it.

    The count travels with the statistic on purpose. A median over eleven rows
    and a median over four thousand read identically once separated from their
    denominator, and this project has already been bitten by a share quoted
    against the wrong total.
    """
    vals = [float(r["epss"]) for r in rows if predicate(r) and r.get("epss")]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "over_threshold": 0}
    return {
        "n": len(vals),
        "mean": round(statistics.mean(vals), 5),
        "median": round(statistics.median(vals), 5),
        "over_threshold": sum(1 for v in vals if v >= ACT_THRESHOLD),
        "expected_exploited": expected_exploited(vals),
    }


def main() -> None:
    scores, meta = fetch()
    if not scores:
        raise SystemExit("EPSS feed returned no scores -- refusing to write")
    print(f"{len(scores):,} scored CVEs  ({meta})")

    summary = {
        "source": "FIRST Exploit Prediction Scoring System (EPSS)",
        "url": "https://www.first.org/epss/",
        "feed": FEED,
        "model": meta,
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "scored_universe": len(scores),
        "act_threshold": ACT_THRESHOLD,
        "meaning": "Probability that exploitation activity is OBSERVED in the next 30 "
                   "days. Not a probability that this device is compromised, and it "
                   "says nothing about impact. A forecast, refreshed daily.",
        "caveat": "EPSS complements severity, it does not replace it. A low-EPSS "
                  "critical flaw in an exposed service is still worth patching.",
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

        matched = 0
        for row in rows:
            hit = scores.get(row.get("cve_id", ""))
            if hit:
                row["epss"], row["epss_percentile"] = f"{hit[0]:.6f}", f"{hit[1]:.6f}"
                matched += 1
            else:
                row["epss"] = row["epss_percentile"] = ""

        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames + NEW_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

        serious = [r for r in rows if (r.get("severity") or "").upper() in SERIOUS]

        # The falsifiable check. Structural claim: serious CVEs needing local
        # access are less urgent. Does exploitation data agree?
        local = _slice(serious, lambda r: (r.get("attack_vector") or "").upper() in LOCAL)
        remote = _slice(serious, lambda r: (r.get("attack_vector") or "").upper() in REMOTE)
        thesis_holds = (
            local["median"] is not None and remote["median"] is not None
            and local["median"] < remote["median"]
        )

        summary["by_version"][major] = {
            "total": len(rows),
            "scored": matched,
            "unscored": len(rows) - matched,
            "serious": len(serious),
            "all": _slice(rows, lambda r: True),
            "serious_all": _slice(serious, lambda r: True),
            "serious_local": local,
            "serious_remote": remote,
            "serious_kev": _slice(serious, lambda r: r.get("known_exploited") == "true"),
            "local_less_exploited_than_remote": thesis_holds,
        }

        print(f"\n  Windows {major}: {matched:,} of {len(rows):,} carry an EPSS score")
        print(f"    serious, median EPSS      {serious and summary['by_version'][major]['serious_all']['median']}")
        print(f"    serious local  (n={local['n']:>4})  median {local['median']}")
        print(f"    serious remote (n={remote['n']:>4})  median {remote['median']}")
        print(f"    thesis (local < remote):  {'HOLDS' if thesis_holds else 'DOES NOT HOLD'}")
        print(f"    expected exploited in 30d: "
              f"{summary['by_version'][major]['serious_all']['expected_exploited']} "
              f"of {len(serious):,} serious")

    out = APP / "epss_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
