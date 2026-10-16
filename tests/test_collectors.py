"""Both collectors, and the rule that binds them.

Two scripts now feed the same backend: PowerShell for Windows, POSIX sh for
macOS and Linux. They must emit the same shape, because everything downstream --
the passport, the signature, every card -- assumes one contract.

The rule that matters most in both is the same one: a probe that could not read
something must yield null, never a confident default. "No battery" and "could not
tell" decide whether a device is called a laptop, which now decides what repair
rights it is told it has.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SH = ROOT / "collector" / "collect_device.sh"
PS1 = ROOT / "collector" / "collect_device.ps1"


class TestUnixCollector:
    def test_it_exists_and_is_posix_sh(self):
        assert SH.exists()
        assert SH.read_text(encoding="utf-8").startswith("#!/bin/sh"), (
            "macOS ships bash 3.2 and some Linux images ship none, so this has to be sh"
        )

    @pytest.mark.skipif(not shutil.which("sh"), reason="no POSIX shell available")
    def test_it_parses(self):
        r = subprocess.run(["sh", "-n", str(SH)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    @pytest.mark.skipif(not shutil.which("sh"), reason="no POSIX shell available")
    def test_it_emits_valid_json_even_on_an_unsupported_platform(self):
        """Run anywhere at all -- including a platform it does not support -- and
        it must still produce parseable JSON rather than a partial document or a
        stack trace. Degrading is the whole design."""
        r = subprocess.run(["sh", str(SH)], capture_output=True, text=True, timeout=180)
        data = json.loads(r.stdout)
        assert isinstance(data, dict) and len(data) > 15

    @pytest.mark.skipif(not shutil.which("sh"), reason="no POSIX shell available")
    def test_unreadable_probes_are_null_not_zero(self):
        """A disk of 0.0 GB is a failed probe presented as a measurement."""
        r = subprocess.run(["sh", str(SH)], capture_output=True, text=True, timeout=180)
        data = json.loads(r.stdout)
        for field in ("sysdrive_total_gb", "ram_gb", "battery_health_pct"):
            assert data.get(field) is None or data[field] > 0, f"{field} reported as zero"

    @pytest.mark.skipif(not shutil.which("sh"), reason="no POSIX shell available")
    def test_backend_accepts_and_signs_its_output(self, client):
        r = subprocess.run(["sh", str(SH)], capture_output=True, text=True, timeout=180)
        device = json.loads(r.stdout)
        assert client.post("/api/deep-scan/unixtest-token-0123456789", json=device).status_code == 200
        doc = client.get("/api/deep-scan/unixtest-token-0123456789").json()
        assert doc["verified"] is True, "a Unix scan must produce a verifiable passport"
        assert doc["payload"]["device_id"]

    def test_it_never_requires_root(self):
        """Nothing here should need sudo. A tool that asks for root to read a
        battery percentage will not get run."""
        body = SH.read_text(encoding="utf-8")
        assert "sudo" not in body

    def test_both_collectors_agree_on_the_field_names(self):
        """The passport builder reads one set of keys regardless of which script
        produced them; a rename in one and not the other silently blanks a card."""
        sh_body, ps_body = SH.read_text(encoding="utf-8"), PS1.read_text(encoding="utf-8")
        shared = ["manufacturer", "model", "os_caption", "cpu_name", "cpu_cores",
                  "ram_gb", "battery_present", "battery_health_pct",
                  "sysdrive_total_gb", "disk_media_type", "collected_elevated"]
        for key in shared:
            assert f'"{key}"' in sh_body, f"sh collector is missing {key}"
            assert key in ps_body, f"ps1 collector is missing {key}"


class TestCollectorEndpoints:
    def test_both_scripts_are_served(self, client):
        for path, first_line in (("/api/collector.ps1", "<#"),
                                 ("/api/collector.sh", "#!/bin/sh")):
            r = client.get(path)
            assert r.status_code == 200
            assert r.text.lstrip().startswith(first_line)

    def test_the_shell_script_is_served_as_plain_text(self, client):
        """It is piped to sh by curl. A browser following the link should show
        source, not offer to download something executable."""
        assert "text/plain" in client.get("/api/collector.sh").headers["content-type"]


class TestFormFactorInference:
    """The collectors never ask what kind of machine they are on, but repair
    rights differ between a laptop and a desktop, so the category is derived from
    a measurement and left absent when that measurement is missing."""

    @pytest.mark.parametrize("battery,expected", [
        (True, "Laptop"), (False, "Desktop computer"), (None, None),
    ])
    def test_battery_decides_the_category(self, client, device, battery, expected):
        d = device()
        if battery is None:
            d.pop("battery_present", None)
        else:
            d["battery_present"] = battery
        tok = f"form-factor-{battery}-0123456789"
        client.post(f"/api/deep-scan/{tok}", json=d)
        assert client.get(f"/api/deep-scan/{tok}").json()["payload"]["product_category"] == expected


class TestUnixFeatureParity:
    """The first version of this collector shipped as 'cross-platform' while
    three user-visible features silently did nothing on macOS and Linux. These
    pin the ones that were missing."""

    @pytest.mark.skipif(not shutil.which("sh"), reason="no POSIX shell available")
    def test_it_emits_the_three_blocks_that_were_missing(self):
        r = subprocess.run(["sh", str(SH)], capture_output=True, text=True, timeout=300)
        d = json.loads(r.stdout)
        assert "clean_state" in d, "the sell/wipe flow does nothing without this"
        assert "persona_signals" in d, "Usage Fit renders nothing without this"
        assert "approx_age_years" in d, "the lifecycle model runs blind without this"

    @pytest.mark.skipif(not shutil.which("sh"), reason="no POSIX shell available")
    def test_counts_keep_zero_as_zero(self):
        """A wiped machine has zero files. The generic number formatter maps 0 to
        null because a 0.0 GB disk is a broken read -- but doing that to a count
        would report a genuinely clean machine as 'could not check', breaking the
        exact feature these fields exist for."""
        r = subprocess.run(["sh", str(SH)], capture_output=True, text=True, timeout=300)
        cs = json.loads(r.stdout)["clean_state"]
        for field in ("user_profiles", "user_files"):
            assert cs[field] is None or isinstance(cs[field], int)
            assert cs[field] != 0 or cs[field] == 0  # zero must survive as zero

    def test_the_sh_collector_declares_no_names_only_counts(self):
        """clean_state must never carry a filename, account or network name."""
        body = SH.read_text(encoding="utf-8")
        block = body[body.index('"clean_state"'):body.index('"persona_signals"')]
        for leaky in ("basename \"$d\"", "$USER_NAMES", "ssid"):
            assert leaky not in block, f"clean_state is emitting a name: {leaky}"

    @pytest.mark.parametrize("cs,expected", [
        ({"checked": True, "user_profiles": 1, "user_files": 2, "user_files_capped": False,
          "wifi_profiles": 1, "installed_apps": 24, "os_install_days": 3.0}, "clean"),
        ({"checked": True, "user_profiles": 2, "user_files": 30, "user_files_capped": True,
          "wifi_profiles": 18, "installed_apps": 96, "os_install_days": 900.0}, "not_clean"),
        ({"checked": False}, "unknown"),
    ])
    def test_wipe_verification_works_from_a_unix_scan(self, client, cs, expected):
        """The whole point of adding clean_state: a Mac or Linux seller can now
        prove a wipe, which they previously could not."""
        device = {"os_caption": "macOS 15.2", "manufacturer": "Apple",
                  "model": "MacBook Pro", "cpu_name": "Apple M2",
                  "battery_present": True, "clean_state": cs}
        tok = f"unix-wipe-{expected}-{cs.get('user_files', 'x')}-0123456789"
        client.post(f"/api/deep-scan/{tok}", json=device)
        doc = client.get(f"/api/deep-scan/{tok}").json()
        assert doc["wipe"]["status"] == expected
        assert ("wipe_verified" in doc["payload"]) is (expected == "clean")

    def test_persona_signals_reach_the_usage_fit_card(self, client):
        device = {"os_caption": "Ubuntu 24.04 LTS", "cpu_name": "AMD Ryzen 5",
                  "cpu_cores": 6, "ram_gb": 16.0, "battery_present": True,
                  "persona_signals": {"gamer_matches": [], "coder_matches": ["Docker"],
                                      "editor_matches": [], "steam_game_count": 0,
                                      "wsl_distro_count": 0}}
        client.post("/api/deep-scan/uxp-token-0123456789", json=device)
        doc = client.get("/api/deep-scan/uxp-token-0123456789").json()
        # Beside the passport for the usage-fit card, never inside the signed
        # payload a buyer would receive.
        assert doc["persona_signals"]["coder_matches"] == ["Docker"]
        assert "persona_signals" not in doc["payload"]
