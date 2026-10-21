"""The deep-scan passport (S2-01): a measured trust score instead of the fixed 75.

Guards the parts written for this project rather than carried over: the device
ID uses the hashed scheme (defect D7 would otherwise come back for every laptop
of one maker), storage health comes from the drive's own report (no unvalidated
model), the five sub-scores add up to the score, OS support comes from the
offline table, and the hand-off tokens can't be trivially guessed.
"""
import json

from afterlife.passport import build_deep_passport, deep_device_id, deep_trust_score, verify_payload


def test_two_models_from_one_maker_get_different_ids(device):
    a = device(manufacturer="Dell Inc.", model="Latitude 5490")
    b = device(manufacturer="Dell Inc.", model="Latitude 7420")
    assert deep_device_id(a) != deep_device_id(b)


def test_the_same_machine_keeps_its_id(device):
    assert deep_device_id(device()) == deep_device_id(device(collected_at="2026-10-20T09:00:00"))


def test_a_perfect_machine_scores_exactly_100(device):
    d = device(os_caption="Microsoft Windows 11 Home", cpu_name="Intel Core i7-1260P",
               battery_health_pct=95.0, approx_age_years=1.5,
               nvme_health=[{"critical_warning": 0, "percentage_used": 3}])
    score, subs, _, _ = deep_trust_score(d)
    assert score == sum(s["points"] for s in subs) == 100
    assert sum(s["max_points"] for s in subs) == 100


def test_os_support_is_recorded_once_not_scored_twice(device):
    """The support date is applied once, by the combined score; the hardware
    trust score must not contain it as well."""
    _, subs, _, state = deep_trust_score(device())
    assert state == "esu"
    assert not [s for s in subs if "support" in s["name"].lower()]
    assert build_deep_passport(device())["payload"]["os_support"] == "esu"


def test_a_measured_trust_score_is_not_docked_again_for_battery_or_age(client):
    body = {"hardware_trust": 81, "battery_health": 71, "age_years": 6.5, "os": "Microsoft Windows 10 Pro",
            "product_category": "Laptop", "trust_measured": True}
    factors = [a["factor"] for a in client.post("/api/assess", json=body).json()["blend"]["adjustments"]]
    assert "battery wear" not in factors and "age" not in factors
    body["trust_measured"] = False   # a browser scan still gets both, as before
    factors = [a["factor"] for a in client.post("/api/assess", json=body).json()["blend"]["adjustments"]]
    assert "battery wear" in factors and "age" in factors


def test_storage_uses_the_drives_own_warning(device):
    _, subs, _, _ = deep_trust_score(device(nvme_health=[{"critical_warning": 1, "percentage_used": 40}]))
    storage = next(s for s in subs if s["name"] == "Storage health")
    assert storage["points"] == 5 and "critical warning" in storage["note"]


def test_unread_battery_is_never_scored_as_healthy(device):
    d = device(); d.pop("battery_health_pct")
    _, subs, _, _ = deep_trust_score(d)
    battery = next(s for s in subs if s["name"] == "Battery health")
    assert battery["points"] < battery["max_points"] and "not read" in battery["note"]


def test_deep_passport_is_signed_and_covers_every_copy(device):
    doc = json.loads(json.dumps(build_deep_passport(device())))
    assert doc["payload"]["tier"] == "full scan"
    assert verify_payload(doc) is True
    doc["credentialSubject"]["trust_score"] = 99
    assert verify_payload(doc) is False


def test_short_or_odd_tokens_are_refused(client, device):
    assert client.post("/api/deep-scan/abc", json=device()).status_code == 400
    assert client.get("/api/deep-scan/has spaces in it!!").status_code in (400, 404)


def test_hand_off_round_trip(client, device):
    token = "handoff-test-0123456789"
    assert client.get(f"/api/deep-scan/{token}").json() == {"pending": True}
    assert client.post(f"/api/deep-scan/{token}", json=device()).json()["ok"] is True
    doc = client.get(f"/api/deep-scan/{token}").json()
    assert doc["payload"]["trust_score"] == sum(s["points"] for s in doc["payload"]["sub_scores"])
    assert doc["verified"] is True


def test_collector_is_served_as_readable_text(client):
    r = client.get("/api/collector.ps1")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "Read-only" in r.text


def test_a_mac_gets_no_windows_11_points_and_the_rest_scale_to_100():
    """The Windows 11 share only applies to a Windows PC. A Mac used to collect
    the full 35 points because the check finds nothing to block without a TPM."""
    from afterlife.passport import build_deep_passport
    mac = {"manufacturer": "Apple", "model": "MacBookAir10,1", "cpu_name": "Apple M1", "ram_gb": 8,
           "os_caption": "macOS 14.5", "battery_present": True, "battery_health_pct": 88,
           "disk_health": "Healthy", "approx_age_years": 4, "uefi": True}
    p = build_deep_passport(mac)["payload"]
    assert p["win11"] == "NOT APPLICABLE" and p["win11_blockers"] == []
    assert "Windows 11 ready" not in [s["name"] for s in p["sub_scores"]]
    got = sum(s["points"] for s in p["sub_scores"])
    out_of = sum(s["max_points"] for s in p["sub_scores"])
    assert p["trust_score"] == round(100 * got / out_of)
