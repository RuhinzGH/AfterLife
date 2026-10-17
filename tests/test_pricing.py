"""Resale estimate (S2-07): an assumed depreciation formula, so its internal
consistency is what can be tested: it falls with age, rises with condition, is
a range, and never exceeds the price new."""
import pytest

from afterlife.pricing import GRADE_LADDER, estimate_resale


def test_older_is_worth_less():
    prices = [estimate_resale(1000, "Laptop", a, "B - good")["mid"] for a in (0, 1, 3, 5, 8)]
    assert prices == sorted(prices, reverse=True)


def test_better_grade_is_worth_more():
    prices = [estimate_resale(1000, "Laptop", 3, g)["mid"] for g in GRADE_LADDER]
    assert prices == sorted(prices)


def test_it_is_a_range_around_the_middle():
    r = estimate_resale(1000, "Laptop", 3, "B - good")
    assert r["low"] < r["mid"] < r["high"]


def test_never_above_the_price_new():
    r = estimate_resale(1000, "Laptop", 0, "A - excellent", "Like new")
    assert r["high"] <= 1000 and r["mid"] <= 1000


def test_the_repaired_grade_is_offered_except_at_the_top():
    assert estimate_resale(1000, "Laptop", 3, "C - serviceable")["potential"]["grade"] == "B - good"
    assert estimate_resale(1000, "Laptop", 3, "A - excellent")["potential"] is None


def test_the_inputs_are_returned_so_the_card_can_show_the_formula():
    r = estimate_resale(60000, "Laptop", 5, "C - serviceable", currency="INR")
    i = r["inputs"]
    assert r["currency"] == "INR"
    shown = 60000 * i["age_factor"] * i["grade_factor"] * i["cosmetic_factor"]
    assert abs(r["mid"] - shown) <= 0.002 * shown     # age_factor is shown to 3 decimals


def test_a_bad_price_is_refused():
    with pytest.raises(ValueError):
        estimate_resale(0, "Laptop", 3, "B - good")
