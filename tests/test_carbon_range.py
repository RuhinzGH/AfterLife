"""Carbon payback as a range (S2-13): light / typical / heavy use, the usage
answer picks one, and a deep scan's processor sets the old machine's power."""
import pytest
from fastapi.testclient import TestClient

from afterlife import grid
from afterlife.cpu_power import rated_power
from api.main import app

client = TestClient(app)


@pytest.mark.parametrize("name, watts", [
    ("Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz", 15),
    ("Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz", 45),
    ("12th Gen Intel(R) Core(TM) i7-1260P", 28),
    ("Intel(R) Core(TM) Ultra 7 155H", 28),
    ("AMD Ryzen 7 6800HS Creator Edition", 35),
    ("AMD Ryzen 9 7945HX", 55),
])
def test_power_class_from_the_model_name(name, watts):
    assert rated_power(name)["watts"] == watts


def test_unknown_or_desktop_only_names_are_not_guessed_for_a_laptop():
    assert rated_power("Apple M2") is None
    assert rated_power("Intel(R) Core(TM) i5-12400") is None
    assert rated_power("Intel(R) Core(TM) i5-12400", "Desktop computer")["watts"] == 65


def test_more_hours_repay_sooner_and_light_use_takes_twice_typical():
    r = grid.payback_range("IN", 307)
    years = {s["name"]: s["years"] for s in r["scenarios"]}
    assert years["light"] > years["typical"] > years["heavy"]
    assert years["light"] == pytest.approx(2 * years["typical"], rel=0.01)


def test_the_usage_answer_picks_the_scenario():
    assert grid.payback_range("IN", 307, use="gamer")["picked"] == "heavy"
    assert grid.payback_range("IN", 307, use="general")["picked"] == "typical"
    assert grid.payback_range("IN", 307)["picked"] == "typical"


def test_a_15_w_laptop_never_repays_and_says_why():
    r = grid.payback_range("IN", 307, cpu=rated_power("Intel(R) Core(TM) i5-8250U"))
    assert not r["repays"] and all(not s["repays"] for s in r["scenarios"])
    assert "low-power class" in r["headline"]
    old = next(i for i in r["inputs"] if i["name"] == "Old processor power")
    assert old["measured"] and "i5-8250U" in old["source"]


def test_unknown_processor_is_labelled_assumed():
    old = next(i for i in grid.payback_range("IN", 307)["inputs"] if i["name"] == "Old processor power")
    assert not old["measured"] and "assumed 45 W" in old["source"]


def test_assess_uses_the_deep_scan_processor_but_not_on_an_instant_scan():
    deep = client.post("/api/assess", json={"hardware_trust": 70, "trust_measured": True, "timezone": "Asia/Kolkata",
                                            "product_category": "Laptop", "cpu": "Intel(R) Core(TM) i7-9750H"}).json()
    assert deep["carbon_tradeoff"]["assumptions"]["old_tdp_w"] == 45
    assert next(i for i in deep["carbon_tradeoff"]["inputs"] if i["name"] == "Old processor power")["measured"]
    instant = client.post("/api/assess", json={"timezone": "Asia/Kolkata", "persona": "editor",
                                               "cpu": "Intel(R) Core(TM) i5-8250U"}).json()
    assert instant["carbon_tradeoff"]["picked"] == "heavy"
    assert not next(i for i in instant["carbon_tradeoff"]["inputs"] if i["name"] == "Old processor power")["measured"]


def test_phones_and_tablets_are_not_run_through_the_laptop_power_model():
    for cat in ("Mobile", "Tablet", "Games console"):
        r = grid.payback_range("IN", 70, "class", device_class=cat)
        assert r["applies"] is False and not r["repays"] and r["scenarios"] is None
        assert "not applied" in r["headline"]
    assert grid.payback_range("IN", 70, device_class="Mobile")["headline"].startswith("Making a replacement phone")
    assert grid.payback_range("IN", 307, device_class="Laptop")["repays"]
