"""Accounts and saved scans, through Supabase (S2-02, S2-03).

Sign-up and sign-in happen in the browser with Supabase's own client; this side
only (1) asks Supabase who a user's access token belongs to, and (2) reads and
writes that user's rows in the `scans` table. Both are plain HTTPS calls to
Supabase's REST API, so the server needs no extra client library.

The secret key (SUPABASE_SERVICE_ROLE_KEY) lives only on the server: a Render
environment variable live, a git-ignored .env file locally. It can bypass the
table's row-level security, so the server always filters by the user id that
Supabase itself vouched for, never by anything the browser claims.

Scanning never needs an account: every function here degrades to "not signed
in" or "nothing saved" when Supabase is not configured or not reachable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from .config import secret

TIMEOUT = 10


def _settings() -> tuple[str, str] | None:
    url, key = secret("SUPABASE_URL").rstrip("/"), secret("SUPABASE_SERVICE_ROLE_KEY")
    return (url, key) if url and key else None


def _server_headers(key: str) -> dict[str, str]:
    # A new-style secret key (sb_secret_...) goes in `apikey` only; a legacy
    # service_role key is a JWT and is also sent as the bearer token.
    headers = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def configured() -> bool:
    return _settings() is not None


def user_from_token(auth_header: str | None) -> str | None:
    """The Supabase user id behind a 'Bearer <access token>' header, else None.

    Never raises: a missing, invalid or expired token simply means "not signed
    in", which is always a valid state.
    """
    s = _settings()
    if not s or not auth_header or not auth_header.startswith("Bearer "):
        return None
    url, key = s
    try:
        r = requests.get(f"{url}/auth/v1/user", timeout=TIMEOUT,
                         headers={"apikey": key, "Authorization": auth_header})
        return r.json().get("id") if r.ok else None
    except (requests.RequestException, ValueError):
        return None


def _fingerprint(record: dict[str, Any]) -> tuple:
    """What has to change for a re-scan to count as a new history entry. The
    issue date, signature and timestamps differ on every scan even of an
    untouched machine, so comparing whole records would never say "same"."""
    p = record.get("payload") or {}
    a = record.get("assessment") or {}
    return (p.get("trust_score"), p.get("battery_health"), p.get("storage_health"),
            p.get("win11"), p.get("os"), p.get("ram_gb"),
            (a.get("blend") or {}).get("combined_score"), (a.get("blend") or {}).get("grade"),
            (a.get("pipeline") or {}).get("estimated_remaining_years"))


def save_scan(user_id: str, device_id: str | None, scan_type: str, record: dict[str, Any]) -> str:
    """Add a history row, or refresh the latest one for this device if nothing
    measurable changed. Returns "inserted", "refreshed" or "unavailable"."""
    s = _settings()
    if not s:
        return "unavailable"
    url, key = s
    headers = _server_headers(key)
    table = f"{url}/rest/v1/scans"
    try:
        if device_id:
            r = requests.get(table, timeout=TIMEOUT, headers=headers, params={
                "select": "id,passport", "user_id": f"eq.{user_id}", "device_id": f"eq.{device_id}",
                "order": "created_at.desc", "limit": "1"})
            latest = r.json()[0] if r.ok and r.json() else None
            if latest and _fingerprint(latest["passport"]) == _fingerprint(record):
                requests.patch(table, timeout=TIMEOUT, headers=headers, params={"id": f"eq.{latest['id']}"},
                               json={"passport": record, "scan_type": scan_type,
                                     "created_at": datetime.now(timezone.utc).isoformat()}).raise_for_status()
                return "refreshed"
        requests.post(table, timeout=TIMEOUT, headers={**headers, "Prefer": "return=minimal"},
                      json={"user_id": user_id, "device_id": device_id,
                            "scan_type": scan_type, "passport": record}).raise_for_status()
        return "inserted"
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return "unavailable"


def list_scans(user_id: str) -> list[dict[str, Any]]:
    """A user's saved scans, newest first; empty if Supabase is unavailable."""
    s = _settings()
    if not s:
        return []
    url, key = s
    try:
        r = requests.get(f"{url}/rest/v1/scans", timeout=TIMEOUT, headers=_server_headers(key),
                         params={"select": "*", "user_id": f"eq.{user_id}", "order": "created_at.desc"})
        return r.json() if r.ok else []
    except (requests.RequestException, ValueError):
        return []
