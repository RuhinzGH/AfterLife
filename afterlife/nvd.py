"""NVD 2.0 client — pull CVEs for a CPE and flatten to the fields we reason over."""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from typing import Any, Iterator

from .http_cache import RateLimiter, get_json

ENDPOINT = "https://services.nvd.nist.gov/rest/json/cves/2.0"
PAGE_SIZE = 2000  # NVD's maximum

# 5 req/30s anonymous, 50 with a key. Set NVD_API_KEY to go faster.
_API_KEY = os.environ.get("NVD_API_KEY")
_LIMITER = RateLimiter(calls=45 if _API_KEY else 5, per_seconds=30)


@dataclass
class Vuln:
    cve_id: str
    published: dt.date | None
    description: str
    base_score: float | None
    severity: str | None
    attack_vector: str | None       # NETWORK | ADJACENT_NETWORK | LOCAL | PHYSICAL
    privileges_required: str | None  # NONE | LOW | HIGH
    user_interaction: str | None     # NONE | REQUIRED
    scope: str | None                # UNCHANGED | CHANGED
    # WHO scored this, not just what the score was. See _primary_metric.
    metric_source: str | None = None   # 'nvd@nist.gov' | 'secure@microsoft.com' | ...
    metric_type: str | None = None     # 'Primary' | 'Secondary'
    metric_version: str | None = None  # '4.0' | '3.1' | '3.0'
    cpe_parts: set[str] = field(default_factory=set)   # {'o', 'a', 'h'}
    cpe_criteria: list[str] = field(default_factory=list)

    @property
    def nist_scored(self) -> bool:
        """Did NIST itself assign this severity, or did we inherit the vendor's?

        From April 2026 NIST stopped routinely enriching CVEs -- it will not
        enrich anything published before 2026-03-01, and now leans on the scores
        CNAs supply. Microsoft is a CNA and self-scores, so this corpus keeps
        working; but the *basis* of every severity silently shifts from NIST to
        the vendor whose product is being scored, and a vendor rating its own
        flaw is a materially different claim.

        Nothing recorded that shift before this field existed. Now it is on every
        row, the way embodied_carbon.py already reports whether a carbon figure
        was matched or class-median.
        """
        return (self.metric_source or "").lower() == "nvd@nist.gov"

    @property
    def is_application_layer(self) -> bool:
        """Vulnerable component is an application, not the OS itself.

        Application CVEs are fixable by updating that application, independent of
        whether the OS still receives updates — so they never justify replacing
        hardware.
        """
        return "a" in self.cpe_parts and "o" not in self.cpe_parts

    @property
    def remotely_reachable(self) -> bool:
        return self.attack_vector in ("NETWORK", "ADJACENT_NETWORK")

    @property
    def requires_local_access(self) -> bool:
        return self.attack_vector in ("LOCAL", "PHYSICAL")


#: CVSS containers in NVD's response, newest first.
_METRIC_KEYS = ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30")

_NIST = "nvd@nist.gov"


def _primary_metric(metrics: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pick a CVSS metric and report which one was picked.

    Preference order is NIST's own score, then any Primary, then whatever is
    first -- unchanged from before. What is new is the second return value: the
    provenance of the metric actually used.

    The old version collapsed all three cases into one anonymous dict, so a
    corpus scored entirely by vendors was indistinguishable from one scored by
    NIST. That distinction stopped being hypothetical in April 2026.
    """
    for key in _METRIC_KEYS:
        entries = metrics.get(key) or []
        if not entries:
            continue
        chosen = (
            next((e for e in entries if (e.get("source") or "").lower() == _NIST), None)
            or next((e for e in entries if e.get("type") == "Primary"), None)
            or entries[0]
        )
        data = chosen.get("cvssData", {}) or {}
        meta = {
            "source": chosen.get("source"),
            "type": chosen.get("type"),
            "version": data.get("version") or key.replace("cvssMetricV", ""),
        }
        return data, meta
    return {}, {}


def _flatten(raw: dict[str, Any]) -> Vuln:
    cve = raw["cve"]
    data, meta = _primary_metric(cve.get("metrics", {}))

    parts: set[str] = set()
    criteria: list[str] = []
    for config in cve.get("configurations", []) or []:
        for node in config.get("nodes", []) or []:
            for match in node.get("cpeMatch", []) or []:
                if not match.get("vulnerable"):
                    continue
                crit = match.get("criteria", "")
                criteria.append(crit)
                bits = crit.split(":")
                if len(bits) > 2:
                    parts.add(bits[2])

    published = None
    if raw_pub := cve.get("published"):
        try:
            published = dt.datetime.fromisoformat(raw_pub).date()
        except ValueError:
            pass

    desc = next(
        (d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"), ""
    )

    return Vuln(
        cve_id=cve["id"],
        published=published,
        description=desc,
        base_score=data.get("baseScore"),
        severity=data.get("baseSeverity"),
        attack_vector=data.get("attackVector"),
        privileges_required=data.get("privilegesRequired"),
        user_interaction=data.get("userInteraction"),
        scope=data.get("scope"),
        metric_source=meta.get("source"),
        metric_type=meta.get("type"),
        metric_version=meta.get("version"),
        cpe_parts=parts,
        cpe_criteria=criteria,
    )


def iter_cves(
    cpe_prefix: str,
    published_after: dt.date | None = None,
    max_records: int | None = None,
) -> Iterator[Vuln]:
    """Page through every CVE matching a CPE prefix (e.g. cpe:2.3:o:microsoft:windows_10).

    NVD rejects pubStartDate/pubEndDate spans wider than 120 days, so published_after
    is applied client-side rather than as a query parameter.
    """
    headers = {"apiKey": _API_KEY} if _API_KEY else None
    start, emitted = 0, 0

    while True:
        params: dict[str, Any] = {
            "virtualMatchString": cpe_prefix,
            "resultsPerPage": PAGE_SIZE,
            "startIndex": start,
        }

        payload = get_json(ENDPOINT, params=params, limiter=_LIMITER, headers=headers)
        total = payload.get("totalResults", 0)
        batch = payload.get("vulnerabilities", []) or []
        if not batch:
            return

        for raw in batch:
            vuln = _flatten(raw)
            if published_after and (vuln.published is None or vuln.published < published_after):
                continue
            yield vuln
            emitted += 1
            if max_records and emitted >= max_records:
                return

        start += len(batch)
        if start >= total:
            return
