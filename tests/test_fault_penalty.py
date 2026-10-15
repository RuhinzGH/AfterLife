"""The reported-fault adjustment counts only text that names a real fault (S2-11).

Before: any text at all in "Anything wrong?" -- even "asdf" -- cost 5 points,
because the score only checked that something had been typed. Now the text must
name a fault theme from the multilingual lexicon, matched on whole words so
"important" isn't a port and "fantastic" isn't a fan.
"""
import pytest
from fastapi.testclient import TestClient

from afterlife.fault_lexicon import fault_themes
from afterlife.passport import build_scan_passport
from api.main import app


@pytest.mark.parametrize("text", ["", "   ", "asdf", "this is important", "a fantastic laptop",
                                  "runs Windows 11 fine", "works great, no issues"])
def test_text_that_names_no_fault_counts_as_no_fault(text):
    assert fault_themes(text) == []


@pytest.mark.parametrize("text, theme", [
    ("battery drains fast", "Battery"),
    ("Akku aufgebläht", "Battery"),          # German: swollen battery
    ("écran cassé", "Screen"),                # French: broken screen
    ("the fans are very loud", "Overheating / fan"),
    ("two USB ports stopped working", "Ports / connectors"),
    ("hinge is cracked", "Hinge / casing"),
])
def test_real_faults_in_several_languages_are_recognised(text, theme):
    assert theme in fault_themes(text)


def _passport(problem):
    return build_scan_passport({"os": "Windows 11", "gpu": "Intel Iris Xe", "cpu_cores": 8, "ram_gb": 8,
                                "architecture": "x86 64", "product_category": "Laptop",
                                "device_age": 4, "problem": problem})


def test_nonsense_text_sets_no_fault_flag_in_the_passport():
    lc = _passport("asdf")["payload"]["lifecycle"]
    assert lc["fault_described"] is False and lc["fault_themes"] == []


def test_a_real_fault_is_flagged_and_named_in_the_passport():
    lc = _passport("battery drains fast")["payload"]["lifecycle"]
    assert lc["fault_described"] is True and lc["fault_themes"] == ["Battery"]


def test_the_waterfall_names_the_recognised_fault():
    client = TestClient(app)
    body = {"hardware_trust": 75, "eol_risk": 0.2, "age_years": 4, "product_category": "Laptop",
            "fault_described": True, "fault_detail": "Battery"}
    adj = client.post("/api/assess", json=body).json()["blend"]["adjustments"]
    fault = [a for a in adj if a["factor"] == "reported fault"]
    assert fault and fault[0]["delta"] == -5 and fault[0]["detail"] == "Battery"


def test_no_fault_means_no_fault_adjustment():
    client = TestClient(app)
    body = {"hardware_trust": 75, "eol_risk": 0.2, "age_years": 4, "product_category": "Laptop",
            "fault_described": False}
    adj = client.post("/api/assess", json=body).json()["blend"]["adjustments"]
    assert not [a for a in adj if a["factor"] == "reported fault"]
