"""The key-value store behaves the same whether Redis is there or not.

These run against the in-process fallback (no REDIS_URL in CI), which is exactly
the path that has to stay correct -- it is what local development and every test
uses. The Redis path is the same contract with expiry and atomicity moved into
the server.
"""
from __future__ import annotations

import time

import pytest

from afterlife import kvstore as K


@pytest.fixture(autouse=True)
def clean():
    K.reset()
    yield
    K.reset()


def test_put_get_roundtrip():
    K.put("k", {"a": 1, "b": [2, 3]}, ttl=60)
    assert K.get("k") == {"a": 1, "b": [2, 3]}


def test_missing_key_is_none_not_an_error():
    assert K.get("never-written") is None


def test_expired_value_reads_as_absent():
    K.put("k", "v", ttl=0)
    time.sleep(0.01)
    assert K.get("k") is None


def test_drop_removes():
    K.put("k", "v", ttl=60)
    K.drop("k")
    assert K.get("k") is None


def test_backend_is_reported_honestly():
    """Without REDIS_URL this must say 'memory'. /api/health surfaces it, and a
    store that claimed durability it does not have would be worse than none."""
    assert K.backend() in ("memory", "redis")
    if not K.available():
        assert K.backend() == "memory"


def test_rate_limit_allows_up_to_the_limit_then_refuses():
    for i in range(5):
        assert K.hit("ip|/api/verify", limit=5, window=60) is True, f"request {i} refused early"
    assert K.hit("ip|/api/verify", limit=5, window=60) is False


def test_rate_limit_buckets_are_independent():
    for _ in range(5):
        K.hit("a|/api/verify", limit=5, window=60)
    assert K.hit("a|/api/verify", limit=5, window=60) is False
    # A different IP, and a different path bucket for the same IP, are untouched.
    assert K.hit("b|/api/verify", limit=5, window=60) is True
    assert K.hit("a|/api/badge", limit=5, window=60) is True


def test_rate_limit_window_slides():
    assert K.hit("s", limit=1, window=0.05) is True
    assert K.hit("s", limit=1, window=0.05) is False
    time.sleep(0.06)
    assert K.hit("s", limit=1, window=0.05) is True, "window did not slide"


def test_deep_scan_handoff_shape():
    """The store's actual job: the collector writes, the browser reads it back
    across a later request."""
    token = "tok-123"
    doc = {"passport_hash": "h", "payload": {"device_id": "D"}}
    device = {"mitigation_state": {"x": 1}}
    K.put(f"deep:{token}", doc, 3600)
    K.put(f"dev:{token}", device, 3600)

    assert K.get(f"deep:{token}") == doc
    assert (K.get(f"dev:{token}") or {}).get("mitigation_state") == {"x": 1}
    assert K.get("deep:wrong-token") is None
