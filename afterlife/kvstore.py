"""Key-value store for the two pieces of state that outlive a single request.

Both were plain Python dicts in api/main.py, which is correct only while there
is exactly one process that never restarts. Neither holds:

  deep-scan handoff   The collector POSTs a scan, the browser polls for it.
                      That state lived in `_DEEP_STORE`, so a Render redeploy
                      mid-scan dropped it and the user saw their scan silently
                      expire with nothing to retry against. Render redeploys on
                      every push to master.

  rate limiting       `_rl_hits` counted per process. A second instance doubles
                      every limit, and a restart clears the window entirely --
                      so the quota is whatever the last deploy left behind.

Redis is the right shape for both: expiry is a native property of a key rather
than a prune pass someone has to remember to call, and INCR is atomic across
instances, which is the whole point of a shared counter.

Redis is optional. Without REDIS_URL this falls back to the same in-process
dicts, so local development and tests need nothing running -- but the fallback
says so, rather than pretending to be durable. `backend()` reports which one is
live, and /api/health surfaces it.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from typing import Any

REDIS_URL = os.environ.get("REDIS_URL", "")

_redis = None
_redis_tried_at: float | None = None   # when the last connection attempt failed
RETRY_AFTER = 60                       # seconds before trying a failed Redis again


def _client():
    """Connect lazily and once. A Redis that is configured but unreachable must
    degrade to memory rather than 500 the API -- losing a scan handoff is bad,
    refusing every request is worse."""
    global _redis, _redis_tried_at
    if _redis is not None or not REDIS_URL:
        return _redis
    # A failed attempt is retried after a minute rather than never: Redis being
    # briefly unreachable while the server starts must not pin it to memory
    # until the next deploy.
    if _redis_tried_at is not None and time.monotonic() - _redis_tried_at < RETRY_AFTER:
        return None
    try:
        import redis  # type: ignore

        client = redis.Redis.from_url(
            REDIS_URL, decode_responses=True,
            socket_connect_timeout=2, socket_timeout=2,
            health_check_interval=30)
        client.ping()
        _redis = client
    except Exception:
        _redis = None
        _redis_tried_at = time.monotonic()
    return _redis


def backend() -> str:
    return "redis" if _client() is not None else "memory"


def available() -> bool:
    return _client() is not None


# ─── Expiring values ─────────────────────────────────────────────────────────

_mem: dict[str, Any] = {}
_mem_exp: dict[str, float] = {}


def _mem_prune() -> None:
    now = time.monotonic()
    for k in [k for k, e in _mem_exp.items() if e <= now]:
        _mem.pop(k, None)
        _mem_exp.pop(k, None)


def put(key: str, value: Any, ttl: int) -> None:
    """Store `value` under `key` for `ttl` seconds."""
    r = _client()
    if r is not None:
        try:
            r.setex(key, ttl, json.dumps(value))
            return
        except Exception:
            pass          # fall through to memory rather than lose the write
    _mem_prune()
    _mem[key] = value
    _mem_exp[key] = time.monotonic() + ttl


def get(key: str) -> Any | None:
    """Fetch a value, or None if absent or expired."""
    r = _client()
    if r is not None:
        try:
            raw = r.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception:
            pass
    exp = _mem_exp.get(key)
    if exp is None:
        return None
    if exp <= time.monotonic():
        _mem.pop(key, None)
        _mem_exp.pop(key, None)
        return None
    return _mem.get(key)


def drop(key: str) -> None:
    r = _client()
    if r is not None:
        try:
            r.delete(key)
        except Exception:
            pass
    _mem.pop(key, None)
    _mem_exp.pop(key, None)


# ─── Sliding-window counter (rate limiting) ──────────────────────────────────

_hits: dict[str, deque] = defaultdict(deque)

#: One round trip instead of four, and atomic: a caller cannot observe the
#: window between the trim and the count and slip an extra request through.
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local n = redis.call('ZCARD', key)
if n >= limit then
  return {n, 0}
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('EXPIRE', key, math.ceil(window))
return {n + 1, 1}
"""
_lua = None


def hit(key: str, limit: int, window: float) -> bool:
    """Record a request against `key`. Returns False when over `limit`.

    A sorted set keyed by timestamp gives a true sliding window rather than
    fixed buckets, which matters because a fixed bucket lets twice the limit
    through across a boundary.
    """
    global _lua
    r = _client()
    now = time.time()
    if r is not None:
        try:
            if _lua is None:
                _lua = r.register_script(_SLIDING_WINDOW_LUA)
            member = f"{now:.6f}:{os.getpid()}"
            _, allowed = _lua(keys=[f"rl:{key}"],
                              args=[now, window, limit, member])
            return bool(allowed)
        except Exception:
            pass          # degrade to the per-process window
    dq = _hits[key]
    cutoff = now - window
    while dq and dq[0] <= cutoff:
        dq.popleft()
    if len(dq) >= limit:
        return False
    dq.append(now)
    return True


def reset() -> None:
    """Test hook: clear in-process state."""
    _mem.clear()
    _mem_exp.clear()
    _hits.clear()
