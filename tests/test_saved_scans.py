"""Accounts and saved scans (S2-02, S2-03), with Supabase replaced by a fake.

No test talks to the real Supabase project: requests.get/post/patch inside
afterlife.auth are swapped for a small in-memory stand-in.
"""
import copy

import pytest

from afterlife import auth
from afterlife.passport import build_scan_passport


class FakeResponse:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data
        self.ok = status < 400

    def json(self):
        return self._data

    def raise_for_status(self):
        if not self.ok:
            raise auth.requests.HTTPError(str(self.status_code))


@pytest.fixture
def supabase(monkeypatch):
    """An in-memory scans table and one valid user token ('good-token')."""
    rows, calls = [], []
    monkeypatch.setattr(auth, "secret", lambda name: {"SUPABASE_URL": "https://example.supabase.co",
                                                      "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_test"}.get(name, ""))

    def get(url, params=None, headers=None, timeout=None):
        calls.append(("GET", url, headers))
        if url.endswith("/auth/v1/user"):
            ok = headers.get("Authorization") == "Bearer good-token"
            return FakeResponse(200 if ok else 401, {"id": "user-1"} if ok else {})
        mine = [r for r in rows if f"eq.{r['user_id']}" == params["user_id"]]
        if "device_id" in params:
            mine = [r for r in mine if f"eq.{r['device_id']}" == params["device_id"]][-1:]
        return FakeResponse(200, list(reversed(mine)))

    def post(url, json=None, headers=None, timeout=None):
        calls.append(("POST", url, headers)); rows.append({"id": len(rows) + 1, **json}); return FakeResponse(201)

    def patch(url, params=None, json=None, headers=None, timeout=None):
        calls.append(("PATCH", url, headers))
        for r in rows:
            if f"eq.{r['id']}" == params["id"]:
                r.update(json)
        return FakeResponse(204)

    monkeypatch.setattr(auth.requests, "get", get)
    monkeypatch.setattr(auth.requests, "post", post)
    monkeypatch.setattr(auth.requests, "patch", patch)
    return rows, calls


def _passport():
    return build_scan_passport({"os": "Windows 11", "gpu": "Intel Iris Xe", "cpu_cores": 8, "ram_gb": 8,
                                "architecture": "x86 64", "product_category": "Laptop", "device_age": 4})


AUTH = {"Authorization": "Bearer good-token"}
ASSESS = {"blend": {"combined_score": 72, "grade": "B - good"}, "pipeline": {"estimated_remaining_years": 6}}


def test_signed_out_cannot_save_or_list(client, supabase):
    assert client.post("/api/save-scan", json={"passport": _passport()}).status_code == 401
    assert client.get("/api/my-scans").status_code == 401
    assert client.get("/api/my-scans", headers={"Authorization": "Bearer stolen"}).status_code == 401


def test_a_genuine_passport_is_saved_and_listed(client, supabase):
    rows, _ = supabase
    r = client.post("/api/save-scan", headers=AUTH, json={"passport": _passport(), "assessment": ASSESS})
    assert r.json() == {"saved": True, "result": "inserted"}
    assert rows[0]["user_id"] == "user-1" and rows[0]["scan_type"] == "instant"
    assert client.get("/api/my-scans", headers=AUTH).json()["scans"][0]["device_id"] == rows[0]["device_id"]


def test_an_edited_passport_is_refused(client, supabase):
    doc = copy.deepcopy(_passport()); doc["payload"]["ram_gb"] = 32
    assert client.post("/api/save-scan", headers=AUTH, json={"passport": doc}).status_code == 400
    assert supabase[0] == []


def test_a_rescan_with_nothing_changed_refreshes_instead_of_duplicating(client, supabase):
    rows, _ = supabase
    for _ in range(2):
        client.post("/api/save-scan", headers=AUTH, json={"passport": _passport(), "assessment": ASSESS})
    assert len(rows) == 1


def test_a_changed_score_adds_a_new_history_row(client, supabase):
    rows, _ = supabase
    client.post("/api/save-scan", headers=AUTH, json={"passport": _passport(), "assessment": ASSESS})
    later = {**ASSESS, "blend": {"combined_score": 66, "grade": "C - serviceable"}}
    client.post("/api/save-scan", headers=AUTH, json={"passport": _passport(), "assessment": later})
    assert len(rows) == 2


def test_the_secret_key_style_decides_the_headers(supabase):
    assert "Authorization" not in auth._server_headers("sb_secret_abc")
    assert auth._server_headers("eyJlegacy.jwt")["Authorization"] == "Bearer eyJlegacy.jwt"


def test_without_supabase_settings_nothing_breaks(client, monkeypatch):
    monkeypatch.setattr(auth, "secret", lambda name: "")
    assert client.get("/api/account-status").json() == {"accounts": False}
    assert client.get("/api/my-scans", headers=AUTH).status_code == 401
