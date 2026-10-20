"""Every available mitigation per flaw, beside the one primary category (S2-17)."""
from fastapi.testclient import TestClient

from afterlife.hardening import build_report
from afterlife.mitigation import MitigationClass, all_mitigations, classify, flags_label, isolation_applies
from afterlife.nvd import Vuln
from api.main import app


def vuln(desc="", av="LOCAL", pr="LOW", parts=("o",)):
    return Vuln(cve_id="CVE-T", published=None, description=desc, base_score=8.8, severity="HIGH",
                attack_vector=av, privileges_required=pr, user_interaction="NONE", scope="UNCHANGED",
                cpe_parts=set(parts))


def test_a_flaw_can_have_more_than_one_way_out():
    v = vuln("Print Spooler flaw reachable over Remote Desktop", av="NETWORK", pr="NONE")
    found = [(m.klass, m.component) for m in all_mitigations(v)]
    assert found == [(MitigationClass.SERVICE_DISABLE, "spooler"), (MitigationClass.SERVICE_DISABLE, "rdp"),
                     (MitigationClass.NETWORK_ISOLATE, "network")]
    # the primary category is still the first, best option
    assert classify(v).component == "spooler"


def test_a_local_flaw_with_no_lever_has_none():
    assert all_mitigations(vuln("kernel memory corruption", av="LOCAL", pr="LOW")) == []


def test_stored_form():
    v = vuln("webdav issue", av="NETWORK", pr="NONE")
    assert flags_label(all_mitigations(v)) == "service_disable:webdav;network_isolate:network"


def test_isolation_rule_matches_the_classifier():
    assert isolation_applies("NETWORK", "NONE") and isolation_applies("ADJACENT_NETWORK", "NONE")
    assert not isolation_applies("NETWORK", "LOW") and not isolation_applies("LOCAL", "NONE")


def test_report_counts_the_overlap_without_changing_the_headline():
    r = build_report(os_caption="Windows 10")
    assert r.fix_also_isolatable <= r.fixable_cves
    # every flaw whose primary option is isolation is isolatable, plus the overlap
    assert r.isolation_applies_cves == r.isolation_cves + r.fix_also_isolatable
    assert r.flags_basis in ("attack vector", "full rule match")
    # addressable still means fixed, isolated or local-only, each flaw counted once
    assert round(r.addressable_share, 3) == round(
        (r.fixable_cves + r.isolation_cves + r.local_access_cves) / r.serious_cves, 3)


def test_research_page_gets_the_overlap():
    mit = TestClient(app).get("/api/findings").json()["mitigation"]["10"]
    assert mit["fixable_pct"] < mit["addressable_pct"]
    assert mit["fix_also_isolatable"] >= 0 and mit["isolation_applies"] >= mit["isolation"]
