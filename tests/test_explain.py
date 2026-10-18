"""The plain-language explanation (S2-08): the model words the result, and any
reply with a number that is not on the page is thrown away. The model is
replaced by a stand-in here, so these tests never call the internet."""
import pytest
from fastapi.testclient import TestClient

from afterlife import explain as E
from afterlife import llm
from api.main import app

client = TestClient(app)
BODY = {"age_years": 5, "eol_risk": 0.18, "fault_described": True, "fault_detail": "Battery",
        "os": "Windows 10", "make_model": "Windows 10", "product_category": "Laptop",
        "timezone": "Asia/Kolkata", "persona": "coder", "cores": 8, "ram_gb": 8}


@pytest.fixture
def assessment():
    return client.post("/api/assess", json=BODY).json()


def test_numbers_on_the_page_pass_and_rounding_of_them_is_allowed(assessment):
    f = E.facts(assessment, "browser profile")
    score = f["score"]
    assert E.check_numbers(f"You scored {score} out of 100, about {round(21.1)} years to repay.", f) == [] \
        or "21" in E._allowed(f)
    assert E.check_numbers(f"You scored {score} out of 100.", f) == []


def test_a_number_not_on_the_page_is_caught(assessment):
    f = E.facts(assessment, "browser profile")
    assert E.check_numbers("It will last 9.5 more years and cost 4,999 to fix.", f) == ["4999", "9.5"]


def test_facts_explain_labels_in_words_the_model_cannot_misread(assessment):
    f = E.facts(assessment, "browser profile")
    whats = [a["what"] for a in f["score_adjustments"]]
    assert any("devices like this one end up beyond repair" in w for w in whats)
    assert "ML end-of-life risk" not in whats


def test_facts_carry_no_identity(assessment):
    f = str(E.facts(assessment, "browser profile"))
    assert "device_id" not in f and "Asia/Kolkata" not in f


def test_a_good_reply_is_shown(assessment, monkeypatch):
    score = assessment["blend"]["combined_score"]
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: f"You scored {score} out of 100.")
    r = E.explain(assessment, "browser profile")
    assert r["source"].startswith("language model") and str(score) in r["text"]


def test_a_reply_with_an_invented_number_falls_back(assessment, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "Your laptop has 12 years left.")
    r = E.explain(assessment, "browser profile")
    assert r["source"] == "rule-based" and "12" in r["reason"]
    assert r["text"] == assessment["narrative"]["summary"]


def test_no_key_or_an_outage_falls_back(assessment, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    assert E.explain(assessment)["source"] == "rule-based"

    def boom(*a, **k):
        raise TimeoutError
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat", boom)
    r = E.explain(assessment)
    assert r["source"] == "rule-based" and "unavailable" in r["reason"]


def test_endpoint_is_rate_limited(assessment, monkeypatch):
    from afterlife import kvstore
    monkeypatch.setattr(llm, "available", lambda: False)
    monkeypatch.setattr(kvstore, "hit", lambda *a, **k: False)
    r = client.post("/api/explain", json={"assessment": assessment}).json()
    assert r["source"] == "rule-based" and "too many" in r["reason"]
