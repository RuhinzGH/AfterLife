"""Disk-cached, rate-limited HTTP GET.

NVD allows 5 requests / 30s without an API key (50 with one), and endoflife.date
asks for light use. Every response is cached to data/cache keyed by URL+params so
re-running the pipeline costs nothing.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Afterlife-research/0.1 (device lifecycle study; contact: student project)"


class RateLimiter:
    def __init__(self, calls: int, per_seconds: float) -> None:
        self.calls = calls
        self.per_seconds = per_seconds
        self._hits: list[float] = []

    def wait(self) -> None:
        now = time.monotonic()
        self._hits = [t for t in self._hits if now - t < self.per_seconds]
        if len(self._hits) >= self.calls:
            sleep_for = self.per_seconds - (now - self._hits[0]) + 0.25
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._hits = []
        self._hits.append(time.monotonic())


def _cache_path(url: str, params: dict[str, Any] | None) -> Path:
    key = url + "|" + json.dumps(params or {}, sort_keys=True)
    return CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"


def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    limiter: RateLimiter | None = None,
    headers: dict[str, str] | None = None,
    max_retries: int = 4,
) -> Any:
    path = _cache_path(url, params)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    last_error: Exception | None = None

    for attempt in range(max_retries):
        if limiter:
            limiter.wait()
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=60)
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(2**attempt)
            continue

        # NVD returns 403/503 under load rather than 429.
        if resp.status_code in (403, 429, 503):
            last_error = RuntimeError(f"{resp.status_code} from {url}")
            time.sleep(6 * (attempt + 1))
            continue

        resp.raise_for_status()
        payload = resp.json()
        path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    raise RuntimeError(f"GET failed after {max_retries} attempts: {url}") from last_error
