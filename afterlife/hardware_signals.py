"""Turn raw collector fields into display-ready hardware findings.

The collector gathers a lot the passport never showed: Windows hardware-error
events, unexpected shutdowns, crash dumps, Device Manager faults, the Reliability
Monitor index, battery cycle count and per-DIMM memory. All of it was being
collected and discarded at the UI boundary.

This rides alongside the signed passport rather than inside it: the signed payload is what
gets gzipped into the QR code, and that has a hard capacity limit this project has
already hit once. Adding a dozen display fields to the payload would push some
passports past what a scannable QR can hold. Keeping them in the API response only
means the QR stays small and old passports keep verifying byte-for-byte.
"""
from __future__ import annotations

from typing import Any

# Windows Reliability Monitor's stability index runs 1-10. Microsoft's own scale
# treats the low end as an unstable system; these cutoffs mirror how the built-in
# Reliability Monitor colours its own graph rather than being invented here.
RELIABILITY_GOOD = 8.0
RELIABILITY_POOR = 5.0


def _evt(block: dict[str, Any] | None) -> tuple[int | None, str | None]:
    """Returns (count, last_seen); count is None when the log could not be read.

    The collector reports "UNKNOWN" rather than 0 when an event query fails, so a
    machine whose event log is unreadable is never described as having no faults.
    """
    if not isinstance(block, dict):
        return None, None
    raw = block.get("count")
    if raw is None or raw == "UNKNOWN":
        return None, None
    try:
        return int(raw), block.get("last_seen")
    except (TypeError, ValueError):
        return None, None


def _window_phrase(days: Any) -> str:
    """Describe the period actually covered, not the period requested.

    Windows caps the System log and rolls old records out, so the collector's
    90-day query often covers far less -- 13 days on the dev machine. Saying
    "last 90 days" when the log only reaches back 13 would overstate the evidence.
    """
    if not isinstance(days, (int, float)) or days <= 0:
        return "in the available event history"
    d = int(round(days))
    if d >= 88:
        return "in the last 90 days"
    return f"in the last {d} days (all this machine's event log retains)"


def summarize(device: dict[str, Any]) -> dict[str, Any]:
    errs = device.get("hardware_errors") or {}
    whea, whea_at = _evt(errs.get("whea_90d"))
    disk, disk_at = _evt(errs.get("disk_90d"))
    ntfs, ntfs_at = _evt(errs.get("ntfs_90d"))
    shut, shut_at = _evt(errs.get("unexpected_shutdowns_90d"))
    tdr, tdr_at = _evt(errs.get("gpu_tdr_90d"))
    dumps, dumps_at = _evt(device.get("crash_dumps"))

    window = _window_phrase(errs.get("log_window_days"))
    findings: list[dict[str, str]] = []
    # None means the query failed, which is not the same as zero -- track it so the
    # card can say "not read" instead of implying a clean bill of health.
    unreadable = [n for n, v in (("hardware", whea), ("disk", disk), ("filesystem", ntfs),
                                 ("shutdown", shut), ("graphics", tdr)) if v is None]

    # WHEA is the platform's own hardware-error reporting channel. Anything here is
    # a real fault the hardware detected, not an inference from age.
    if whea:
        findings.append({"severity": "serious", "label": "Hardware errors",
                         "detail": f"{whea} hardware error(s) logged by Windows {window}."
                                   f"{f' Most recent {whea_at[:10]}.' if whea_at else ''}"})
    if (disk or 0) or (ntfs or 0):
        findings.append({"severity": "serious", "label": "Disk errors",
                         "detail": f"{(disk or 0) + (ntfs or 0)} disk or filesystem error(s) {window}."})
    if tdr:
        findings.append({"severity": "warning", "label": "Graphics resets",
                         "detail": f"The graphics driver stopped responding and recovered {tdr} time(s) "
                                   f"{window}."})
    if dumps:
        findings.append({"severity": "warning", "label": "Crash dumps",
                         "detail": f"{dumps} blue-screen crash dump(s) on disk."
                                   f"{f' Most recent {dumps_at[:10]}.' if dumps_at else ''}"})
    if shut:
        findings.append({"severity": "info", "label": "Unexpected shutdowns",
                         "detail": f"{shut} unexpected shutdown(s) {window} — a crash, a power "
                                   f"cut, or holding the power button."
                                   f"{f' Most recent {shut_at[:10]}.' if shut_at else ''}"})

    # Device Manager faults, already filtered of the disabled-by-default virtual
    # WAN Miniport adapters that would otherwise flag nearly every Windows install.
    for d in (device.get("device_errors") or [])[:4]:
        findings.append({"severity": "warning", "label": "Device fault",
                         "detail": f"{d.get('name')} is not working properly "
                                   f"(Device Manager code {d.get('error_code')})."})

    idx = device.get("reliability_index")
    reliability = None
    if isinstance(idx, (int, float)):
        reliability = {
            "index": round(float(idx), 1),
            "band": ("good" if idx >= RELIABILITY_GOOD
                     else "poor" if idx < RELIABILITY_POOR else "fair"),
            "note": "Windows' own stability score for this machine, out of 10.",
        }

    battery = None
    cycles = device.get("battery_cycle_count")
    if isinstance(cycles, (int, float)) and cycles > 0:
        battery = {"cycle_count": int(cycles),
                   "note": f"{int(cycles)} charge cycles. Most laptop batteries are rated "
                           f"for 300–1000 before meaningful capacity loss."}

    memory = [m for m in (device.get("memory_sticks") or []) if isinstance(m, dict)]

    return {
        "findings": findings,
        # Three states, not two. `not findings` made a machine whose event logs
        # could not be READ indistinguishable from one with nothing wrong --
        # and `clean` is the field a UI hangs a green tick on.
        #
        # That contradicted this module's own opening promise, that a machine
        # whose event log is unreadable "is never described as having no
        # faults". _evt() and `unreadable` kept the distinction faithfully all
        # the way here and then this line collapsed it again.
        #
        #   True   readable, and nothing found
        #   False  something found
        #   None   nothing found, but not everything could be read
        #
        # Same shape as scan_coverage's per-probe ok flag, and the same bug as
        # the completeness_pct that was hardcoded to 100: an absence of
        # evidence reported as evidence of absence.
        "clean": False if findings else (None if unreadable else True),
        "reliability": reliability,
        "battery": battery,
        "memory_sticks": memory,
        "window": window,
        "unreadable": unreadable,
        "counts": {"whea": whea, "disk": (disk or 0) + (ntfs or 0), "gpu_tdr": tdr,
                   "unexpected_shutdowns": shut, "crash_dumps": dumps,
                   "device_faults": len(device.get("device_errors") or [])},
        "summary": (f"Some event logs could not be read, so this is incomplete."
                    if unreadable and not findings else
                    f"No hardware faults logged {window}." if not findings else
                    f"{len(findings)} hardware signal(s) worth knowing about."),
    }
