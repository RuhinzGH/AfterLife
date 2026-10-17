"""Repair rights (S2-06): EU law stated precisely, and only where it applies."""
import datetime as dt

from afterlife.repair_rights import assess


def test_phones_are_covered_with_their_ecodesign_rules():
    r = assess("Mobile", in_eea=True)
    assert r["status"] == "covered"
    assert any("seven years" in x["title"] for x in r["rights"])


def test_a_laptop_is_only_partly_covered_and_says_so_first():
    r = assess("Laptop", in_eea=True)
    assert r["status"] == "display_only"
    assert "not the laptop" in r["headline"]
    assert not any("must repair it" in x["title"] for x in r["rights"])


def test_desktops_and_consoles_are_not_covered():
    for c in ("Desktop computer", "Games console"):
        assert assess(c, in_eea=True)["status"] == "not_covered"


def test_outside_the_eea_no_eu_rule_is_shown():
    r = assess("Mobile", in_eea=False, country="IN", country_name="India")
    assert r["status"] == "outside" and "India" in r["headline"]
    assert not any("seven years" in x["title"] for x in r["rights"])
    assert r["sources"][0]["url"].startswith("https://righttorepairindia.gov.in")


def test_outside_the_eea_elsewhere_names_no_portal():
    r = assess("Laptop", in_eea=False, country="US", country_name="United States")
    assert len(r["rights"]) == 1 and r["sources"][0]["label"].startswith("Directive")


def test_unknown_device_type_gets_no_claim():
    assert assess("Toaster", in_eea=True) is None
    assert assess(None, in_eea=True) is None


def test_in_force_from_31_july_2026():
    assert assess("Mobile", True, today=dt.date(2026, 7, 30))["in_force"] is False
    assert assess("Mobile", True, today=dt.date(2026, 7, 31))["in_force"] is True
