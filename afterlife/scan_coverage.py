"""What the deep scan actually managed to read, probe by probe.

THE BUG THIS FIXES
------------------
`build_deep_passport` hardcoded `completeness_pct: 100`. Every deep-scan
passport claimed full coverage regardless of what the collector came back with
-- so a scan that could not read the TPM, could not reach SMART, and found no
battery still asserted, inside a cryptographic signature, that it had seen
everything.

That is the worst shape of wrong this codebase has: confident, checkable by
nobody, and sitting next to figures that are correct. The browser-scan path
already computed its completeness honestly from the fields it received; only the
deep path asserted a constant.

WHY A LIST AND NOT JUST A NUMBER
--------------------------------
A percentage tells someone their scan was 71% complete and leaves them with no
idea what the missing 29% was, or whether it mattered. Most gaps here have a
cause the user can act on -- almost always that the collector was not run
elevated, which is one re-run away -- and a few are simply facts about the
machine, like a desktop having no battery.

So this returns each probe with its own outcome and, where it failed, why. A
partial scan is reported as a partial success: what worked, what did not, and
which of those the user can do something about.
"""
from __future__ import annotations

from typing import Any

#: The collector's sentinel for "asked, could not determine". Distinct from a
#: missing key (never asked) and from a real null (asked, answer is nothing).
UNKNOWN = "UNKNOWN"


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and (not value.strip() or value.strip().upper() == UNKNOWN):
        return False
    return True


#: (key, label, fields, needs_elevation, note-when-missing)
#:
#: `fields` is satisfied when ANY of them came back, because several probes have
#: more than one route to the same fact and only need one of them to land.
PROBES: list[tuple[str, str, tuple[str, ...], bool, str]] = [
    ("identity", "Make and model", ("manufacturer", "model", "make_model"), False,
     "The firmware did not report a model string."),
    ("cpu", "Processor", ("cpu_name",), False,
     "The processor could not be identified."),
    ("memory", "Memory", ("ram_gb",), False,
     "Installed memory could not be read."),
    ("storage", "Storage capacity", ("sysdrive_total_gb", "disk_media_type"), False,
     "The system drive could not be measured."),
    ("disk_health", "Drive health (SMART)", ("disk_health", "smart_predict_failure"), True,
     "SMART data needs an elevated run — right-click and Run as administrator."),
    ("battery", "Battery wear", ("battery_health_pct",), False,
     "No battery was detected. Normal for a desktop; on a laptop it means the "
     "battery report could not be produced."),
    ("tpm", "Security chip (TPM)", ("tpm_present", "tpm_spec_version"), True,
     "The TPM query needs an elevated run, and times out on some machines."),
    ("secure_boot", "Secure Boot state", ("secure_boot_on",), True,
     "Secure Boot state is only readable on a UEFI system, elevated."),
    ("os", "Operating system", ("os_caption", "os_version"), False,
     "The OS build could not be read."),
]


def evaluate(device: dict[str, Any]) -> dict[str, Any]:
    """Per-probe coverage for one collector payload.

    `completeness_pct` here is a measurement, not a constant: the share of
    probes that actually returned something usable.
    """
    elevated = device.get("collected_elevated")
    probes: list[dict[str, Any]] = []

    for key, label, fields, needs_elevation, why in PROBES:
        ok = any(_present(device.get(f)) for f in fields)

        # Not applicable is a third outcome, and collapsing it into "failed"
        # would mark every desktop as an incomplete scan for the crime of having
        # no battery. The collector reports battery_present as a measurement, so
        # an explicit False is a fact about the machine, not a gap in the read.
        if not ok and key == "battery" and device.get("battery_present") is False:
            probes.append({"key": key, "label": label, "ok": None,
                           "why": "No battery — this is a desktop."})
            continue

        entry: dict[str, Any] = {"key": key, "label": label, "ok": ok}
        if not ok:
            entry["why"] = why
            # Only claim elevation is the cause when we know it was not granted.
            # Blaming it for a probe that failed for another reason sends the
            # user to re-run as administrator for nothing.
            entry["fixable"] = bool(needs_elevation and elevated is False)
        probes.append(entry)

    applicable = [p for p in probes if p["ok"] is not None]
    got = sum(1 for p in applicable if p["ok"])
    missing = [p for p in applicable if not p["ok"]]

    return {
        "completeness_pct": round(100 * got / len(applicable)) if applicable else 0,
        "probes": probes,
        "read": got,
        "total": len(applicable),
        "elevated": elevated,
        # The single most useful thing to tell someone with an incomplete scan.
        "rerun_elevated_would_help": any(p.get("fixable") for p in missing),
        # len(applicable), not len(probes): a desktop has eight checks that can
        # return data, and telling it "all 9 returned" while the count beside it
        # reads 8/8 is the kind of small internal contradiction that makes a
        # reader stop trusting the rest of the page.
        "summary": _summary(got, len(applicable), missing, elevated),
    }


def _summary(got: int, total: int, missing: list[dict], elevated: Any) -> str:
    if not missing:
        return f"All {total} checks returned data."

    names = ", ".join(m["label"].lower() for m in missing[:3])
    more = f" and {len(missing) - 3} more" if len(missing) > 3 else ""
    head = f"{got} of {total} checks returned data. Missing: {names}{more}."

    if any(m.get("fixable") for m in missing) and elevated is False:
        return head + (" Re-running the collector as administrator would most "
                       "likely fill these in.")
    return head
