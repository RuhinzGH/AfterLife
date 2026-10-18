"""A processor's rated power class, read from its model name.

The carbon payback compares the power an old machine draws with a replacement's.
Without a processor name it assumes a 45 W performance laptop chip. A deep scan
reads the real name (e.g. "Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz"), and Intel
and AMD publish what each model suffix means: U is a 15 W thin-and-light part,
H a 45 W performance part, and so on. That class is what this returns.

It is the manufacturer's rated (design) power for that class, not a measurement
of this machine, and the carbon card says so. Unrecognised names (Apple silicon,
older or unusual chips) return None and the default stays, labelled as assumed.
"""
from __future__ import annotations

import re
from typing import Any

#: Rated power in watts by model suffix (laptop parts unless noted).
INTEL_SUFFIX_W = {
    "Y": 7,      # fanless ultra-low power
    "U": 15,     # thin-and-light
    "G": 15,     # 10th/11th-gen thin-and-light (e.g. i5-1035G1; 11th-gen parts run 12-28 W, 15 W typical)
    "V": 17,     # Core Ultra 200V
    "P": 28,     # 12th/13th-gen performance thin
    "H": 45, "HQ": 45, "HK": 45,   # performance laptop
    "HX": 55,    # top laptop parts
}
INTEL_ULTRA_H_W = 28          # Core Ultra "H" parts are rated 28 W base power, not 45 W
INTEL_DESKTOP_W = {"": 65, "F": 65, "T": 35, "K": 125, "KF": 125}
AMD_SUFFIX_W = {"U": 15, "HS": 35, "H": 45, "HX": 55}
AMD_DESKTOP_W = {"": 65, "G": 65, "X": 105}

_INTEL = re.compile(r"\b(core\s*ultra\s*[3579]|i[3579])[\s-]*(\d{3,5})([a-z]{0,2})\d?\b", re.I)
_AMD = re.compile(r"\bryzen\s*(?:ai\s*)?[3579]\s*(?:pro\s*)?(\d{3,4})([a-z]{0,2})\b", re.I)


def rated_power(cpu_name: str | None, product_category: str | None = None) -> dict[str, Any] | None:
    """{"watts", "model", "suffix", "maker"} or None when the class can't be told."""
    if not cpu_name:
        return None
    desktop = product_category == "Desktop computer"
    name = re.sub(r"\((r|tm)\)|®|™", " ", cpu_name, flags=re.I)
    m = _INTEL.search(name)
    if m:
        family, suffix = m.group(1).lower(), m.group(3).upper()
        ultra = family.startswith("core")
        if ultra and suffix == "H":
            watts = INTEL_ULTRA_H_W
        elif suffix in INTEL_SUFFIX_W:
            watts = INTEL_SUFFIX_W[suffix]
        elif desktop and suffix in INTEL_DESKTOP_W:
            watts = INTEL_DESKTOP_W[suffix]
        else:
            return None
        return {"watts": watts, "model": " ".join(m.group(0).split()), "suffix": suffix or "none", "maker": "Intel"}
    m = _AMD.search(name)
    if m:
        suffix = m.group(2).upper()
        if suffix in AMD_SUFFIX_W:
            watts = AMD_SUFFIX_W[suffix]
        elif desktop and suffix in AMD_DESKTOP_W:
            watts = AMD_DESKTOP_W[suffix]
        else:
            return None
        return {"watts": watts, "model": " ".join(m.group(0).split()), "suffix": suffix or "none", "maker": "AMD"}
    return None
