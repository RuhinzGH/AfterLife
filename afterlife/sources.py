"""Every dataset this product stands on, and how stale each one is.

WHY THIS IS COMPUTED AND NOT WRITTEN
------------------------------------
A page listing sources is the easiest thing in the world to hand-write, and the
worst thing to hand-write, because it drifts the moment anything is re-pulled
and nobody notices. This project has already been bitten by exactly that: the
CVE corpus went two years without a refresh while the page went on quoting a
confident number, and a second block a few inches below it quoted a different
one.

So nothing here is typed in. Each entry names an artifact on disk, and the
freshness, the row count and the provenance are read out of that artifact's own
fields at request time. A dataset that has not been refreshed says so, in days,
without anyone remembering to update a sentence.

The licence and the URL ARE authored, because they are facts about the source
rather than about our copy of it, and they do not change when we re-pull.

WHAT "STALE" MEANS HERE
-----------------------
Different datasets age at completely different rates and pretending otherwise
would be its own dishonesty. EPSS is refitted daily; the Open Repair Alliance
publishes roughly annually. So each source declares the cadence it is actually
maintained at, and staleness is judged against that rather than against a single
global threshold. An ORA corpus four months old is current. An EPSS file four
months old is broken.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
from typing import Any

APP = pathlib.Path(__file__).resolve().parents[1] / "app_data"

#: key -> (label, file, licence, url, refresh cadence in days, what it decides)
#:
#: `expected_days` is the source's own publication rhythm, not an opinion about
#: how often we feel like updating. Where a feed has no rhythm -- a one-off
#: academic release -- it is None and the entry is never called stale.
SOURCES: list[dict[str, Any]] = [
    {
        "key": "cve",
        "label": "National Vulnerability Database",
        "file": "win10_cve_classified.csv",
        "licence": "Public domain (US Government work)",
        "url": "https://nvd.nist.gov/",
        "expected_days": 31,
        "used_for": "Every security claim on the research page: how many serious "
                    "Windows flaws exist, and how many need an attacker already "
                    "on the device.",
    },
    {
        "key": "kev",
        "label": "CISA Known Exploited Vulnerabilities",
        "file": "kev_summary.json",
        "licence": "Public domain (US Government work)",
        "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
        "expected_days": 14,
        "used_for": "Separating flaws that COULD be exploited from ones that "
                    "demonstrably have been.",
    },
    {
        "key": "epss",
        "label": "FIRST Exploit Prediction Scoring System",
        "file": "epss_summary.json",
        "licence": "Free for any use, attribution requested",
        "url": "https://www.first.org/epss/",
        "expected_days": 7,
        "used_for": "Turning the serious flaws into a distribution with a mass "
                    "and a tail, and testing whether local-access flaws really "
                    "are less exploited.",
    },
    {
        "key": "grid",
        "label": "Our World in Data — grid carbon intensity",
        "file": "grid_intensity.json",
        "licence": "CC BY 4.0",
        "url": "https://ourworldindata.org/grapher/carbon-intensity-electricity",
        "expected_days": 180,
        "used_for": "Whether replacing a device repays its own manufacturing "
                    "carbon, on the grid it is actually plugged into.",
    },
    {
        "key": "carbon",
        "label": "Boavizta — manufacturer LCA declarations",
        "file": "embodied_carbon.json",
        "licence": "Open database, CC BY-SA",
        "url": "https://boavizta.org/",
        "expected_days": 180,
        "used_for": "The embodied carbon of a specific model, where its maker "
                    "published a life-cycle assessment.",
    },
    {
        "key": "survival",
        "label": "Alibaba fail-slow drive dataset",
        "file": "survival_failslow.json",
        "licence": "Open dataset (Tianchi 144479), research use",
        "url": "https://tianchi.aliyun.com/dataset/144479",
        "expected_days": None,      # a one-off academic release
        "used_for": "Whether drive age actually predicts degradation. It does "
                    "not -- which drive model it is matters far more.",
    },
    {
        "key": "support",
        "label": "endoflife.date",
        "file": "device_support.json",
        "licence": "CC BY-SA 4.0",
        "url": "https://endoflife.date/",
        "expected_days": 90,
        "used_for": "When a device or OS stops receiving security updates, and "
                    "whether an extended-updates programme covers it.",
    },
]


def _fetched(path: pathlib.Path) -> tuple[str | None, str]:
    """(date, basis) -- the artifact's own stamp, or the file's mtime.

    Returns the BASIS alongside the date because they are not equally good
    evidence and collapsing them would be the sort of quiet overclaim this
    module exists to prevent. A self-stamp is the pipeline recording when it
    actually pulled. An mtime is whenever the file last happened to be written,
    which a fresh checkout resets -- so on a CI runner every mtime reads as
    today regardless of how old the data is.

    Three artifacts currently have no stamp of their own: the CVE corpus (a CSV,
    with nowhere to put one) and the Boavizta and endoflife.date pulls, whose
    builders record source, url and licence but never a date. Those builders
    should stamp themselves; until they are re-run, mtime is the honest
    second-best and is labelled as such.
    """
    if not path.exists():
        return None, "missing"
    if path.suffix == ".json":
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None, "unreadable"
        for field in ("fetched", "date_released", "generated", "pulled"):
            if isinstance(blob, dict) and blob.get(field):
                return str(blob[field])[:10], "stamp"
    mtime = dt.date.fromtimestamp(path.stat().st_mtime)
    return mtime.isoformat(), "mtime"


def _rows(path: pathlib.Path) -> int | None:
    """How much is actually in it. A source with no volume is a claim, not data."""
    if not path.exists():
        return None
    try:
        if path.suffix == ".csv":
            with path.open(encoding="utf-8") as fh:
                return max(0, sum(1 for _ in fh) - 1)
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if isinstance(blob, dict):
        for field in ("count", "n", "points", "n_drives", "scored_universe",
                      "kev_total", "n_models"):
            if isinstance(blob.get(field), int):
                return blob[field]
        for v in blob.values():
            if isinstance(v, list) and len(v) > 8:
                return len(v)
        for field in ("devices", "countries", "models", "classes"):
            if isinstance(blob.get(field), (list, dict)):
                return len(blob[field])
    elif isinstance(blob, list):
        return len(blob)
    return None


def manifest(as_of: dt.date | None = None) -> dict[str, Any]:
    """Every source, with freshness judged against its OWN refresh cadence."""
    as_of = as_of or dt.date.today()
    out = []

    for s in SOURCES:
        path = APP / s["file"]
        fetched, basis = _fetched(path)
        age_days = None
        if fetched:
            try:
                age_days = (as_of - dt.date.fromisoformat(fetched)).days
            except ValueError:
                age_days = None

        expected = s["expected_days"]
        # Stale only against the cadence the source is actually published at.
        # A single global threshold would call a yearly academic release stale
        # eleven months out of twelve, and let a daily feed rot for a fortnight.
        if expected is None or age_days is None:
            status = "unknown" if age_days is None else "current"
        elif basis == "mtime":
            # An mtime cannot distinguish a fresh pull from a fresh checkout, so
            # it is never used to declare a source CURRENT -- only to rule one
            # out as definitely stale.
            status = "stale" if age_days > expected * 2 else "unverified"
        elif age_days <= expected:
            status = "current"
        elif age_days <= expected * 2:
            status = "ageing"
        else:
            status = "stale"

        out.append({
            "key": s["key"], "label": s["label"], "licence": s["licence"],
            "url": s["url"], "used_for": s["used_for"],
            "present": path.exists(),
            "fetched": fetched, "fetched_basis": basis, "age_days": age_days,
            "expected_days": expected, "status": status,
            "rows": _rows(path),
        })

    counts: dict[str, int] = {}
    for row in out:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    return {
        "as_of": as_of.isoformat(),
        "total": len(out),
        "by_status": counts,
        "note": "Freshness is read from each artifact's own stamp and judged "
                "against that source's publication rhythm, not against one "
                "global threshold. Nothing on this page is typed in by hand.",
        "sources": out,
    }
