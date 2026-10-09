"""Exploit probability, as a counterweight to severity.

WHAT THIS ADDS THAT THE CORPUS DID NOT HAVE
-------------------------------------------
Afterlife already answers two questions per CVE:

    severity     how bad would this be if exploited          (CVSS, an opinion)
    exploited    has anyone been seen doing it               (CISA KEV, an observation)

Both are useful and both are blunt at the ends. Severity is an opinion about a
hypothetical, and thousands of the Windows 10 corpus are HIGH or CRITICAL -- a set
that large cannot prioritise anything. KEV is an observation, so it is
trustworthy, but only a small fraction of them are in it, and absence from KEV is not evidence
of safety, only that no report reached CISA.

EPSS fills the gap between them: a probability, per CVE, that exploitation will
be observed in the next 30 days, fitted by FIRST on real exploitation telemetry.
It turns "thousands of serious flaws" into a distribution with a mass and a tail.

WHY IT MATTERS TO *THIS* PRODUCT SPECIFICALLY
---------------------------------------------
Afterlife's central claim is that security-driven retirement is often
carbon-irrational, because most of the risk is mitigable without new hardware --
and in particular that a majority of serious Windows CVEs need an attacker who
is already on the device.

That claim is currently structural: it reads the CVSS attack vector and counts.
EPSS makes it *falsifiable*. If locally-exploitable CVEs turn out to carry the
same exploitation probability as remote ones, the argument weakens and the
product should say so. `scripts/enrich_cve_epss.py` computes exactly that
comparison and writes it out whether or not it flatters the thesis.

HOW TO READ A SCORE, AND HOW NOT TO
-----------------------------------
An EPSS score is a probability of *observed exploitation activity* in the next
30 days. It is not a probability that a given device will be compromised, it
says nothing about impact if it is, and it is a forecast that moves daily. It
complements severity; it does not replace it. A low-EPSS critical flaw in
something internet-facing is still worth patching.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

APP_DATA = pathlib.Path(__file__).resolve().parents[1] / "app_data"
SUMMARY = APP_DATA / "epss_summary.json"

#: Presentation bands. These are authored thresholds for describing a score in
#: words, not decision rules and not fitted -- flagged here the same way the
#: blend-score constants are.
#:
#: The 0.10 boundary is the one with a basis: FIRST's own analysis puts the
#: threshold that best balances effort against coverage in that region, and it
#: is the value most published EPSS guidance uses for "act on this". The others
#: are round numbers chosen to describe the distribution's shape.
BANDS: list[tuple[float, str, str]] = [
    (0.10, "elevated", "Exploitation activity is likely enough to act on now"),
    (0.01, "moderate", "Some exploitation risk; patch on the normal cycle"),
    (0.001, "low", "Exploitation is unlikely in the next month"),
    (0.0, "negligible", "No meaningful exploitation signal"),
]

ACT_THRESHOLD = 0.10


def band(score: float | None) -> tuple[str, str]:
    """Describe a score in words. Unknown is its own answer, never 'negligible'."""
    if score is None:
        return "unknown", "No EPSS score published for this vulnerability"
    for floor, name, blurb in BANDS:
        if score >= floor:
            return name, blurb
    return "negligible", BANDS[-1][2]


def expected_exploited(scores: list[float]) -> float:
    """Sum of probabilities = expected number seen exploited in 30 days.

    Sound because expectation is linear -- it needs no independence assumption
    between CVEs, which is just as well, since they are plainly not independent.
    It is an expectation, not a prediction: the realised count will differ.
    """
    return round(sum(scores), 1)


def load_summary() -> dict[str, Any] | None:
    """The committed summary, or None if the enrichment has never run."""
    if not SUMMARY.exists():
        return None
    try:
        return json.loads(SUMMARY.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
