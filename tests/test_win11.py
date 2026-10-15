"""Windows 11 eligibility -- the gate the whole product argues about.

This module decides whether a working machine is "stranded by a technicality",
which is AfterLife's central narrative claim, and it shipped untested. The
distinction that carries the argument is not eligible/ineligible but
PERMANENT vs FIXABLE: a CPU-generation block is forever, a TPM or Secure Boot
block is usually one firmware toggle. Getting that backwards would tell someone
to replace a laptop that needed a setting changed.

The CPU string parsing is the fragile part -- real collector output is
inconsistent ("11th Gen Intel(R) Core(TM) i5-11400H", "Intel(R) Core(TM)
i5-8250U CPU @ 1.60GHz", "AMD Ryzen 5 3500U with Radeon Vega Mobile Gfx") --
so it is exercised against strings of the shape the collector actually emits.
"""
from __future__ import annotations

import pytest

from afterlife.win11 import (
    INTEL_MIN_CORE_GEN, REMEDIABLE, Blocker, Eligibility,
    _amd_ryzen_series, _intel_generation, assess,
)


class TestIntelGenerationParsing:
    @pytest.mark.parametrize("name,gen", [
        ("11th Gen Intel(R) Core(TM) i5-11400H", 11),
        ("12th Gen Intel(R) Core(TM) i7-1255U", 12),
        ("8th Gen Intel(R) Core(TM) i5-8250U", 8),
    ])
    def test_explicit_generation_prefix(self, name, gen):
        assert _intel_generation(name) == gen

    @pytest.mark.parametrize("name,gen", [
        ("Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz", 8),
        ("Intel(R) Core(TM) i7-4790 CPU @ 3.60GHz", 4),
        ("Intel(R) Core(TM) i5-11400H", 11),
        ("Intel(R) Core(TM) i5-9300H", 9),
    ])
    def test_falls_back_to_the_sku(self, name, gen):
        """Older collector output carries no "Nth Gen" prefix at all, so the
        SKU is the only signal available."""
        assert _intel_generation(name) == gen

    @pytest.mark.parametrize("name,gen", [
        ("Intel(R) Core(TM) i3-1005G1", 10),   # Ice Lake
        ("Intel(R) Core(TM) i5-1035G1", 10),
        ("Intel(R) Core(TM) i7-1065G7", 10),
        ("Intel(R) Core(TM) i5-1135G7", 11),   # Tiger Lake
        ("Intel(R) Core(TM) i7-1165G7", 11),
        ("Intel(R) Core(TM) i5-1235U", 12),    # Alder Lake
        ("Intel(R) Core(TM) i7-1355U", 13),    # Raptor Lake
    ])
    def test_four_digit_mobile_skus_are_not_first_generation(self, name, gen):
        """REGRESSION. Desktop SKUs went four digits to five at the 10th
        generation; mobile SKUs did not. Reading only the first digit made
        every one of these parse as generation 1 -- below the 8th-gen cut-off --
        so healthy Ice Lake and Tiger Lake laptops were reported PERMANENTLY
        blocked by CPU generation. These are the most common laptop processors
        of 2019-2023 and every one of them is genuinely Windows 11 eligible.
        """
        assert _intel_generation(name) == gen

    @pytest.mark.parametrize("name", [
        "Intel(R) Core(TM) i3-1005G1", "Intel(R) Core(TM) i5-1135G7",
        "Intel(R) Core(TM) i7-1165G7", "Intel(R) Core(TM) i5-1235U",
    ])
    def test_those_machines_are_eligible_end_to_end(self, name):
        """The parse is only half of it: the verdict is what a user is shown."""
        e = assess({"cpu_name": name, "ram_gb": 16.0, "sysdrive_total_gb": 512.0,
                    "cpu_cores": 4, "uefi": True, "secure_boot_on": True,
                    "tpm_present": True, "tpm_spec_version": "2.0",
                    "tpm_enabled": True})
        assert e.eligible is True, f"{name} wrongly ineligible"
        assert e.permanently_blocked is False

    def test_core_ultra_is_treated_as_current(self):
        """Meteor Lake onward dropped the generation number from the name. It
        is unambiguously eligible, so it must not parse as unknown."""
        assert _intel_generation("Intel(R) Core(TM) Ultra 7 155H") >= INTEL_MIN_CORE_GEN

    def test_unparseable_returns_none_rather_than_guessing(self):
        """A wrong generation is worse than no generation: it produces a
        confident verdict the user cannot check."""
        assert _intel_generation("Intel(R) Celeron(R) N4020") is None


class TestAmdSeriesParsing:
    @pytest.mark.parametrize("name,series", [
        ("AMD Ryzen 5 3500U with Radeon Vega Mobile Gfx", 3),
        ("AMD Ryzen 7 5800X 8-Core Processor", 5),
        ("AMD Ryzen 5 PRO 4650U", 4),
        ("AMD Ryzen 3 1200 Quad-Core Processor", 1),
    ])
    def test_series_digit(self, name, series):
        assert _amd_ryzen_series(name) == series

    def test_unparseable_returns_none(self):
        assert _amd_ryzen_series("AMD A9-9425 RADEON R5") is None


class TestTheDistinctionThatCarriesTheArgument:
    """Permanent vs fixable. Getting this backwards sends someone to buy a
    laptop when they needed to change a BIOS setting."""

    def _device(self, **over):
        base = {"cpu_name": "Intel(R) Core(TM) i5-11400H", "ram_gb": 16.0,
                "sysdrive_total_gb": 512.0, "cpu_cores": 6, "uefi": True,
                "secure_boot_on": True, "tpm_present": True,
                "tpm_spec_version": "2.0", "tpm_enabled": True}
        base.update(over)
        return base

    def test_a_modern_machine_is_eligible_with_no_blockers(self):
        e = assess(self._device())
        assert e.eligible is True
        assert e.blockers == []
        assert e.permanently_blocked is False

    def test_old_cpu_is_permanent_not_fixable(self):
        e = assess(self._device(cpu_name="Intel(R) Core(TM) i7-4790 CPU @ 3.60GHz"))
        assert e.eligible is False
        assert Blocker.CPU_GENERATION in e.blockers
        assert e.permanently_blocked is True
        assert e.firmware_fixable is False

    def test_secure_boot_off_is_fixable_not_permanent(self):
        """The exact case the product exists to defend: a healthy machine
        failing the gate on a setting."""
        e = assess(self._device(secure_boot_on=False))
        assert e.eligible is False
        assert e.permanently_blocked is False
        assert e.firmware_fixable is True

    def test_tpm_absent_is_fixable(self):
        e = assess(self._device(tpm_present=False, tpm_enabled=False,
                                tpm_spec_version=None))
        assert e.permanently_blocked is False
        assert e.firmware_fixable is True

    def test_low_ram_is_fixable_because_ram_is_a_part(self):
        e = assess(self._device(ram_gb=2.0))
        assert Blocker.RAM in e.blockers
        assert e.firmware_fixable is True

    def test_an_eligible_machine_is_not_firmware_fixable(self):
        """firmware_fixable means "blocked, but cheaply" -- it must be false
        when nothing is blocking at all, or the UI offers a fix for a
        non-problem."""
        assert assess(self._device()).firmware_fixable is False

    def test_a_mix_of_permanent_and_fixable_reads_as_permanent(self):
        """Clearing the cheap blocker would still leave the machine ineligible,
        so advising a fix here would waste the owner's time."""
        e = assess(self._device(cpu_name="Intel(R) Core(TM) i7-4790", ram_gb=2.0))
        assert e.permanently_blocked is True
        assert e.firmware_fixable is False

    def test_every_remediable_blocker_is_genuinely_remediable(self):
        assert Blocker.CPU_GENERATION not in REMEDIABLE
        assert Blocker.CPU_SPEC not in REMEDIABLE


class TestUnknownIsNotAVerdict:
    def _device(self, **over):
        base = {"cpu_name": "Intel(R) Core(TM) i5-11400H", "ram_gb": 16.0,
                "sysdrive_total_gb": 512.0, "cpu_cores": 6, "uefi": True,
                "secure_boot_on": True, "tpm_present": True,
                "tpm_spec_version": "2.0", "tpm_enabled": True}
        base.update(over)
        return base

    def test_an_unread_tpm_yields_indeterminate_not_ineligible(self):
        """The collector's TPM probe needs elevation and times out on some
        machines. Reporting "not eligible" for a probe that was merely denied
        would condemn a machine on missing evidence."""
        e = assess(self._device(tpm_present="UNKNOWN", tpm_spec_version=None,
                                tpm_enabled="UNKNOWN"))
        assert e.eligible is None
        assert Blocker.UNKNOWN_TPM in e.blockers

    def test_unknown_tpm_is_not_counted_as_permanent(self):
        e = assess(self._device(tpm_present="UNKNOWN", tpm_spec_version=None,
                                tpm_enabled="UNKNOWN"))
        assert e.permanently_blocked is False

    def test_an_unparseable_cpu_does_not_fabricate_a_block(self):
        """No generation is not the same as an old generation."""
        e = assess(self._device(cpu_name="Intel(R) Celeron(R) N4020"))
        assert Blocker.CPU_GENERATION not in e.blockers
        assert any("could not parse" in n.lower() or "not assessed" in n.lower()
                   for n in e.notes)

    def test_a_missing_cpu_name_is_reported_not_guessed(self):
        e = assess(self._device(cpu_name=None))
        assert Blocker.CPU_GENERATION not in e.blockers
        assert e.notes
