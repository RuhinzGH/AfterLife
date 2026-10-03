"""Turn the per-CVE mitigation classification into a per-device keep-or-replace report.

`mitigation.py` answers the question for one CVE. This module answers it for one
*machine*: given the CVEs that apply to its OS and which hardening levers are
already pulled on it, how many of its serious vulnerabilities can be closed
without buying new hardware -- and what exactly is left to do?

The CVE classification is precomputed (`data/raw/win10_cve_classified.csv`, built
by running mitigation.classify over an NVD pull) so a scan never waits on the NVD
API. 1,982 Windows 10 CVEs, already labelled.

The output is deliberately shaped as *actions*, not CVEs. "Disable the Print
Spooler" is one thing a person does; it happens to close 14 CVEs. Listing 14 rows
would be noise.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

SERIOUS = {"HIGH", "CRITICAL"}

#: Windows versions we hold a classified corpus for, and whether Microsoft still
#: ships security updates for them. The support flag drives the framing, not the
#: data: on an end-of-support OS the card is answering "must I replace this?",
#: which is a question people are actively being pushed toward. On a supported OS
#: nobody is pushing that, so asking it would be manufacturing the anxiety this
#: product exists to argue against. Same numbers, different headline.
WINDOWS_VERSIONS: dict[str, dict[str, Any]] = {
    "10": {"label": "Windows 10", "supported": False, "support_ended": "2025-10-14"},
    "11": {"label": "Windows 11", "supported": True, "support_ends": "2031-10-14"},
}


def corpus_path(major: str) -> Path | None:
    """Where the classified corpus for this Windows version lives, if anywhere.

    app_data/ is the shipped-artifact directory: tracked in git and copied into
    the container image. data/raw/ is neither -- it is gitignored working data, so
    a path pointing only there works locally and silently yields nothing in
    production, which is the worst possible failure for a feature whose whole job
    is to tell someone their machine is fine. Prefer the shipped copy, fall back
    to the working copy so a checkout that has run the NVD pull still resolves.
    """
    for base in (ROOT / "app_data", ROOT / "data" / "raw"):
        p = base / f"win{major}_cve_classified.csv"
        if p.exists():
            return p
    return None

#: Maps a mitigation key (from mitigation.SERVICE_CATALOG) to how the collector
#: reports whether it is already handled on this machine, and to the command that
#: would apply it. `check` is the field name the collector emits inside
#: `mitigation_state`; `applied_when` is the value that means "already safe".
#:
#: `command` is shown to the user and can be written into a generated script. Every
#: one is reversible and `undo` gives the exact reversal -- a hardening step nobody
#: can walk back is not a hardening step, it is a trap.
LEVERS: dict[str, dict[str, str]] = {
    "spooler": {
        "plain": "The printing service. If you never print from this PC, it does not need to be running.",
        "label": "Print Spooler",
        "command": "Stop-Service -Name Spooler -Force; Set-Service -Name Spooler -StartupType Disabled",
        "undo": "Set-Service -Name Spooler -StartupType Automatic; Start-Service -Name Spooler",
        "cost": "You cannot print until re-enabled.",
    },
    "smbv1": {
        "plain": "A 1990s way of sharing files that Windows still supports for very old equipment.",
        "label": "SMBv1 file sharing",
        "command": "Disable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -NoRestart",
        "undo": "Enable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol -NoRestart",
        "cost": "Breaks file sharing with pre-2008 devices only. Modern shares use SMBv2/3.",
    },
    "rdp": {
        "plain": "Lets someone control this PC from another computer.",
        "label": "Remote Desktop",
        "command": "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name fDenyTSConnections -Value 1",
        "undo": "Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name fDenyTSConnections -Value 0",
        "cost": "You cannot remote into this machine until re-enabled.",
    },
    "wsh": {
        "plain": "Runs old-style script files. Modern software does not need it.",
        "label": "Windows Script Host",
        "command": "New-Item -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows Script Host\\Settings' -Force | Out-Null; Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows Script Host\\Settings' -Name Enabled -Value 0",
        "undo": "Set-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows Script Host\\Settings' -Name Enabled -Value 1",
        "cost": "Legacy .vbs/.js installers stop working. Rare on modern systems.",
    },
    "webdav": {
        "plain": "Lets you open a website folder as if it were a drive. Rarely used now.",
        "label": "WebDAV (WebClient service)",
        "command": "Stop-Service -Name WebClient -Force; Set-Service -Name WebClient -StartupType Disabled",
        "undo": "Set-Service -Name WebClient -StartupType Manual; Start-Service -Name WebClient",
        "cost": "Breaks mapping web folders as drives. Uncommon.",
    },
    "remote_registry": {
        "plain": "Lets another computer change this PC's settings over the network.",
        "label": "Remote Registry",
        "command": "Stop-Service -Name RemoteRegistry -Force; Set-Service -Name RemoteRegistry -StartupType Disabled",
        "undo": "Set-Service -Name RemoteRegistry -StartupType Manual",
        "cost": "Remote admin tools that edit this machine's registry stop working.",
    },
    "psv2": {
        "plain": "An outdated version of PowerShell kept only for very old scripts.",
        "label": "PowerShell 2.0 engine",
        "command": "Disable-WindowsOptionalFeature -Online -FeatureName MicrosoftWindowsPowerShellV2Root -NoRestart",
        "undo": "Enable-WindowsOptionalFeature -Online -FeatureName MicrosoftWindowsPowerShellV2Root -NoRestart",
        "cost": "None in practice -- PowerShell 5.1+ stays. v2 is a downgrade-attack surface.",
    },
    "search": {
        "plain": "The background service that makes Start-menu search instant.",
        "label": "Windows Search indexer",
        "command": "Stop-Service -Name WSearch -Force; Set-Service -Name WSearch -StartupType Disabled",
        "undo": "Set-Service -Name WSearch -StartupType Automatic; Start-Service -Name WSearch",
        "cost": "Start-menu and Explorer search get slower (they still work).",
    },
    "remote_assist": {
        "plain": "Lets someone request to take over your screen to help you.",
        "label": "Remote Assistance",
        "command": "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Remote Assistance' -Name fAllowToGetHelp -Value 0",
        "undo": "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Remote Assistance' -Name fAllowToGetHelp -Value 1",
        "cost": "Nobody can offer you Remote Assistance until re-enabled.",
    },
    "fax": {
        "plain": "Yes -- Windows still includes a fax service.",
        "label": "Fax service",
        "command": "Stop-Service -Name Fax -Force -ErrorAction SilentlyContinue; Set-Service -Name Fax -StartupType Disabled -ErrorAction SilentlyContinue",
        "undo": "Set-Service -Name Fax -StartupType Manual",
        "cost": "None unless this machine sends faxes.",
    },
    "bluetooth": {
        "plain": "The Bluetooth radio, for wireless mice, keyboards and headphones.",
        "label": "Bluetooth stack",
        "command": "Stop-Service -Name bthserv -Force; Set-Service -Name bthserv -StartupType Disabled",
        "undo": "Set-Service -Name bthserv -StartupType Manual; Start-Service -Name bthserv",
        "cost": "Bluetooth mice, keyboards and headphones stop working.",
    },
}

#: Levers whose cost is high enough that we never put them in a generated script
#: by default -- they are reported, but applying them is an explicit human choice.
HIGH_FRICTION = {"bluetooth", "rdp", "search"}

#: Plain-English "what is this thing" for the display-only classes.
PLAIN_ONLY: dict[str, str] = {
    "application": "Ordinary apps like browsers and PDF readers. These update themselves, "
                   "separately from Windows.",
    "network": "Changing router or firewall settings so the flaw cannot be reached from outside.",
    "hyperv": "A tool for running virtual machines. Most people never turn it on.",
    "iis": "Software for hosting a website from this PC. Not needed on a normal laptop.",
    "ie": "Internet Explorer, and the old page-rendering engine some apps still use.",
    "os": "Upgrading Windows in place, keeping the same machine.",
    "macros": "Little automated programs that can be embedded in Office documents.",
    "dotnet": "A Microsoft software framework many apps rely on. It updates on its own schedule.",
    "snmp": "A protocol for remotely monitoring equipment. Uncommon on personal machines.",
    "legacy_net": "Very old ways of connecting to other computers, replaced long ago.",
    "name_resolution": "Older methods Windows uses to find other devices on your network.",
}

#: Display names for classes that have no single command (so no LEVERS entry) but
#: still need to read as English rather than a raw catalogue key.
DISPLAY_ONLY: dict[str, str] = {
    "application": "Application updates",
    "network": "Network segmentation",
    "hyperv": "Hyper-V role",
    "iis": "IIS web server role",
    "ie": "Internet Explorer / MSHTML",
    "os": "In-place OS upgrade",
    "macros": "Office macros & OLE",
    "dotnet": ".NET Framework servicing",
    "snmp": "SNMP",
    "legacy_net": "Telnet / FTP",
    "name_resolution": "LLMNR / NetBIOS / WPAD",
}


@dataclass
class Action:
    """One thing a person can do, and what it buys."""
    key: str
    label: str
    plain: str | None   # what the thing actually is, for someone who isn't an admin
    action: str
    klass: str
    cves_closed: int
    max_severity: str
    source: str | None = None
    command: str | None = None
    undo: str | None = None
    cost: str | None = None
    applied: bool | None = None  # None = we could not tell

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "plain": self.plain,
            "action": self.action,
            "class": self.klass, "cves_closed": self.cves_closed,
            "max_severity": self.max_severity, "source": self.source,
            "command": self.command, "undo": self.undo, "cost": self.cost,
            "applied": self.applied,
        }


@dataclass
class Report:
    """The keep-or-replace verdict, split four ways.

    The split matters more than any single number. "Unmitigable" on its own reads
    as damning -- until you notice 90% of that bucket needs an attacker already
    sitting at the keyboard, which is a completely different risk class from
    something reachable across the internet. Collapsing those two into one figure
    is how a working machine gets condemned.
    """
    os_label: str
    os_major: str                # "10" | "11" -- which corpus these counts came from
    os_supported: bool           # still receiving security updates? drives the framing
    serious_cves: int
    fixable_cves: int            # documented vendor fix, hardware kept
    isolation_cves: int          # reduced by segmentation, defect remains
    local_access_cves: int       # attacker must already be on the device
    remote_no_lever_cves: int    # genuinely residual
    remote_no_creds_cves: int    # residual AND needs no credentials -- the real tail
    app_update_cves: int
    actions: list[Action] = field(default_factory=list)
    already_applied: int = 0
    outstanding: int = 0
    unknown_state: int = 0

    @property
    def fixable_share(self) -> float:
        return self.fixable_cves / self.serious_cves if self.serious_cves else 0.0

    @property
    def addressable_share(self) -> float:
        """Fixable, segmentable, or requiring local access -- i.e. not an argument
        for replacing the hardware."""
        if not self.serious_cves:
            return 0.0
        return (self.fixable_cves + self.isolation_cves + self.local_access_cves) / self.serious_cves

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": True,
            "os_label": self.os_label,
            "os_major": self.os_major,
            "os_supported": self.os_supported,
            "serious_cves": self.serious_cves,
            "fixable_cves": self.fixable_cves,
            "fixable_share": round(self.fixable_share, 3),
            "isolation_cves": self.isolation_cves,
            "local_access_cves": self.local_access_cves,
            "remote_no_lever_cves": self.remote_no_lever_cves,
            "remote_no_creds_cves": self.remote_no_creds_cves,
            "addressable_share": round(self.addressable_share, 3),
            "app_update_cves": self.app_update_cves,
            "already_applied": self.already_applied,
            "outstanding": self.outstanding,
            "unknown_state": self.unknown_state,
            "actions": [a.as_dict() for a in self.actions],
        }


def detect_windows_major(os_caption: str | None) -> str | None:
    """Which Windows version this is, if it is one we hold a corpus for.

    Matching the version explicitly rather than defaulting to Windows 10 matters:
    the earlier version labelled the report with whatever OS the device reported
    while counting from the Windows 10 corpus, so a Windows 11 laptop was shown
    another operating system's vulnerability count as its own.
    """
    if not os_caption:
        return None
    c = os_caption.lower()
    for major in WINDOWS_VERSIONS:
        if f"windows {major}" in c:
            return major
    return None


def is_covered_os(os_caption: str | None) -> bool:
    """True when we hold a corpus for this OS *and* the file is actually present."""
    major = detect_windows_major(os_caption)
    return bool(major and corpus_path(major))


@lru_cache(maxsize=4)
def load_classified(major: str = "10") -> list[dict[str, str]]:
    """The precomputed CVE classification. Cached -- it never changes at runtime."""
    p = corpus_path(major)
    if not p:
        return []
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _severity_rank(s: str) -> int:
    return {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}.get((s or "").upper(), 0)


def build_report(
    os_caption: str | None = None,
    mitigation_state: dict[str, Any] | None = None,
    os_upgradable: bool = False,
) -> Report | None:
    """Roll the classified CVEs up into a per-device report.

    `mitigation_state` is what the collector observed on this machine, keyed by
    lever (see LEVERS). A key that is absent, or whose value is None, means we
    could not determine it -- reported as unknown rather than guessed, because
    telling someone they are protected when we did not check is the one failure
    mode that actually matters here.
    """
    # Count from the corpus that actually matches this machine's OS. Anything
    # else means showing one operating system's vulnerability count as another's.
    major = detect_windows_major(os_caption)
    if not major:
        return None
    rows = load_classified(major)
    if not rows:
        return None

    serious = [r for r in rows if (r.get("severity") or "").upper() in SERIOUS]
    if not serious:
        return None

    state = mitigation_state or {}

    # Group by the distinct action text -- one row per thing a human does.
    grouped: dict[str, dict[str, Any]] = {}
    counts = {"unmitigable": 0, "network_isolate": 0, "service_disable": 0, "app_update": 0, "os_upgrade": 0}
    local_access = remote_no_lever = remote_no_creds = 0

    for r in serious:
        klass = (r.get("mitigation_class") or "").strip()
        counts[klass] = counts.get(klass, 0) + 1
        if klass == "unmitigable":
            # Split the residual bucket by how reachable it actually is. A local-only
            # flaw and an internet-facing one are not the same argument.
            if (r.get("attack_vector") or "") in ("LOCAL", "PHYSICAL"):
                local_access += 1
            else:
                remote_no_lever += 1
                if (r.get("privileges_required") or "").upper() == "NONE":
                    remote_no_creds += 1
        if klass in ("unmitigable", "network_isolate"):
            continue  # not an action a user takes on this screen
        key = (r.get("component") or klass).strip() or klass
        g = grouped.setdefault(key, {
            "key": key, "action": (r.get("action") or "").strip(), "klass": klass,
            "source": (r.get("source") or "").strip() or None, "n": 0, "sev": "LOW",
        })
        g["n"] += 1
        if _severity_rank(r.get("severity", "")) > _severity_rank(g["sev"]):
            g["sev"] = (r.get("severity") or "LOW").upper()

    actions: list[Action] = []
    for key, g in grouped.items():
        lever = LEVERS.get(key, {})
        raw = state.get(key)
        applied: bool | None
        if raw is None or (isinstance(raw, str) and raw.upper() == "UNKNOWN"):
            applied = None
        else:
            applied = bool(raw)
        actions.append(Action(
            key=key,
            label=lever.get("label") or DISPLAY_ONLY.get(key) or key.replace("_", " ").title(),
            plain=lever.get("plain") or PLAIN_ONLY.get(key),
            action=g["action"], klass=g["klass"], cves_closed=g["n"], max_severity=g["sev"],
            source=g["source"], command=lever.get("command"), undo=lever.get("undo"),
            cost=lever.get("cost"), applied=applied,
        ))

    # Biggest wins first; unknown-state before known-applied so the actionable
    # items are never buried under a wall of green ticks.
    actions.sort(key=lambda a: (a.applied is True, -a.cves_closed))

    fixable = counts.get("service_disable", 0) + counts.get("app_update", 0) + counts.get("os_upgrade", 0)
    meta = WINDOWS_VERSIONS[major]
    return Report(
        os_label=meta["label"],
        os_major=major,
        os_supported=bool(meta["supported"]),
        serious_cves=len(serious),
        fixable_cves=fixable,
        isolation_cves=counts.get("network_isolate", 0),
        local_access_cves=local_access,
        remote_no_lever_cves=remote_no_lever,
        remote_no_creds_cves=remote_no_creds,
        app_update_cves=counts.get("app_update", 0),
        actions=actions,
        already_applied=sum(1 for a in actions if a.applied is True),
        outstanding=sum(1 for a in actions if a.applied is False),
        unknown_state=sum(1 for a in actions if a.applied is None),
    )
