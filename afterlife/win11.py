"""Windows 11 hardware eligibility.

The CPU generation cut-off is what actually strands working hardware: a machine
can be fast, healthy and perfectly serviceable and still be refused the upgrade
because its processor predates an arbitrary line. This module reproduces
Microsoft's published requirements and, crucially, reports *which* requirement
failed -- because "blocked only by TPM/Secure Boot" is often a firmware setting,
while "blocked by CPU generation" is permanent.

Sources: Microsoft "Windows 11 minimum hardware requirements" and the published
supported-processor lists for Intel, AMD and Qualcomm.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

MIN_RAM_GB = 4.0
MIN_STORAGE_GB = 64.0
MIN_CORES = 2
MIN_CLOCK_MHZ = 1000

UNKNOWN = "UNKNOWN"


class Blocker(str, Enum):
    CPU_GENERATION = "cpu_generation"   # permanent -- hardware cannot be made eligible
    TPM = "tpm"                         # often a firmware toggle (fTPM/PTT)
    SECURE_BOOT = "secure_boot"         # often a firmware toggle
    UEFI = "uefi"                       # may need a disk conversion (MBR2GPT)
    RAM = "ram"                         # upgradable on most laptops
    STORAGE = "storage"                 # upgradable
    CPU_SPEC = "cpu_spec"               # cores/clock/64-bit
    UNKNOWN_TPM = "unknown_tpm"         # probe was denied; not a finding


#: Blockers a technician can clear without replacing the machine.
REMEDIABLE = {
    Blocker.TPM, Blocker.SECURE_BOOT, Blocker.UEFI,
    Blocker.RAM, Blocker.STORAGE,
}

# Intel Core: 8th generation and newer. A handful of 7th-gen parts were added
# later (Surface Studio 2 / specific HQ SKUs).
INTEL_MIN_CORE_GEN = 8
INTEL_7TH_GEN_EXCEPTIONS = {"7820hq", "7920hq", "7700hq", "7440hq"}

# AMD: Zen+ and newer -- Ryzen 2000 series and above.
AMD_MIN_RYZEN_SERIES = 2


@dataclass
class Eligibility:
    eligible: bool | None                 # None when a required fact is unknown
    blockers: list[Blocker] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    cpu_family: str | None = None
    cpu_generation: int | None = None

    @property
    def permanently_blocked(self) -> bool:
        """Blocked by something no amount of servicing can fix."""
        return Blocker.CPU_GENERATION in self.blockers or Blocker.CPU_SPEC in self.blockers

    @property
    def firmware_fixable(self) -> bool:
        """Every blocker is a setting or a cheap part -- the machine is not stranded."""
        return bool(self.blockers) and all(b in REMEDIABLE for b in self.blockers)


def _intel_generation(name: str) -> int | None:
    """Extract Core generation from an Intel model string."""
    low = name.lower()

    # Modern strings carry it explicitly: "11th Gen Intel(R) Core(TM) i5-11400H"
    if m := re.search(r"(\d{1,2})(?:st|nd|rd|th)\s+gen", low):
        return int(m.group(1))

    # Core Ultra (Meteor Lake onward) is always eligible; treat as gen 14+.
    if "core(tm) ultra" in low or "core ultra" in low:
        return 14

    # Fall back to the SKU: i5-8250U -> 8, i5-11400H -> 11, i7-4790 -> 4
    #
    # Digit count alone does NOT determine where the generation ends, and
    # assuming it did stranded every modern laptop this product exists for.
    # Desktop parts went four digits to five at the 10th generation
    # (i5-9600K -> i5-10400), but MOBILE parts stayed at four: i5-1035G1,
    # i5-1135G7, i5-1235U are 10th, 11th and 12th gen respectively. Reading
    # only the first digit of those gives 1, which is below the 8th-gen
    # cut-off, so a healthy Ice Lake or Tiger Lake laptop was reported
    # PERMANENTLY blocked by CPU generation -- the exact false verdict this
    # module exists to prevent, inverted.
    #
    # A leading 1 on a four-digit SKU is unambiguous: first-generation Core
    # parts were three digits (i5-750, i7-920), so nothing else can produce it.
    if m := re.search(r"i[3579][- ](\d{4,5})", low):
        sku = m.group(1)
        if len(sku) == 5 or sku.startswith("1"):
            return int(sku[:2])
        return int(sku[0])

    return None


def _amd_ryzen_series(name: str) -> int | None:
    """Ryzen 5 3500U -> 3 (i.e. the 3000 series)."""
    low = name.lower()
    if m := re.search(r"ryzen\s+\d+\s+(?:pro\s+)?(\d{4})", low):
        return int(m.group(1)[0])
    if m := re.search(r"athlon\s+(?:gold|silver)?\s*(\d{4})", low):
        return int(m.group(1)[0])
    return None


def _check_cpu(name: str | None) -> tuple[list[Blocker], list[str], str | None, int | None]:
    if not name:
        return [], ["CPU name unavailable; generation not assessed"], None, None

    low = name.lower()

    if "intel" in low or re.search(r"\bi[3579][- ]", low):
        gen = _intel_generation(name)
        sku = re.search(r"i[3579][- ](\d{4,5}[a-z]*)", low)
        if sku and sku.group(1) in INTEL_7TH_GEN_EXCEPTIONS:
            return [], ["7th-gen SKU on Microsoft's exception list"], "intel", 7
        if gen is None:
            return [], [f"could not parse Intel generation from {name!r}"], "intel", None
        if gen < INTEL_MIN_CORE_GEN:
            return (
                [Blocker.CPU_GENERATION],
                [f"Intel {gen}th gen is below the 8th-gen cut-off"],
                "intel", gen,
            )
        return [], [], "intel", gen

    if "amd" in low or "ryzen" in low or "athlon" in low:
        series = _amd_ryzen_series(name)
        if series is None:
            return [], [f"could not parse AMD series from {name!r}"], "amd", None
        if series < AMD_MIN_RYZEN_SERIES:
            return (
                [Blocker.CPU_GENERATION],
                [f"AMD Ryzen {series}000 series is below the 2000-series cut-off"],
                "amd", series,
            )
        return [], [], "amd", series

    if "snapdragon" in low or "qualcomm" in low:
        return [], ["Qualcomm part; assumed eligible"], "qualcomm", None

    return [], [f"unrecognised CPU vendor in {name!r}"], None, None


def assess(device: dict[str, Any]) -> Eligibility:
    """Apply Windows 11 requirements to one collector JSON record."""
    blockers: list[Blocker] = []
    notes: list[str] = []

    cpu_blockers, cpu_notes, family, gen = _check_cpu(device.get("cpu_name"))
    blockers += cpu_blockers
    notes += cpu_notes

    cores = device.get("cpu_cores")
    clock = device.get("cpu_max_mhz")
    width = device.get("cpu_address_width")
    if isinstance(cores, int) and cores < MIN_CORES:
        blockers.append(Blocker.CPU_SPEC)
        notes.append(f"{cores} core(s) < {MIN_CORES}")
    if isinstance(clock, int) and clock < MIN_CLOCK_MHZ:
        blockers.append(Blocker.CPU_SPEC)
        notes.append(f"{clock} MHz < {MIN_CLOCK_MHZ}")
    if width == 32:
        blockers.append(Blocker.CPU_SPEC)
        notes.append("32-bit CPU")

    ram = device.get("ram_gb")
    if isinstance(ram, (int, float)) and ram < MIN_RAM_GB:
        blockers.append(Blocker.RAM)
        notes.append(f"{ram} GB RAM < {MIN_RAM_GB}")

    storage = device.get("sysdrive_total_gb")
    if isinstance(storage, (int, float)) and storage < MIN_STORAGE_GB:
        blockers.append(Blocker.STORAGE)
        notes.append(f"{storage} GB system drive < {MIN_STORAGE_GB}")

    tpm_spec = device.get("tpm_spec_version")
    tpm_present = device.get("tpm_present")
    if tpm_present == UNKNOWN or tpm_spec == UNKNOWN:
        blockers.append(Blocker.UNKNOWN_TPM)
        notes.append("TPM probe denied (needs elevation) -- not counted as absent")
    elif tpm_present is False:
        blockers.append(Blocker.TPM)
        notes.append("no TPM detected")
    elif isinstance(tpm_spec, str) and tpm_spec:
        try:
            if float(tpm_spec.split(".")[0] + "." + (tpm_spec.split(".") + ["0"])[1]) < 2.0:
                blockers.append(Blocker.TPM)
                notes.append(f"TPM {tpm_spec} < 2.0")
        except (ValueError, IndexError):
            notes.append(f"unparseable TPM spec {tpm_spec!r}")

    if device.get("uefi") is False:
        blockers.append(Blocker.UEFI)
        notes.append("legacy BIOS, not UEFI")

    if device.get("secure_boot_on") is False:
        blockers.append(Blocker.SECURE_BOOT)
        notes.append("Secure Boot off (capability may still exist)")

    # An unknown TPM means we cannot certify eligibility either way.
    if Blocker.UNKNOWN_TPM in blockers:
        real = [b for b in blockers if b is not Blocker.UNKNOWN_TPM]
        eligible = False if any(b not in REMEDIABLE for b in real) else None
    else:
        eligible = not blockers

    return Eligibility(
        eligible=eligible,
        blockers=blockers,
        notes=notes,
        cpu_family=family,
        cpu_generation=gen,
    )
