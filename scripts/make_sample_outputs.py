"""Write example outputs of the API to docs/sample_outputs/, for the README.

    set PYTHONPATH=.
    venv\\Scripts\\python scripts\\make_sample_outputs.py

Runs the real API in-process (FastAPI's test client) on one example laptop:
an instant scan, the signed passport it produces, the full assessment, and a
verification of that passport before and after one value is edited. No network
calls; the passport is signed with this machine's local key, so it verifies as
"issued by AfterLife" only on the server that made it.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app

OUT = Path(__file__).resolve().parent.parent / "docs" / "sample_outputs"

# What a browser reports for a typical Windows laptop, plus the owner's answers.
SCAN = {
    "os": "Windows 11 (build 15.0.0)", "os_family": "Windows", "architecture": "x86 64",
    "gpu": "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "cpu_cores": 8, "ram_gb": 8, "screen": "1920×1080", "timezone": "Asia/Kolkata",
    "source": "browser-scan",
    "device_age": 6, "product_category": "Laptop", "problem": "battery drains fast",
}


def write(name: str, data: dict) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT / name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    c = TestClient(app)

    write("1_browser_scan_input.json", SCAN)

    passport = c.post("/api/scan-passport", json=SCAN).json()
    write("2_signed_passport.json", passport)

    lc = passport["payload"].get("lifecycle", {})
    assessment = c.post("/api/assess", json={
        "eol_risk": lc.get("eol_risk"), "age_years": SCAN["device_age"],
        "fault_described": lc.get("fault_described", False),
        "fault_detail": ", ".join(lc.get("fault_themes") or []) or None,
        "make_model": SCAN["os"], "os": SCAN["os"], "product_category": "Laptop",
        "timezone": SCAN["timezone"], "persona": "coding",
        "cores": SCAN["cpu_cores"], "ram_gb": SCAN["ram_gb"], "gpu": SCAN["gpu"],
        "problem": SCAN["problem"],
    }).json()
    write("3_assessment.json", assessment)

    genuine = c.post("/api/verify", json={"passport": passport}).json()
    tampered_doc = copy.deepcopy(passport)
    tampered_doc["payload"]["ram_gb"] = 32
    tampered = c.post("/api/verify", json={"passport": tampered_doc}).json()
    write("4_verify_genuine_and_tampered.json", {"genuine": genuine, "after_editing_ram_8_to_32": tampered})


if __name__ == "__main__":
    main()
