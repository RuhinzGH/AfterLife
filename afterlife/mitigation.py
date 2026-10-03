"""Can this vulnerability be neutralised without replacing the hardware?

This is the core of Afterlife's argument. Existing tooling treats an end-of-life
OS as a replace trigger. We ask a narrower question per CVE: is there a documented
action -- update an app, turn off a service, upgrade the OS in place, segment the
network -- that removes or materially reduces the exposure while keeping the device?

Every SERVICE_DISABLE rule below points at a real vendor advisory. We are not
inventing mitigations; we are counting ones the vendor already published.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .nvd import Vuln


class MitigationClass(str, Enum):
    APP_UPDATE = "app_update"            # vulnerable component updates independently of the OS
    SERVICE_DISABLE = "service_disable"  # vendor-documented config change removes the surface
    OS_UPGRADE = "os_upgrade"            # hardware supports a still-supported OS, in place
    NETWORK_ISOLATE = "network_isolate"  # remote-only; segmentation reduces but does not remove
    UNMITIGABLE = "unmitigable"          # local/physical vector, no config lever -> argues replace


#: Ordered; first match wins. Sources are the advisories that document the toggle.
SERVICE_CATALOG: list[tuple[str, str, str, str]] = [
    (
        r"\b(print spooler|spoolsv|printnightmare|point and print)\b",
        "Stop and disable the Print Spooler service on devices that do not print",
        "Microsoft ADV / KB5005010",
        "spooler",
    ),
    (
        r"\b(smbv1|smb1|server message block.{0,20}(1|v1))\b",
        "Remove the SMBv1 feature (Disable-WindowsOptionalFeature SMB1Protocol)",
        "Microsoft KB2696547",
        "smbv1",
    ),
    (
        r"\b(remote desktop|terminal services|rdp|bluekeep)\b",
        "Disable Remote Desktop, or require Network Level Authentication and gate by firewall",
        "Microsoft CVE-2019-0708 guidance",
        "rdp",
    ),
    (
        r"\b(adobe type manager|atmfd\.dll|type 1 font)\b",
        "Disable the ATM font parser via the DisableATMFD registry key",
        "Microsoft ADV200006",
        "fonts",
    ),
    (
        r"\b(windows script host|wscript|cscript|\.hta\b|mshta)\b",
        "Disable Windows Script Host and block .hta execution by policy",
        "Microsoft WSH administration guidance",
        "wsh",
    ),
    (
        r"\b(webdav|webclient service)\b",
        "Stop and disable the WebClient (WebDAV) service",
        "Microsoft WebDAV advisory guidance",
        "webdav",
    ),
    (
        r"\b(llmnr|netbios|wpad)\b",
        "Disable LLMNR/NetBIOS name resolution and WPAD by Group Policy",
        "Microsoft name-resolution hardening guidance",
        "name_resolution",
    ),
    (
        r"\b(remote registry)\b",
        "Disable the Remote Registry service",
        "Microsoft security baseline",
        "remote_registry",
    ),
    (
        r"\b(powershell 2\.0|powershellv2)\b",
        "Remove the PowerShell 2.0 engine optional feature",
        "Microsoft PowerShell 2.0 deprecation guidance",
        "psv2",
    ),
    (
        r"\b(internet explorer|mshtml|trident|ie mode)\b",
        "Disable Internet Explorer / MSHTML rendering and set Edge as the only browser",
        "Microsoft IE retirement + ADV guidance",
        "ie",
    ),
    (
        r"\b(office macro|vba macro|ole object)\b",
        "Block macros from the internet and disable OLE embedding by policy",
        "Microsoft macro-blocking guidance",
        "macros",
    ),
    (
        r"\b(telnet|ftp server)\b",
        "Remove the Telnet/FTP optional features",
        "Microsoft optional feature guidance",
        "legacy_net",
    ),
    (
        r"\b(snmp)\b",
        "Remove the SNMP optional feature or restrict to a management VLAN",
        "Microsoft SNMP deprecation guidance",
        "snmp",
    ),
    (
        r"\b(hyper-v)\b",
        "Remove the Hyper-V role on endpoints that do not host VMs",
        "Microsoft Hyper-V role guidance",
        "hyperv",
    ),
    (
        r"\b(bluetooth)\b",
        "Disable the Bluetooth radio/stack by policy where unused",
        "Microsoft Bluetooth hardening guidance",
        "bluetooth",
    ),
    (
        r"\b(remote assistance)\b",
        "Disable Remote Assistance by Group Policy",
        "Microsoft security baseline",
        "remote_assist",
    ),
    (
        r"\b(fax service|windows fax)\b",
        "Remove the Fax and Scan optional feature",
        "Microsoft optional feature guidance",
        "fax",
    ),
    (
        r"\b(windows search|indexing service)\b",
        "Disable the Windows Search indexer where not required",
        "Microsoft service hardening guidance",
        "search",
    ),
    (
        r"\b(iis|http\.sys|internet information services)\b",
        "Remove the IIS role from endpoints",
        "Microsoft IIS guidance",
        "iis",
    ),
    (
        r"\b(\.net framework|dotnet)\b",
        "Patch the .NET Framework independently of the OS servicing channel",
        "Microsoft .NET servicing policy",
        "dotnet",
    ),
]

_COMPILED = [(re.compile(p, re.I), action, source, key) for p, action, source, key in SERVICE_CATALOG]


@dataclass(frozen=True)
class Mitigation:
    cve_id: str
    klass: MitigationClass
    action: str
    source: str | None = None
    component: str | None = None

    @property
    def keeps_hardware(self) -> bool:
        return self.klass is not MitigationClass.UNMITIGABLE

    @property
    def fully_remediates(self) -> bool:
        """Isolation reduces exposure without removing the defect; the others remove it."""
        return self.klass in (
            MitigationClass.APP_UPDATE,
            MitigationClass.SERVICE_DISABLE,
            MitigationClass.OS_UPGRADE,
        )


def classify(vuln: Vuln, os_upgradable: bool = False) -> Mitigation:
    if vuln.is_application_layer:
        return Mitigation(
            vuln.cve_id,
            MitigationClass.APP_UPDATE,
            "Update the affected application; it services independently of the OS",
            component="application",
        )

    haystack = f"{vuln.description} {' '.join(vuln.cpe_criteria)}"
    for pattern, action, source, key in _COMPILED:
        if pattern.search(haystack):
            return Mitigation(
                vuln.cve_id, MitigationClass.SERVICE_DISABLE, action, source, key
            )

    if os_upgradable:
        return Mitigation(
            vuln.cve_id,
            MitigationClass.OS_UPGRADE,
            "In-place upgrade to a supported OS build; hardware meets requirements",
            component="os",
        )

    if vuln.remotely_reachable and vuln.privileges_required == "NONE":
        return Mitigation(
            vuln.cve_id,
            MitigationClass.NETWORK_ISOLATE,
            "Segment to a restricted VLAN and block inbound access at the host firewall",
            component="network",
        )

    return Mitigation(
        vuln.cve_id,
        MitigationClass.UNMITIGABLE,
        "No documented mitigation that preserves current use; re-role or replace",
    )


@dataclass
class DeviceVerdict:
    total_cves: int
    serious_cves: int
    counts: dict[str, int]
    mitigations: list[Mitigation]
    os_upgradable: bool

    @property
    def blocking(self) -> list[Mitigation]:
        """Serious CVEs with no hardware-preserving fix at all."""
        return [m for m in self.mitigations if m.klass is MitigationClass.UNMITIGABLE]

    @property
    def strictly_mitigable(self) -> bool:
        """Conservative: every serious CVE is fully remediated without new hardware.

        Network isolation does NOT count here -- it lowers exposure but leaves the
        defect in place. This is the figure we quote.
        """
        return bool(self.mitigations) and all(m.fully_remediates for m in self.mitigations)

    @property
    def mitigable_with_isolation(self) -> bool:
        """Upper bound: isolation accepted as a compensating control."""
        return bool(self.mitigations) and all(m.keeps_hardware for m in self.mitigations)


SERIOUS = {"HIGH", "CRITICAL"}


def assess_device(
    vulns: Iterable[Vuln],
    os_upgradable: bool = False,
    severity_floor: set[str] = SERIOUS,
) -> DeviceVerdict:
    """Roll per-CVE classifications up to a keep/replace verdict for one device.

    Only HIGH/CRITICAL CVEs gate the verdict: a device is not worth replacing over
    a medium-severity issue, and including them would inflate the mitigable share
    with easy wins.
    """
    all_vulns = list(vulns)
    serious = [v for v in all_vulns if (v.severity or "").upper() in severity_floor]
    mitigations = [classify(v, os_upgradable) for v in serious]

    counts: dict[str, int] = {k.value: 0 for k in MitigationClass}
    for m in mitigations:
        counts[m.klass.value] += 1

    return DeviceVerdict(
        total_cves=len(all_vulns),
        serious_cves=len(serious),
        counts=counts,
        mitigations=mitigations,
        os_upgradable=os_upgradable,
    )
