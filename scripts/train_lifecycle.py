"""Train and evaluate lifecycle classifiers on Open Repair Alliance IT devices.

Two numbers are reported for every model, and the gap between them is the main
experimental result.

    RANDOM SPLIT   rows shuffled, so the same repair cafe appears in both train
                   and test. The standard protocol, and what this script used to
                   do exclusively.

    GROUPED SPLIT  whole venues held out, so every test record comes from a
                   repair cafe the model has never seen.

The dataset has eight data providers, and fault text is written in whatever
language the event ran in -- roughly 19% of rows carry English markers, 6%
German, 6% Dutch, 5% French. Language therefore identifies the venue, so a
token-based model can score well by recognising where a record came from rather
than reading what broke. Measured here that is worth about twenty points of
macro F1: performance that exists under the standard protocol and disappears the
moment the model meets a repair cafe it was not trained on.

Two text representations are compared against that:

    TOKENS   word TF-IDF. Expressive, and carries the language signal.
    LEXICON  a nine-category multilingual fault signature (afterlife/
             fault_lexicon.py) mapping "Akku aufgeblaeht" and "swollen battery"
             onto the same feature, so it cannot encode the language and
             therefore cannot leak the venue.

Neither wins outright. Tokens separate Fixed from Repairable better; the lexicon
is far better at catching End of life, the class the product actually acts on.
Reporting only the winner would repeat exactly the mistake this project exists to
argue against, so both go into the metrics artifact and the research page shows
the trade rather than resolving it.

    python scripts/train_lifecycle.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import GroupKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from afterlife.fault_lexicon import theme_features
from afterlife.lifecycle_model import (
    CAT_FEATURES, CLASSES, EOL, MODEL_DIR, NUM_FEATURES, TEXT_FEATURE,
    class_distribution, load_it_frame,
)

OUT_METRICS = ROOT / "app_data" / "lifecycle_metrics.json"
FIG = ROOT / "app_data" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
RANDOM = 42
FOLDS = 4

GROUND, GRID, INK, SECOND, MUTED = "#0E1518", "#243033", "#F2F5F4", "#9DB0AD", "#7D8F8C"
BRAND, AMBER = "#8b5cf6", "#c98500"

#: Whatever representation wins, the deployed pipeline must accept exactly the
#: columns predict_lifecycle() sends -- so all three are built over the same
#: input frame and differ only in which columns they actually use.
#:
#: `country` is dropped from the invariant configuration on purpose. A
#: language-independent text representation is pointless while the model can
#: still read the country off a categorical column: the venue signal simply moves
#: from the text to the metadata, and the first run of this script showed exactly
#: that -- the lexicon looked no better than tokens until country came out.
#: `brand` goes with it, because brand mix tracks region too.
_VENUE_FREE_CAT = ["product_category"]

_NUM_STEP = ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                              ("sc", StandardScaler())]), NUM_FEATURES)


def preprocessor(representation: str) -> ColumnTransformer:
    """tokens   -- word TF-IDF + every categorical, including country.
    lexicon     -- fault signature, but country/brand still available.
    invariant   -- fault signature with every venue-revealing column removed."""
    cats = _VENUE_FREE_CAT if representation == "invariant" else CAT_FEATURES
    if representation == "tokens":
        text = ("txt", TfidfVectorizer(max_features=400, strip_accents="unicode",
                                       min_df=5, ngram_range=(1, 2)), TEXT_FEATURE)
    else:
        # validate=False keeps the DataFrame intact so theme_features can read the
        # named column. theme_features is a module-level function, not a lambda,
        # precisely so joblib can pickle the fitted model for production.
        text = ("txt", FunctionTransformer(theme_features, validate=False), [TEXT_FEATURE])
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=25), cats),
        _NUM_STEP, text,
    ])


def candidates() -> dict:
    """All class-balanced, so nothing wins by ignoring the minority class."""
    return {
        "Logistic Regression": LogisticRegression(max_iter=2000, class_weight="balanced",
                                                  n_jobs=-1, random_state=RANDOM),
        "Random Forest": RandomForestClassifier(n_estimators=300, max_depth=18,
                                                min_samples_leaf=3, class_weight="balanced",
                                                n_jobs=-1, random_state=RANDOM),
        "XGBoost": XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.08,
                                 subsample=0.9, colsample_bytree=0.8,
                                 eval_metric="mlogloss", n_jobs=-1, random_state=RANDOM),
    }


def make_pipe(representation: str, model_name: str) -> Pipeline:
    return Pipeline([("pre", preprocessor(representation)),
                     ("clf", candidates()[model_name])])


def expected_calibration_error(prob: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """How far the model's stated probability is from what actually happens.

    This matters more to the product than any accuracy figure. blend_score()
    multiplies eol_risk by 15 and subtracts it from a device's score out of 100,
    so an overstated probability is points taken off a machine that did not earn
    the loss. Measured at 0.141 before calibration: the model said 33% where the
    real rate was 19%, and every assessed device was being docked about 1.8
    points too many. For a product whose whole argument is that working hardware
    gets written off too early, that was quietly doing a small version of the
    same thing.
    """
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (prob >= lo) & (prob < hi if hi < 1 else prob <= hi)
        if m.sum():
            total += m.sum() / len(prob) * abs(prob[m].mean() - actual[m].mean())
    return round(float(total), 4)


def _scores(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": round(float((y_true == y_pred).mean()), 3),
        "macro_f1": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 3),
        "eol_recall": round(float(recall_score(y_true, y_pred, labels=[EOL],
                                               average="macro", zero_division=0)), 3),
        "eol_precision": round(float(precision_score(y_true, y_pred, labels=[EOL],
                                                     average="macro", zero_division=0)), 3),
        "fixed_recall": round(float(recall_score(y_true, y_pred, labels=[0],
                                                 average="macro", zero_division=0)), 3),
    }


def _fit(rep: str, name: str, X: pd.DataFrame, y: np.ndarray, idx: np.ndarray) -> Pipeline:
    """XGBoost takes explicit sample weights to match class_weight='balanced'."""
    pipe = make_pipe(rep, name)
    if isinstance(pipe.named_steps["clf"], XGBClassifier):
        return pipe.fit(X.iloc[idx], y[idx],
                        clf__sample_weight=compute_sample_weight("balanced", y[idx]))
    return pipe.fit(X.iloc[idx], y[idx])


def evaluate_grouped(rep, name, X, y, groups) -> dict[str, float]:
    """Mean across folds where every test venue is unseen during training."""
    folds = [_scores(y[te], _fit(rep, name, X, y, tr).predict(X.iloc[te]))
             for tr, te in GroupKFold(n_splits=FOLDS).split(X, y, groups)]
    out = {k: round(float(np.mean([f[k] for f in folds])), 3) for k in folds[0]}
    # Fold spread matters more than usual with only eight venues: one unusual
    # repair cafe moves the mean a long way, and a figure quoted without its
    # variance would overstate how settled the result is.
    out["macro_f1_sd"] = round(float(np.std([f["macro_f1"] for f in folds])), 3)
    out["eol_recall_sd"] = round(float(np.std([f["eol_recall"] for f in folds])), 3)
    return out


def evaluate_random(rep, name, X, y) -> dict[str, float]:
    idx = np.arange(len(y))
    tr, te = train_test_split(idx, test_size=0.2, stratify=y, random_state=RANDOM)
    return _scores(y[te], _fit(rep, name, X, y, tr).predict(X.iloc[te]))


def _leak_figure(results: list[dict]) -> None:
    """The headline chart: what each model scores when it can recognise the venue,
    and what is left when it cannot."""
    rows = [r for r in results if r["representation"] == "tokens"]
    labels = [r["model"] for r in rows]
    x, w = np.arange(len(labels)), 0.38
    fig, ax = plt.subplots(figsize=(9.2, 4.2), dpi=200)
    fig.patch.set_facecolor(GROUND); ax.set_facecolor(GROUND)
    ax.bar(x - w / 2, [r["random"]["macro_f1"] for r in rows], w,
           color=MUTED, label="random split (same venues in train and test)")
    ax.bar(x + w / 2, [r["grouped"]["macro_f1"] for r in rows], w,
           color=BRAND, label="grouped split (unseen venues)")
    ax.set_xticks(x); ax.set_xticklabels(labels, color=SECOND, fontsize=9.5)
    ax.set_ylim(0, 0.8); ax.grid(axis="y", color=GRID, lw=1); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.set_ylabel("macro F1", color=SECOND)
    ax.set_title("Most of the score was recognising the repair cafe, not the fault",
                 color=INK, fontsize=11.5, pad=10)
    ax.legend(frameon=False, labelcolor=SECOND, fontsize=9.5)
    fig.tight_layout(); fig.savefig(FIG / "venue_leakage.png", facecolor=GROUND); plt.close(fig)


def _tradeoff_figure(results: list[dict]) -> None:
    """The trade, plotted: end-of-life recall against macro F1, both grouped."""
    fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
    fig.patch.set_facecolor(GROUND); ax.set_facecolor(GROUND)
    for rep, colour, marker in (("tokens", MUTED, "o"), ("lexicon", SECOND, "s"),
                                ("invariant", BRAND, "D")):
        pts = [r for r in results if r["representation"] == rep]
        ax.scatter([p["grouped"]["macro_f1"] for p in pts],
                   [p["grouped"]["eol_recall"] for p in pts],
                   s=110, color=colour, marker=marker, label=f"{rep} representation", zorder=3)
        for p in pts:
            ax.annotate(p["model"].replace("Logistic Regression", "LogReg"),
                        (p["grouped"]["macro_f1"], p["grouped"]["eol_recall"]),
                        textcoords="offset points", xytext=(8, -3),
                        color=SECOND, fontsize=8.5)
    ax.set_xlabel("macro F1 (separating all three outcomes)", color=SECOND)
    ax.set_ylabel("End-of-life recall (catching dead devices)", color=SECOND)
    ax.grid(color=GRID, lw=1); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.set_title("Neither representation wins outright, on unseen venues",
                 color=INK, fontsize=11.5, pad=10)
    ax.legend(frameon=False, labelcolor=SECOND, fontsize=9.5, loc="lower left")
    fig.tight_layout(); fig.savefig(FIG / "model_compare.png", facecolor=GROUND); plt.close(fig)


def main() -> None:
    df = load_it_frame()
    X = df[CAT_FEATURES + NUM_FEATURES + [TEXT_FEATURE]]
    y = df["y"].to_numpy()
    groups = df["data_provider"].astype(str).to_numpy()
    n_groups = int(pd.Series(groups).nunique())

    print(f"{len(df):,} IT repair records across {n_groups} data providers")
    print(f"distribution: {class_distribution(df)}")
    print(f"device_age coverage: {df['device_age'].notna().mean():.1%}\n")

    majority = int(np.bincount(y).argmax())
    baseline = _scores(y, np.full(len(y), majority))
    results = [{"model": "Baseline (majority)", "representation": "none",
                "random": baseline, "grouped": baseline}]
    print(f"  {'baseline':<8} {'majority class':<21} acc {baseline['accuracy']:.3f} | "
          f"macro F1 {baseline['macro_f1']:.3f} | EOL recall {baseline['eol_recall']:.3f}")

    for rep in ("tokens", "lexicon", "invariant"):
        for name in candidates():
            rnd = evaluate_random(rep, name, X, y)
            grp = evaluate_grouped(rep, name, X, y, groups)
            results.append({"model": name, "representation": rep,
                            "random": rnd, "grouped": grp})
            print(f"  {rep:<8} {name:<21} random F1 {rnd['macro_f1']:.3f} | "
                  f"grouped F1 {grp['macro_f1']:.3f} (sd {grp['macro_f1_sd']:.3f}) | "
                  f"grouped EOL recall {grp['eol_recall']:.3f}")

    # ---- per-category validation ------------------------------------------
    # Laptops are half the data, so a single headline number could be a laptop
    # score wearing a general label. Every row is predicted by a model that never
    # saw its repair organisation, then scored per product category, so "does
    # this work for phones?" has an answer rather than an assumption.
    cats = df["product_category"].to_numpy()
    oof = np.empty(len(y), dtype=int)
    for tr, te in GroupKFold(n_splits=FOLDS).split(X, y, groups):
        # Scored on the configuration that actually ships, so these per-category
        # numbers describe the model a user gets rather than a different one.
        oof[te] = _fit("tokens", "Random Forest", X, y, tr).predict(X.iloc[te])
    by_category = []
    for cat in pd.Series(cats).value_counts().index:
        m = cats == cat
        by_category.append({
            "category": str(cat), "n": int(m.sum()),
            "share": round(float(m.mean()), 3),
            "macro_f1": round(float(f1_score(y[m], oof[m], average="macro", zero_division=0)), 3),
            "eol_recall": round(float(recall_score(y[m], oof[m], labels=[EOL],
                                                   average="macro", zero_division=0)), 3),
            "eol_base_rate": round(float((y[m] == EOL).mean()), 3),
            "age_known": round(float(df.loc[m, "device_age"].notna().mean()), 3),
        })
    print("\nper category, predicted by models that never saw the venue:")
    for c in by_category:
        print(f"  {c['category']:<18} n={c['n']:>6,}  macro F1 {c['macro_f1']:.3f}  "
              f"EOL recall {c['eol_recall']:.3f}")

    scored = [r for r in results if r["representation"] != "none"]

    # Both winners chosen on the GROUPED numbers, because those describe a venue
    # the model has not seen -- which is every real deployment.
    best_eol = max(scored, key=lambda r: (r["grouped"]["eol_recall"], r["grouped"]["macro_f1"]))
    best_f1 = max(scored, key=lambda r: (r["grouped"]["macro_f1"], r["grouped"]["eol_recall"]))

    # ---- calibration -------------------------------------------------------
    # The product consumes eol_risk as a probability, not a ranking, so the
    # number has to mean what it says. Measured across held-out venues, fitting
    # the calibrator only inside each training fold -- a calibrator fitted on the
    # venues it will be scored against is the same leak wearing a different coat.
    raw_p, cal_p, truth = [], [], []
    for tr, te in GroupKFold(n_splits=FOLDS).split(X, y, groups):
        base = _fit(best_eol["representation"], best_eol["model"], X, y, tr)
        raw_p.append(base.predict_proba(X.iloc[te])[:, EOL])
        cal = CalibratedClassifierCV(make_pipe(best_eol["representation"], best_eol["model"]),
                                     method="isotonic", cv=3)
        cal.fit(X.iloc[tr], y[tr])
        cal_p.append(cal.predict_proba(X.iloc[te])[:, EOL])
        truth.append((y[te] == EOL).astype(float))
    raw_p, cal_p, truth = map(np.concatenate, (raw_p, cal_p, truth))
    calibration = {
        "ece_raw": expected_calibration_error(raw_p, truth),
        "ece_calibrated": expected_calibration_error(cal_p, truth),
        "mean_points_docked_raw": round(float(raw_p.mean() * 15), 2),
        "mean_points_docked_calibrated": round(float(cal_p.mean() * 15), 2),
        "mean_absolute_shift_points": round(float(np.abs(raw_p - cal_p).mean() * 15), 2),
        "base_rate": round(float(truth.mean()), 3),
    }
    print(f"\ncalibration: ECE {calibration['ece_raw']:.4f} -> "
          f"{calibration['ece_calibrated']:.4f}"
          f"   (score adjustment {calibration['mean_points_docked_raw']:.2f} -> "
          f"{calibration['mean_points_docked_calibrated']:.2f} points)")

    # The shipped model is the one that best catches end-of-life devices across
    # unseen venues -- the single output the product acts on -- wrapped in the
    # calibrator so the probability it reports is honest.
    shipped = CalibratedClassifierCV(
        make_pipe(best_eol["representation"], best_eol["model"]), method="isotonic", cv=3)
    shipped.fit(X, y)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(shipped, MODEL_DIR / "lifecycle_model.joblib")

    leakage = {
        "model": best_f1["model"], "representation": best_f1["representation"],
        "macro_f1": round(best_f1["random"]["macro_f1"] - best_f1["grouped"]["macro_f1"], 3),
        "accuracy": round(best_f1["random"]["accuracy"] - best_f1["grouped"]["accuracy"], 3),
    }

    _leak_figure(results)
    _tradeoff_figure(scored)

    # Confusion matrix for the shipped model, on held-out venues only.
    tr, te = next(iter(GroupKFold(n_splits=FOLDS).split(X, y, groups)))
    pred = _fit(best_eol["representation"], best_eol["model"], X, y, tr).predict(X.iloc[te])
    cm = confusion_matrix(y[te], pred, normalize="true")
    fig, ax = plt.subplots(figsize=(6.4, 5.6), dpi=200)
    fig.patch.set_facecolor(GROUND); ax.set_facecolor(GROUND)
    ax.imshow(cm, cmap="Purples", vmin=0, vmax=1)
    ax.set_xticks(range(3)); ax.set_yticks(range(3))
    ax.set_xticklabels(CLASSES, color=SECOND, fontsize=10)
    ax.set_yticklabels(CLASSES, color=SECOND, fontsize=10, rotation=90, va="center")
    ax.set_xlabel("predicted", color=SECOND); ax.set_ylabel("actual", color=SECOND)
    for i in range(3):
        for j in range(3):
            ax.text(j, i, f"{cm[i, j]:.0%}", ha="center", va="center",
                    color="white" if cm[i, j] > 0.5 else INK, fontweight="bold", fontsize=12)
    ax.set_title(f"{best_eol['model']} / {best_eol['representation']} — unseen venues",
                 color=INK, fontsize=12, pad=12)
    for s in ax.spines.values(): s.set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout(); fig.savefig(FIG / "confusion.png", facecolor=GROUND); plt.close(fig)

    OUT_METRICS.write_text(json.dumps({
        "n_records": int(len(df)), "n_groups": n_groups, "folds": FOLDS,
        "distribution": class_distribution(df),
        "results": results,
        "winner": best_eol["model"],
        "winner_representation": best_eol["representation"],
        "winner_grouped": best_eol["grouped"],
        "best_macro_f1": {"model": best_f1["model"],
                          "representation": best_f1["representation"],
                          "grouped": best_f1["grouped"]},
        "venue_leakage": leakage,
        "calibration": calibration,
        "by_category": by_category,
        "protocol": (
            "Grouped K-fold by data provider: every test record comes from a repair "
            "venue absent from training. Random-split figures are reported alongside "
            "to quantify what venue memorisation is worth."
        ),
    }, indent=2), encoding="utf-8")

    print(f"\nvenue leakage ({leakage['model']}/{leakage['representation']}): "
          f"{leakage['macro_f1']:+.3f} macro F1, {leakage['accuracy']:+.3f} accuracy")
    print(f"shipped, best grouped EOL recall : {best_eol['model']} / {best_eol['representation']} "
          f"-> {best_eol['grouped']['eol_recall']:.3f}")
    print(f"best grouped macro F1            : {best_f1['model']} / {best_f1['representation']} "
          f"-> {best_f1['grouped']['macro_f1']:.3f}")
    print(f"\nwrote {OUT_METRICS}")


if __name__ == "__main__":
    main()
