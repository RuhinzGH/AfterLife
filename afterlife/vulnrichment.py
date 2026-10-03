"""Recover a CVSS vector for CVEs that NVD never scored.

WHY THIS MODULE EXISTS
----------------------
In April 2026 NIST formally gave up on the NVD enrichment backlog. It will not
enrich any CVE with an NVD publish date earlier than 2026-03-01, everything
older was moved to a "Deferred" state, and going forward NIST prioritises only
three classes: CVEs already in CISA's KEV catalogue, CVEs in federal software,
and CVEs in critical software. Everything else is marked "Not Scheduled" and
carries whatever the CNA supplied -- or nothing at all.

Afterlife reasons over `attackVector` and `privilegesRequired`. A CVE with no
CVSS vector cannot be classified at all: it is not "low risk", it is *unknown*,
and it silently drops out of every denominator on the research page. That is the
exact failure this project already caught once, where a stale corpus let the site
assert 1,513 serious CVEs while the real figure was 4,809.

The gap-filler is CISA's Vulnrichment programme. CISA is the CVE Program's first
Authorized Data Publisher, and it writes SSVC decision points and -- where it can
determine them -- CVSS and CWE data into an ADP container inside the CVE record
itself. That record is served by the CVE Program's own API, so one GET per
unscored CVE recovers what NVD no longer provides.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not overwrite a score that already exists, and it does not launder the
result. A vector recovered here is tagged with its real source in the corpus
(`metric_source`), so a row scored by CISA-ADP or by Microsoft is distinguishable
from one scored by NIST forever after. Mixing them silently would make the
corpus's provenance unrecoverable, which is worse than the missing data.
"""
from __future__ import annotations

from typing import Any

from .http_cache import RateLimiter, get_json

#: The CVE Program's own record store. Unauthenticated, no key required. Carries
#: the CNA container plus every ADP container, which is where CISA writes.
ENDPOINT = "https://cveawg.mitre.org/api/cve"

#: No published limit, but this is a courtesy service run for the whole industry
#: and we only ever call it for the handful of rows NVD left empty.
_LIMITER = RateLimiter(calls=10, per_seconds=10)

#: CVSS containers inside a CVE record, newest first. Same preference order as
#: afterlife.nvd, so a recovered row is comparable with a natively-scored one.
_CVSS_KEYS = ("cvssV4_0", "cvssV3_1", "cvssV3_0")

_CISA_ADP = "cisa-adp"


def _vector_from(metric: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    for key in _CVSS_KEYS:
        data = metric.get(key)
        if isinstance(data, dict) and data.get("baseScore") is not None:
            return data, key.replace("cvssV", "").replace("_", ".")
    return None


def _containers(record: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """Every scoring container in the record, CISA's ADP first.

    CISA is preferred over the CNA not because it is more authoritative about
    the product -- the vendor obviously knows its own software better -- but
    because it is the neutral party. When both have scored, a vendor's rating of
    its own flaw is the one worth flagging, and preferring CISA keeps the corpus
    consistent with the "who says so" question the provenance field exists to
    answer.
    """
    out: list[tuple[dict[str, Any], str]] = []
    containers = record.get("containers", {}) or {}

    for adp in containers.get("adp", []) or []:
        provider = ((adp.get("providerMetadata") or {}).get("shortName") or "").lower()
        for metric in adp.get("metrics", []) or []:
            out.append((metric, f"adp:{provider}" if provider else "adp"))

    cna = containers.get("cna", {}) or {}
    provider = ((cna.get("providerMetadata") or {}).get("shortName") or "").lower()
    for metric in cna.get("metrics", []) or []:
        out.append((metric, f"cna:{provider}" if provider else "cna"))

    out.sort(key=lambda pair: 0 if pair[1] == f"adp:{_CISA_ADP}" else 1)
    return out


def lookup(cve_id: str) -> dict[str, Any] | None:
    """Best available CVSS vector for one CVE, or None if nobody has scored it.

    Returns the same field names afterlife.nvd.Vuln uses, plus `metric_source`
    identifying which container it came from. Never raises: a lookup failure for
    one CVE must not abort a corpus rebuild of several thousand.
    """
    try:
        record = get_json(f"{ENDPOINT}/{cve_id}", limiter=_LIMITER)
    except Exception:  # noqa: BLE001 -- see docstring
        return None

    for metric, origin in _containers(record):
        found = _vector_from(metric)
        if not found:
            continue
        data, version = found
        return {
            "base_score": data.get("baseScore"),
            "severity": (data.get("baseSeverity") or "").upper() or None,
            "attack_vector": (data.get("attackVector") or "").upper() or None,
            "privileges_required": (data.get("privilegesRequired") or "").upper() or None,
            "user_interaction": (data.get("userInteraction") or "").upper() or None,
            "scope": (data.get("scope") or "").upper() or None,
            "metric_source": origin,
            "metric_type": "Secondary",
            "metric_version": version,
        }
    return None
