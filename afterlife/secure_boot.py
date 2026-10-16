"""The Secure Boot certificate cliff -- a 2026 obsolescence trigger nobody checks.

Microsoft's original Secure Boot certificates are expiring:

  * Microsoft Corporation KEK CA 2011  -- expired June 2026
  * Microsoft Corporation UEFI CA 2011 -- expired June 2026
  * Microsoft Windows Production PCA 2011 (signs the bootloader) -- expires Oct 2026

Replacements issued in 2023 run to 2038 and arrive through Windows Update. The
catch, in Microsoft's own words, is that some older UEFI firmware does not accept
the new certificates without a vendor BIOS update first -- and plenty of those
vendors have stopped shipping BIOS updates.

Why this matters for Afterlife: a machine that misses this does not stop booting.
It quietly stops receiving *boot-level* security updates -- Boot Manager fixes,
Secure Boot DB revocations, new bootkit mitigations. That is a genuine security
degradation, and it is exactly the kind of thing that gets a working machine
written off ("it's not getting updates any more, bin it") when the actual fix is
often a free firmware update.

So: detect it, name it, and say whether it is fixable. Never imply a device is
doomed when a BIOS update from the vendor would settle it.

Reference: Microsoft, "Act now: Secure Boot certificates expire in June 2026"
(Windows IT Pro Blog) and support topic "Windows Secure Boot certificate
expiration and CA updates".
"""
from __future__ import annotations

import datetime as dt
from typing import Any

#: Certificate retirement dates Microsoft has published.
# Exact expiry dates (checked 16 Oct 2026 against the University of Wisconsin KB 159935
# and a summary of Microsoft's KB5025885 guidance; Microsoft states the months).
# Expiry does not stop a PC from booting: it stops boot-level protections from
# being updated until the 2023 certificates are installed.
KEK_2011_EXPIRY = dt.date(2026, 6, 24)
UEFI_CA_2011_EXPIRY = dt.date(2026, 6, 27)
PCA_2011_EXPIRY = dt.date(2026, 10, 19)

STATUS_OK = "ok"
STATUS_ACTION_NEEDED = "action_needed"
STATUS_AT_RISK = "at_risk"
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_UNKNOWN = "unknown"


def _days_until(d: dt.date, today: dt.date) -> int:
    return (d - today).days


def assess(payload: dict[str, Any], today: dt.date | None = None) -> dict[str, Any] | None:
    """Interpret what the collector saw about this machine's Secure Boot certs.

    Expects (all optional -- absence is reported as unknown, never guessed):
      uefi              : bool  -- legacy BIOS machines are out of scope entirely
      secure_boot_on    : bool
      secure_boot_certs : {"db_2023": bool|None, "kek_2023": bool|None, "checked": bool}
    """
    today = today or dt.date.today()

    uefi = payload.get("uefi")
    if uefi is False:
        # Legacy BIOS: no Secure Boot, so no certificate to expire. Not a finding.
        return {
            "status": STATUS_NOT_APPLICABLE,
            "headline": "Legacy BIOS — Secure Boot certificates do not apply",
            "detail": "This machine boots in legacy BIOS mode, so it has no Secure Boot "
                      "certificate store to update. The June 2026 expiry does not affect it.",
            "fixable": None, "deadlines": _deadlines(today),
        }

    certs = payload.get("secure_boot_certs") or {}
    checked = bool(certs.get("checked"))
    db_2023 = certs.get("db_2023")
    kek_2023 = certs.get("kek_2023")

    if not checked or (db_2023 is None and kek_2023 is None):
        return {
            "status": STATUS_UNKNOWN,
            "headline": "Secure Boot certificate state could not be read",
            "detail": "Reading the Secure Boot certificate store needs an elevated scan. "
                      "Re-run the deep scan as administrator to check whether this device "
                      "has the 2023 certificates that replace the ones expiring in 2026.",
            "fixable": None, "deadlines": _deadlines(today),
        }

    updated = bool(db_2023) and bool(kek_2023)
    partial = bool(db_2023) != bool(kek_2023)

    if updated:
        return {
            "status": STATUS_OK,
            "headline": "Secure Boot certificates are up to date",
            "detail": "This device carries the 2023 certificates, valid to 2038. It will keep "
                      "receiving boot-level security updates after the 2011 certificates retire.",
            "fixable": None, "deadlines": _deadlines(today),
        }

    # Not updated. How bad depends on where we are relative to the dates.
    kek_gone = today > KEK_2011_EXPIRY
    pca_days = _days_until(PCA_2011_EXPIRY, today)

    if kek_gone:
        headline = "This PC has not picked up the new startup certificates"
        detail = (
            f"The old ones expired on {KEK_2011_EXPIRY:%d %B %Y} and this PC does not appear "
            "to have the replacements. Nothing breaks and it still starts up normally — but "
            "it has stopped receiving one specific category of security update: the fixes "
            "that protect the very first moments of switching on, before Windows itself loads."
        )
        if pca_days > 0:
            detail += (f" A second, more important certificate expires in {pca_days} days "
                       f"({PCA_2011_EXPIRY:%d %B %Y}), so this is worth sorting before then.")
        status = STATUS_AT_RISK
    else:
        headline = "This PC has not picked up the new startup certificates yet"
        detail = ("The replacements normally arrive on their own through Windows Update. "
                  "Nothing is wrong right now — this is worth checking before the old ones "
                  "expire.")
        status = STATUS_ACTION_NEEDED

    if partial:
        detail += (" Some of the new certificates did arrive but not all of them, which "
                   "usually means this PC's firmware accepted part of the update and "
                   "stopped.")

    return {
        "status": status,
        "headline": headline,
        "detail": detail,
        # This is the whole point: it is very often fixable, and for free.
        "fixable": True,
        "fix": [
            "Install all pending Windows updates, then reboot and re-scan — the certificates "
            "ship through Windows Update and this alone resolves most machines.",
            "If they still do not appear, check the manufacturer's support page for a UEFI/BIOS "
            "update. Some older firmware needs that first before it will accept the new certificates.",
            "This is a firmware and update problem, not a hardware limit — replacing the machine "
            "is not the fix.",
        ],
        "deadlines": _deadlines(today),
    }


def _deadlines(today: dt.date) -> list[dict[str, Any]]:
    out = []
    for label, when in (
        ("KEK CA 2011 (key exchange)", KEK_2011_EXPIRY),
        ("UEFI CA 2011 (third-party boot)", UEFI_CA_2011_EXPIRY),
        ("Windows Production PCA 2011 (bootloader)", PCA_2011_EXPIRY),
    ):
        days = _days_until(when, today)
        out.append({
            "label": label,
            "date": when.isoformat(),
            "days_remaining": days,
            "passed": days < 0,
        })
    return out
