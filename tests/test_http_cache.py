"""The rate limiter and the disk cache every data pull in this project sits on.

Small, shared, and untested -- which is the combination that lets a bug reach
every dataset at once. Two things matter here and nothing else does:

  the limiter must not exceed its window, because NVD answers 403 under load
  rather than 429, and a pull that trips it looks like a network failure;

  the cache key must separate requests that differ only by query parameters,
  because every paged NVD pull is the same URL with a different startIndex. A
  key that ignored params would serve page one for all ninety pages and the
  corpus would be silently, plausibly wrong.
"""
from __future__ import annotations

import json
import time

import pytest

from afterlife.http_cache import RateLimiter, _cache_path, get_json


class TestRateLimiter:
    def test_it_does_not_block_below_the_limit(self):
        rl = RateLimiter(calls=5, per_seconds=30)
        start = time.monotonic()
        for _ in range(5):
            rl.wait()
        assert time.monotonic() - start < 0.5

    def test_it_blocks_once_the_window_is_full(self):
        """NVD allows 5 requests / 30s unauthenticated and answers 403 rather
        than 429 when that is exceeded, so overrunning reads as an outage."""
        rl = RateLimiter(calls=2, per_seconds=0.6)
        start = time.monotonic()
        for _ in range(3):
            rl.wait()
        assert time.monotonic() - start >= 0.5

    def test_the_window_reopens(self):
        rl = RateLimiter(calls=1, per_seconds=0.3)
        rl.wait()
        time.sleep(0.4)
        start = time.monotonic()
        rl.wait()
        assert time.monotonic() - start < 0.2

    def test_each_limiter_keeps_its_own_budget(self):
        """nvd and vulnrichment hold separate limiters against separate hosts;
        sharing state would make one starve the other."""
        a, b = RateLimiter(calls=1, per_seconds=5), RateLimiter(calls=1, per_seconds=5)
        a.wait()
        start = time.monotonic()
        b.wait()
        assert time.monotonic() - start < 0.2


class TestCacheKey:
    def test_params_change_the_key(self):
        """The bug this prevents is the expensive one: every paged NVD pull is
        one URL with a different startIndex, so a key that ignored params would
        serve page one ninety times and produce a corpus that looks complete."""
        url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
        assert _cache_path(url, {"startIndex": 0}) != _cache_path(url, {"startIndex": 2000})

    def test_the_same_request_is_the_same_key(self):
        url = "https://example.test/x"
        assert _cache_path(url, {"a": 1, "b": 2}) == _cache_path(url, {"a": 1, "b": 2})

    def test_parameter_order_does_not_matter(self):
        """Otherwise the cache misses on requests that are genuinely identical."""
        url = "https://example.test/x"
        assert _cache_path(url, {"a": 1, "b": 2}) == _cache_path(url, {"b": 2, "a": 1})

    def test_no_params_and_empty_params_agree(self):
        url = "https://example.test/x"
        assert _cache_path(url, None) == _cache_path(url, {})

    def test_different_urls_differ(self):
        assert _cache_path("https://a.test/", None) != _cache_path("https://b.test/", None)


class TestCacheBehaviour:
    def test_a_cached_response_is_served_without_a_request(self, tmp_path, monkeypatch):
        """The whole reason re-running a pipeline is free."""
        # monkeypatch.setattr on the module attribute is enough: _cache_path
        # reads CACHE_DIR at call time. Writing to __globals__ directly, as an
        # earlier draft of this did, does the same thing permanently -- it
        # survives the test and leaks the temp path into every later one.
        monkeypatch.setattr("afterlife.http_cache.CACHE_DIR", tmp_path)
        url = "https://example.test/cached"
        path = _cache_path(url, None)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"from": "disk"}), encoding="utf-8")

        def explode(*a, **k):
            raise AssertionError("a cached URL must not reach the network")
        monkeypatch.setattr("afterlife.http_cache.requests.get", explode)

        assert get_json(url) == {"from": "disk"}

    def test_a_failed_request_is_not_cached(self, tmp_path, monkeypatch):
        """Caching an error would make one bad afternoon permanent."""
        monkeypatch.setattr("afterlife.http_cache.CACHE_DIR", tmp_path)
        url = "https://example.test/fails"

        class Resp:
            status_code = 500
            headers = {"content-type": "application/json"}
            def raise_for_status(self):
                raise RuntimeError("500")

        monkeypatch.setattr("afterlife.http_cache.requests.get", lambda *a, **k: Resp())
        monkeypatch.setattr("afterlife.http_cache.time.sleep", lambda *_: None)
        with pytest.raises(Exception):
            get_json(url, max_retries=2)
        assert not _cache_path(url, None).exists()
