"""EU repairability grade (S3-01): the official EPREL class for phones and
tablets, found from the model code a phone reports, and never guessed."""
from fastapi.testclient import TestClient

from afterlife.eprel import class_spread, find, lookup_code
from api.main import app

client = TestClient(app)


def test_a_phone_model_code_finds_its_registration():
    r = find("SM-S931B", "Mobile")        # registered as SM-S931B/DS
    assert r["brand"] == "Samsung" and r["model"].startswith("SM-S931B")
    assert r["repairability_class"] in "ABCDE" and 1 <= r["repairability_index"] <= 5


def test_a_code_in_brackets_is_found():
    assert find("XT2523-3", "Mobile")["model"] == "g05 (XT2523-3)"


def test_laptops_never_get_a_grade():
    assert find("SM-S931B", "Laptop") is None
    assert find("SM-S931B", "Desktop computer") is None


def test_unclear_or_unknown_models_get_nothing():
    assert find("Pixel 8", "Mobile") is None          # Google registers codes, not names
    assert lookup_code("SM-A") is None                 # too short: many models start this way
    assert find("", "Mobile") is None


def test_the_record_says_it_is_a_declaration_and_credits_the_commission():
    r = find("SM-S931B", "Mobile")
    assert "DECLARED" in r["caveat"] and "European Commission" in r["attribution"]


def test_class_spread_comes_from_the_analysis_file():
    s = class_spread()
    assert set(s["classes"]) == set("ABCDE") and sum(s["classes"].values()) <= s["n"]


def test_assess_returns_the_grade_or_says_no_match():
    base = {"product_category": "Mobile", "age_years": 2, "timezone": "Europe/Berlin"}
    hit = client.post("/api/assess", json={**base, "model_code": "SM-S931B"}).json()["eprel"]
    assert hit["matched"] and hit["spread"]["n"] > 2000
    miss = client.post("/api/assess", json={**base, "model_code": "Nokia 3310"}).json()["eprel"]
    assert miss == {"matched": False, "query": "Nokia 3310"}
    laptop = client.post("/api/assess", json={**base, "product_category": "Laptop", "model_code": "SM-S931B"}).json()
    assert laptop["eprel"] is None
