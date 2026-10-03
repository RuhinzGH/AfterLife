"""The provenance manifest, and why it refuses to flatter itself.

A sources page is the easiest thing to hand-write and the worst, because it
drifts silently the moment anything is re-pulled. This project already shipped a
page quoting a confident CVE count from a corpus two years stale, so a
provenance page that itself needed remembering to update would be the same
failure in a new hat.

Everything here is therefore read off the artifacts at request time, and these
tests hold it to the two properties that make that trustworthy: freshness is
judged per-source, and weak evidence is never presented as strong.
"""
from __future__ import annotations

import datetime as dt

import pytest

from afterlife.sources import SOURCES, manifest


@pytest.fixture(scope="module")
def m():
    return manifest()


class TestItDescribesWhatIsActuallyThere:
    def test_every_declared_source_is_reported(self, m):
        assert m["total"] == len(SOURCES)
        assert {s["key"] for s in m["sources"]} == {s["key"] for s in SOURCES}

    def test_the_big_datasets_are_present_and_counted(self, m):
        by_key = {s["key"]: s for s in m["sources"]}
        for key in ("cve", "epss"):
            assert by_key[key]["present"] is True
            assert by_key[key]["rows"] and by_key[key]["rows"] > 100

    def test_row_counts_are_read_not_asserted(self, m):
        """The CVE count must match the corpus on disk, because the whole point
        is that nobody can type a number here."""
        import csv
        from pathlib import Path
        rows = sum(1 for _ in csv.reader(
            (Path(__file__).resolve().parent.parent / "app_data"
             / "win10_cve_classified.csv").open(encoding="utf-8"))) - 1
        cve = next(s for s in m["sources"] if s["key"] == "cve")
        assert cve["rows"] == rows

    def test_every_source_says_what_it_decides(self, m):
        """A dataset nobody can explain the use of should not be listed."""
        for s in m["sources"]:
            assert s["used_for"] and len(s["used_for"]) > 20

    def test_every_source_carries_a_licence_and_a_url(self, m):
        for s in m["sources"]:
            assert s["licence"]
            assert s["url"].startswith("https://")


class TestFreshnessIsJudgedPerSource:
    def test_cadences_differ_because_the_sources_do(self):
        """EPSS is refitted daily; endoflife.date moves quarterly. One global
        threshold would call a yearly academic release stale eleven months out
        of twelve and let a daily feed rot for a fortnight."""
        by_key = {s["key"]: s for s in SOURCES}
        assert by_key["epss"]["expected_days"] < by_key["support"]["expected_days"]
        assert by_key["survival"]["expected_days"] is None

    def test_a_source_with_no_cadence_is_never_called_stale(self, m):
        """A one-off academic release does not go off."""
        s = next(x for x in m["sources"] if x["key"] == "survival")
        assert s["status"] != "stale"

    def test_status_follows_age_against_that_sources_own_cadence(self):
        """Checked by moving the clock rather than by waiting for reality."""
        far = manifest(as_of=dt.date.today() + dt.timedelta(days=400))
        epss = next(s for s in far["sources"] if s["key"] == "epss")
        assert epss["status"] == "stale"

    def test_counts_add_up_to_the_total(self, m):
        assert sum(m["by_status"].values()) == m["total"]


class TestWeakEvidenceIsNotPresentedAsStrong:
    def test_the_basis_of_every_date_is_declared(self, m):
        for s in m["sources"]:
            assert s["fetched_basis"] in ("stamp", "mtime", "missing", "unreadable")

    def test_an_mtime_never_declares_a_source_current(self, m):
        """An mtime is whenever the file was last written, which a fresh
        checkout resets -- on a CI runner every one reads as today regardless of
        how old the data actually is. It can rule a source OUT as stale; it can
        never vouch for one."""
        for s in m["sources"]:
            if s["fetched_basis"] == "mtime":
                assert s["status"] != "current"

    def test_a_self_stamped_source_can_be_current(self, m):
        """The other half: a real stamp is allowed to vouch, or the distinction
        would be pointless."""
        stamped = [s for s in m["sources"] if s["fetched_basis"] == "stamp"]
        assert stamped
        assert any(s["status"] == "current" for s in stamped)

    def test_the_note_explains_the_method(self, m):
        assert "judged against" in m["note"] or "publication rhythm" in m["note"]


class TestApiSurface:
    def test_the_endpoint_returns_the_manifest(self, client):
        r = client.get("/api/sources").json()
        assert r["total"] == len(SOURCES)
        assert all("fetched_basis" in s for s in r["sources"])
