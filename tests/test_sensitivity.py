"""Sensitivity analysis (S3-08): computed by the site's own functions, and it
reports where the conclusions change as well as where they hold."""
from fastapi.testclient import TestClient

from afterlife import grid
from afterlife.assessment import blend_score
from afterlife.sensitivity import analysis
from api.main import app


def test_the_default_case_is_the_cards_own_number():
    c = analysis()["carbon"]
    laptop_on_india = grid.payback_range("IN", c["base"]["embodied_kg"], "class", device_class="Laptop")
    assert c["base"]["years"] == laptop_on_india["years"]


def test_more_hours_or_load_repay_sooner_and_a_cleaner_grid_later():
    rows = {(r["factor"], r["value"].split(" ")[0]): r["years"] for r in analysis()["carbon"]["one_at_a_time"]}
    base = analysis()["carbon"]["base"]["years"]
    assert rows[("Hours a day", "12")] < base < rows[("Hours a day", "4")]
    assert rows[("Grid", "France")] > base


def test_it_says_where_the_conclusion_breaks():
    c = analysis()["carbon"]
    assert c["never_repays"]                                   # a 15 W laptop never repays
    assert c["everything_against_keeping"]["years"] < c["range_years"][0]


def test_score_variants_are_reported_with_their_size():
    s = analysis()["score"]
    assert s["devices"] > 500 and len(s["variants"]) == 4
    for v in s["variants"]:
        assert 0 <= v["grade_changes_pct"] <= 100 and v["max_points_moved"] >= v["mean_points_moved"]


def test_rule_overrides_change_only_what_they_name():
    base = blend_score(75, 0.2, None, None, False)
    assert blend_score(75, 0.2, None, None, False, rules={"FAULT_PENALTY": -10}) == base
    assert blend_score(75, 0.2, None, None, False, rules={"EOL_WEIGHT": 20})["combined_score"] == 71


def test_endpoint():
    d = TestClient(app).get("/api/sensitivity").json()
    assert "carbon" in d and "score" in d
