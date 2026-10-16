"""Secure Boot certificate expiry: real dates, and honest about what it can't read.

The expiry dates were rounded to month-ends at first (30 June, 31 October), which
on 16 Oct 2026 told a reader a certificate had 15 days left when it had 3. These
pin the published dates and the wording that depends on them.
"""
import datetime as dt

from afterlife.secure_boot import (KEK_2011_EXPIRY, PCA_2011_EXPIRY, UEFI_CA_2011_EXPIRY, assess)


def test_the_published_expiry_dates():
    assert KEK_2011_EXPIRY == dt.date(2026, 6, 24)
    assert UEFI_CA_2011_EXPIRY == dt.date(2026, 6, 27)
    assert PCA_2011_EXPIRY == dt.date(2026, 10, 19)


def test_days_left_are_counted_from_the_real_date():
    out = assess({"uefi": True, "secure_boot_on": True,
                  "secure_boot_certs": {"checked": True, "db_2023": False, "kek_2023": False}},
                 today=dt.date(2026, 10, 16))
    assert "expires in 3 days" in out["detail"]


def test_an_unread_certificate_store_is_unknown_never_fine():
    out = assess({"uefi": True, "secure_boot_on": True}, today=dt.date(2026, 10, 16))
    assert out["status"] == "unknown"


def test_updated_certificates_are_reported_as_up_to_date():
    out = assess({"uefi": True, "secure_boot_certs": {"checked": True, "db_2023": True, "kek_2023": True}},
                 today=dt.date(2026, 10, 16))
    assert "up to date" in out["headline"]


def test_legacy_bios_is_not_a_finding():
    out = assess({"uefi": False}, today=dt.date(2026, 10, 16))
    assert out["status"] not in ("at_risk", "action_needed")
