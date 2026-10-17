"""/api/assess returns the Sprint-2 cards (usage fit, repair outlook, repair
rights), and /api/price-estimate prices from the awarded grade."""
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)
INSTANT = {"hardware_trust": 75, "age_years": 5, "fault_described": True, "fault_detail": "Battery",
           "os": "Windows 10", "make_model": "Windows 10", "product_category": "Laptop",
           "cores": 8, "ram_gb": 8, "gpu": "Intel UHD Graphics 620", "problem": "battery drains fast"}


def test_instant_scan_uses_the_usage_answer():
    d = client.post("/api/assess", json={**INSTANT, "persona": "coder", "timezone": "Asia/Kolkata"}).json()
    assert d["usage_fit"]["source"] == "self-reported" and d["usage_fit"]["persona"] == "coder"
    assert any("coding" in s for s in d["key_points"]["strengths"])
    assert d["uplift"]["capability"] is None          # browser memory is only "8 or more"
    assert d["repair_evidence"]["themes"][0]["key"] == "battery"
    assert d["repair_rights"]["status"] == "outside"
    assert d["geo"]["currency"] == "INR"


def test_no_answer_no_usage_card():
    assert client.post("/api/assess", json=INSTANT).json()["usage_fit"] is None


def test_deep_scan_detects_the_use():
    body = {"hardware_trust": 62, "trust_measured": True, "battery_health": 55, "age_years": 6,
            "product_category": "Laptop", "timezone": "Europe/Berlin", "cores": 8, "ram_gb": 7.8,
            "persona_signals": {"coder_matches": ["Visual Studio Code"]}, "gpu": "Intel Iris Xe"}
    d = client.post("/api/assess", json=body).json()
    assert d["usage_fit"]["source"] == "auto-detected" and d["usage_fit"]["persona"] == "coder"
    assert d["uplift"]["condition"]["actions"][0]["action"] == "Replace the battery"
    assert d["uplift"]["capability"]["target_ram_gb"] == 16
    assert d["repair_rights"]["status"] == "display_only"


def test_price_estimate_endpoint():
    r = client.post("/api/price-estimate", json={"price_new": 900, "product_category": "Laptop",
                                                 "age_years": 3, "grade": "B - good"})
    assert r.status_code == 200 and r.json()["low"] < r.json()["high"] <= 900
    assert client.post("/api/price-estimate", json={"price_new": -5}).status_code == 400
