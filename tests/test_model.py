"""The model's honesty guarantees.

These exist because the project's central claim is that its numbers are earned
rather than flattering. A future refactor that quietly reintroduces the leak, or
starts reporting only the random-split figure, should fail here rather than on
the research page.
"""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture(scope="module")
def model_block(client):
    return client.get("/api/findings").json()["model"]


def test_every_model_reports_both_protocols(model_block):
    """Reporting only one number is how the original mistake happened."""
    for row in model_block["results"]:
        assert row["random"] and row["grouped"], f"{row['model']} is missing a protocol"
        assert "macro_f1" in row["grouped"] and "eol_recall" in row["grouped"]


def test_grouped_scores_carry_their_spread(model_block):
    """Eight venues is a small number of groups: one unusual repair cafe moves a
    fold a long way, so a mean without its variance overstates the result."""
    for row in model_block["results"]:
        if row["representation"] == "none":
            continue
        assert "macro_f1_sd" in row["grouped"], f"{row['model']} quotes a mean with no spread"


def test_venue_leakage_is_reported_not_hidden(model_block):
    leak = model_block["venue_leakage"]
    assert leak["macro_f1"] > 0, (
        "the random split no longer scores higher than the grouped one -- either the "
        "leak is genuinely gone, which is a finding, or the protocols got swapped"
    )


def test_selection_uses_the_honest_protocol(model_block):
    """The shipped model must win on held-out venues, not on the leaky split."""
    scored = [r for r in model_block["results"] if r["representation"] != "none"]
    best = max(scored, key=lambda r: (r["grouped"]["eol_recall"], r["grouped"]["macro_f1"]))
    assert model_block["winner"] == best["model"]
    assert model_block["winner_representation"] == best["representation"]


def test_beats_the_baseline_on_the_metric_it_selects_for(model_block):
    """A majority-class baseline scores well on accuracy and catches zero
    end-of-life devices. Every real model must beat that where it counts."""
    assert model_block["winner_grouped"]["eol_recall"] > 0.3


def test_venue_free_configuration_is_the_most_stable(model_block):
    """The claim on the research page. If a refresh makes it untrue, the copy is
    wrong and this should say so."""
    def spread(rep):
        rows = [r for r in model_block["results"] if r["representation"] == rep]
        return sum(r["grouped"]["macro_f1_sd"] for r in rows) / len(rows)
    assert spread("invariant") < spread("tokens")


class TestFaultLexicon:
    def test_same_fault_in_four_languages_maps_to_one_feature(self):
        """The whole point: the representation cannot tell which language, and so
        cannot tell which venue."""
        from afterlife.fault_lexicon import feature_names, theme_features
        rows = pd.DataFrame({"problem": [
            "swollen battery", "Akku aufgebläht", "batterij opgezwollen", "batterie",
        ]})
        m = theme_features(rows)
        col = feature_names().index("fault:battery")
        assert all(m[i][col] == 1.0 for i in range(4))

    def test_empty_text_fires_nothing(self):
        from afterlife.fault_lexicon import theme_features
        assert theme_features(pd.DataFrame({"problem": ["", None]})).sum() == 0

    def test_shape_is_stable(self):
        from afterlife.fault_lexicon import THEME_KEYS, theme_features
        m = theme_features(pd.DataFrame({"problem": ["screen cracked"] * 3}))
        assert m.shape == (3, len(THEME_KEYS))

    def test_the_model_and_the_research_card_share_one_lexicon(self):
        """Two copies would let the card and the classifier describe different
        faults from the same dataset."""
        import scripts.build_repair_evidence as bre
        from afterlife.fault_lexicon import THEMES
        assert bre.THEMES is THEMES


class TestPredictionPath:
    def test_saved_model_loads_and_predicts(self):
        """Retraining changed the feature pipeline; the deployed joblib must still
        accept exactly the columns predict_lifecycle() sends."""
        from afterlife.predict import predict_lifecycle
        r = predict_lifecycle(product_category="Laptop", brand="Dell",
                              device_age=7, problem="battery swollen, won't charge")
        assert r["prediction"] in ("Fixed", "Repairable", "End of life")
        assert 0.0 <= r["eol_risk"] <= 1.0

    def test_survives_a_bare_request(self, client):
        assert client.post("/api/predict", json={"product_category": "Laptop"}).status_code == 200


class TestCalibration:
    """The product consumes eol_risk as a probability, not a ranking.

    blend_score() multiplies it by 15 and subtracts that from a device's score.
    Measured before this was fixed: the model said 33% where the true rate was
    19%, so every assessed device lost about 1.8 points it had not earned. For a
    product arguing that working hardware gets written off too early, that was a
    small version of the same mistake.
    """

    def test_calibration_is_measured_and_reported(self, model_block):
        cal = model_block.get("calibration")
        assert cal, "calibration was measured during training and must be published"
        assert {"ece_raw", "ece_calibrated"} <= set(cal)

    def test_calibration_actually_improves_honesty(self, model_block):
        cal = model_block["calibration"]
        assert cal["ece_calibrated"] < cal["ece_raw"], (
            "isotonic calibration made the probabilities worse -- ship the raw model instead"
        )

    def test_calibrated_probabilities_are_close_to_reality(self, model_block):
        # 0.05 is a loose bar deliberately: with 8 venues the estimate is noisy,
        # and a tight threshold here would fail on data drift rather than on a bug.
        assert model_block["calibration"]["ece_calibrated"] < 0.05

    def test_the_shipped_model_reports_calibrated_probabilities(self):
        """A calibrated pipeline that got replaced by a bare one would still
        predict fine and silently go back to overcharging every device."""
        from afterlife.predict import _model
        from sklearn.calibration import CalibratedClassifierCV
        assert isinstance(_model(), CalibratedClassifierCV)

    def test_eol_risk_stays_a_probability(self):
        from afterlife.predict import predict_lifecycle
        for problem in ("", "battery swollen", "motherboard is dead", "won't turn on"):
            r = predict_lifecycle(product_category="Laptop", problem=problem)
            assert 0.0 <= r["eol_risk"] <= 1.0
            assert abs(sum(p["probability"] for p in r["probabilities"]) - 1.0) < 0.02
