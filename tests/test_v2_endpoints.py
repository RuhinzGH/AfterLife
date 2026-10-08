"""The read-only endpoints behind the redesigned site's tools.

Each one is a thin view over a module the assessment already uses, so the
tests pin that they agree with it rather than re-deriving the numbers.
"""
from fastapi.testclient import TestClient

from afterlife import esu, grid
from api.main import app

client = TestClient(app)


class TestEsu:
    def test_both_programmes_come_from_the_score_table(self):
        d = client.get("/api/esu").json()
        assert d["consumer"]["esu_end"] == esu.PROGRAMMES["windows10"].esu_end.isoformat()
        assert d["commercial"]["esu_end"] == esu.PROGRAMMES["windows10-commercial"].esu_end.isoformat()

    def test_consumer_ends_before_commercial(self):
        d = client.get("/api/esu").json()
        assert d["consumer"]["esu_end"] < d["commercial"]["esu_end"]


class TestGridCountries:
    def test_lists_countries_and_classes(self):
        d = client.get("/api/grid-countries").json()
        assert len(d["countries"]) > 100
        assert {"code", "name", "gco2_kwh", "year"} <= set(d["countries"][0])
        assert any(c["name"] == "Laptop" for c in d["device_classes"])


class TestCarbonCalc:
    def test_matches_the_assessment_maths(self):
        d = client.get("/api/carbon-calc", params={"country": "IN", "device_class": "Laptop"}).json()
        same = grid.break_even("IN", d["embodied_kg"], 45.0, 28.0)
        assert d["years"] == same["years"]
        assert d["grid"]["basis"] == "country"
        assert d["embodied_range_kg"][0] <= d["embodied_kg"] <= d["embodied_range_kg"][1]

    def test_unknown_country_says_it_used_the_world_average(self):
        d = client.get("/api/carbon-calc", params={"country": "ZZ"}).json()
        assert d["grid"]["basis"] == "world"

    def test_no_efficiency_gain_never_repays(self):
        d = client.get("/api/carbon-calc", params={"old_tdp_w": 28, "new_tdp_w": 28}).json()
        assert d["repays"] is False

    def test_unknown_class_is_refused_not_defaulted(self):
        assert client.get("/api/carbon-calc", params={"device_class": "Toaster"}).status_code == 404

    def test_absurd_power_is_refused(self):
        assert client.get("/api/carbon-calc", params={"old_tdp_w": 0}).status_code == 400
