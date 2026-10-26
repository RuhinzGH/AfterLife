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
