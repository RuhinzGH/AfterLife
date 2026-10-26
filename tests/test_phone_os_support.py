"""A phone's OS label must resolve to its own release (defect S2-D16).

The browser scan labelled Android 16 as "Android 11 (build 16.0.0)", because a
Windows-only version rule ran on every platform; the support lookup then
matched Android 11, whose support ended in 2024, and My Scans told the owner of
a current phone that its security support had ended. The label is fixed in
frontend/src/scan.js (osLabel, with its own test); these pin the server side:
a recent Android must never be reported as out of support, and an old one still
must be.
"""
import datetime as dt

from afterlife.device_support import lookup

TODAY = dt.date(2026, 10, 26)


def test_android_16_is_not_reported_as_out_of_support():
    h = lookup("Android 16 (build 16.0.0)", "Android 16 (build 16.0.0)", as_of=TODAY)
    assert h is None or not h.is_eol


def test_the_old_wrong_label_was_what_matched_android_11():
    h = lookup("Android 11 (build 16.0.0)", "Android 11 (build 16.0.0)", as_of=TODAY)
    assert h is not None and h.is_eol and h.matched_key == "android11"


def test_an_old_android_is_still_reported_as_out_of_support():
    h = lookup("Android 10 (build 10.0.0)", "Android 10 (build 10.0.0)", as_of=TODAY)
    assert h is not None and h.is_eol


# ------------------------------------------------------------- phone model codes
# Chrome on Android reports a model CODE; the support table lists phones by name.
# app_data/model_aliases.json (scripts/build_model_aliases.py, from Google Play's
# supported-devices list) bridges the two.

def test_a_samsung_model_code_resolves_to_its_support_date():
    h = lookup(None, "Android 16 (build 16.0.0)", as_of=TODAY, model_code="SM-S711B")
    assert h is not None and h.release == "Galaxy S23 FE" and h.matched_on == "device"
    assert not h.is_eol and h.eol_from == "2028-10-05"


def test_a_typed_model_name_still_works():
    h = lookup(None, None, as_of=TODAY, model_code="Galaxy S23 FE")
    assert h is not None and h.release == "Galaxy S23 FE"


def test_an_unknown_code_falls_back_to_the_os_and_never_guesses_a_device():
    h = lookup(None, "Android 16 (build 16.0.0)", as_of=TODAY, model_code="XYZ-0000")
    assert h is None or h.matched_on == "os"


def test_every_alias_points_at_a_device_the_support_table_knows():
    import json, re
    from pathlib import Path
    app = Path(__file__).resolve().parents[1] / "app_data"
    aliases = json.loads((app / "model_aliases.json").read_text(encoding="utf-8"))["aliases"]
    devices = json.loads((app / "device_support.json").read_text(encoding="utf-8"))["devices"]
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    assert aliases
    for name in set(aliases.values()):
        assert any(k in norm(name) for k in devices if len(k) >= 6), name
