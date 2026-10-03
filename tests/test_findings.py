"""The research page's numbers must come from the corpus, never from a literal.

This exists because the page once asserted two different totals for one dataset:
a hardcoded security block said 1,513 serious CVEs while the mitigation block a
few inches below it read 4,809 from the refreshed corpus. The same class of bug
had already happened twice before with a hardcoded day count. Every test here is
a guard against a number being typed into the code again.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERIOUS = {"HIGH", "CRITICAL"}


def _corpus(major: str) -> list[dict]:
    p = ROOT / "app_data" / f"win{major}_cve_classified.csv"
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def findings(client):
    r = client.get("/api/findings")
    assert r.status_code == 200
    return r.json()


def test_security_and_mitigation_agree(findings):
    """The two blocks describe the same corpus and must never diverge again."""
    assert findings["security"]["serious_cves"] == findings["mitigation"]["10"]["serious"]


def test_security_counts_match_the_corpus_on_disk(findings):
    rows = _corpus("10")
    serious = [r for r in rows if (r.get("severity") or "").upper() in SERIOUS]
    assert findings["security"]["total_cves"] == len(rows)
    assert findings["security"]["serious_cves"] == len(serious)


def test_local_share_is_computed_not_asserted(findings):
    rows = [r for r in _corpus("10") if (r.get("severity") or "").upper() in SERIOUS]
    local_like = sum(1 for r in rows
                     if (r.get("attack_vector") or "").upper() in ("LOCAL", "PHYSICAL"))
    assert findings["security"]["local_share"] == pytest.approx(local_like / len(rows), abs=0.001)


def test_headline_claim_still_holds(findings):
    """Zero serious CVEs reachable remotely, without credentials, with no fix.

    This is the finding the entire product is built on. If a corpus refresh ever
    breaks it, that must fail loudly here rather than being discovered by a
    reader of the homepage.
    """
    for major in ("10", "11"):
        assert findings["mitigation"][major]["remote_no_creds"] == 0, (
            f"Windows {major} no longer supports the core claim -- the copy on the "
            f"homepage and Our Research both assert this and would now be wrong."
        )


def test_addressable_share_is_a_majority(findings):
    for major in ("10", "11"):
        assert findings["mitigation"][major]["addressable_pct"] > 50


def test_supporting_datasets_are_present(findings):
    assert findings["repair_evidence"]["themes"], "the repair-outcome card would render empty"


class TestKnownExploited:
    """The KEV counts must be counted, and must mean what the page says.

    The page draws a distinction between "serious" (what CVSS predicts a flaw
    would do) and "known exploited" (what was observed happening). That
    distinction only holds if the second set really is a subset of the corpus and
    really is smaller -- otherwise the card is asserting a contrast that is not
    in the data.
    """

    def test_counts_match_the_corpus_on_disk(self, findings):
        rows = _corpus("10")
        exploited = [r for r in rows if (r.get("known_exploited") or "").lower() == "true"]
        ransom = [r for r in rows if (r.get("ransomware") or "").lower() == "true"]
        assert findings["security"]["known_exploited"] == len(exploited)
        assert findings["security"]["ransomware"] == len(ransom)

    def test_serious_subset_is_counted_among_serious_only(self, findings):
        rows = _corpus("10")
        both = [r for r in rows
                if (r.get("known_exploited") or "").lower() == "true"
                and (r.get("severity") or "").upper() in SERIOUS]
        assert findings["security"]["serious_known_exploited"] == len(both)

    def test_known_exploited_is_a_strict_subset_of_serious(self, findings):
        """If these were equal the card's whole point would evaporate."""
        s = findings["security"]
        assert 0 < s["serious_known_exploited"] < s["serious_cves"], (
            "the card claims exploitation is rarer than severity -- that must be true "
            "in the data, not just in the copy"
        )
        assert s["serious_known_exploited"] <= s["known_exploited"]

    def test_ransomware_is_a_subset_of_exploited(self, findings):
        s = findings["security"]
        assert s["ransomware"] <= s["known_exploited"], (
            "a flaw cannot be used in a ransomware campaign without being exploited"
        )

    def test_provenance_is_present_and_states_the_caveat(self, findings):
        """A floor reported as a total would be the most misleading thing here."""
        kev = findings["kev"]
        assert kev["catalog_version"], "the page shows which catalogue this came from"
        assert kev["kev_total"] > 0
        assert "floor" in (kev["caveat"] or "").lower()

    def test_every_row_carries_the_flags(self):
        """A half-enriched corpus would undercount silently rather than fail."""
        for major in ("10", "11"):
            rows = _corpus(major)
            missing = [r["cve_id"] for r in rows
                       if r.get("known_exploited") not in ("true", "false")]
            assert not missing, (
                f"Windows {major}: {len(missing)} rows never got tagged -- "
                f"re-run scripts/enrich_cve_kev.py"
            )


class TestArtifactsAreActuallyShipped:
    """Every artifact the API reads must be tracked in git.

    This exists because of a real failure. Two research artifacts were added to
    .gitignore with the note "not read by the app or the API" -- true when
    written, false the moment the research page started rendering them. The cards
    worked perfectly in development, where the untracked files sit on disk, and
    showed nothing in production, where the container never received them.

    A comment cannot notice when its own premise expires. A test can.
    """

    def _artifacts_the_api_reads(self) -> set[str]:
        import re
        src = (ROOT / "api" / "main.py").read_text(encoding="utf-8")
        return set(re.findall(r'_load_json\("([^"]+)"\)', src))

    def test_every_artifact_the_api_reads_exists_on_disk(self):
        missing = [n for n in self._artifacts_the_api_reads()
                   if not (ROOT / "app_data" / n).exists()]
        assert not missing, f"the API reads files that are not there: {missing}"

    def test_every_artifact_the_api_reads_is_tracked_in_git(self):
        """Untracked means absent from the container, which means a card that
        renders locally and is blank for every real visitor."""
        import subprocess
        untracked = []
        for name in sorted(self._artifacts_the_api_reads()):
            r = subprocess.run(
                ["git", "ls-files", "--error-unmatch", f"app_data/{name}"],
                cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                untracked.append(name)
        assert not untracked, (
            f"these are read by the API but not committed, so production will "
            f"never see them: {untracked}"
        )

    def test_the_cards_that_broke_have_their_data(self, findings):
        """Named explicitly, because this card once shipped blank."""
        assert findings.get("research", {}).get("cv_5fold"), (
            "the cross-validation card renders nothing without this"
        )
