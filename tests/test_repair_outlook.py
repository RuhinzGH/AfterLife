"""Repair outlook (S2-05): what a fix buys, re-scored by the real scorer, and
how often repairs of the same fault worked in the Open Repair Alliance records."""
from afterlife.assessment import blend_score
from afterlife.passport import battery_points
from afterlife.repair_evidence import evidence_block
from afterlife.uplift import capability_uplift, condition_uplift


def test_battery_replacement_is_scored_by_blend_score_itself():
    out = condition_uplift(75, None, 55, 4, False)
    assert out["actions"][0]["action"] == "Replace the battery"
    assert out["projected_score"] == blend_score(75, None, 95, 4, False)["combined_score"]


def test_on_a_deep_scan_the_battery_is_rescored_inside_the_trust_score():
    out = condition_uplift(62, None, 55, 6, False, trust_measured=True)
    gain = battery_points(95) - battery_points(55)
    assert out["actions"][0]["points"] == gain
    assert out["projected_score"] == 62 + gain


def test_a_battery_fault_and_a_worn_battery_are_one_fix_not_two():
    out = condition_uplift(70, 0.3, 55, 7, True, "Battery")
    assert [a["action"] for a in out["actions"]] == ["Replace the battery"]
    assert out["projected_score"] == blend_score(70, 0.3, 95, 7, False)["combined_score"]


def test_fixing_another_reported_fault_removes_its_penalty():
    out = condition_uplift(70, None, None, 3, True, "Screen")
    assert out["actions"][0]["action"] == "Fix the reported fault"
    assert out["projected_score"] == blend_score(70, None, None, 3, False)["combined_score"]


def test_nothing_fixable_means_no_card():
    assert condition_uplift(80, None, 90, 9, False) is None      # age alone has no fix


def test_hard_disk_offered_without_points():
    out = condition_uplift(80, None, None, 3, False, storage="500 GB HDD")
    assert out["ssd_swap_available"] and out["actions"] == []


def test_memory_upgrade_only_when_memory_is_the_only_gap():
    assert capability_uplift("coder", 8, 8, None) == {
        "current_tier": "Scripting & web dev", "next_tier": "Multi-service / Docker",
        "ram_needed_gb": 8, "target_ram_gb": 16}
    assert capability_uplift("coder", 4, 8, None) is None              # also needs cores
    assert capability_uplift("coder", 8, 8, None, ram_is_lower_bound=True) is None


def test_repair_records_match_the_fault_the_score_recognised():
    out = evidence_block(problem="Akku aufgebläht, écran cassé")
    assert [t["key"] for t in out["themes"]] == ["battery", "screen"]
    assert evidence_block(problem="asdf") is None
    assert evidence_block(problem="runs windows fine") is None    # an OS name alone is not a fault


def test_measured_problems_bring_their_records():
    out = evidence_block(battery_health=60, storage_health="FAILING", os_supported=False)
    assert {t["key"] for t in out["themes"]} == {"battery", "storage", "software"}
    assert out["source"].startswith("Open Repair Alliance") and out["n_records"] > 0
