"""Research paper experiment: does model-selection metric change under asymmetric costs?

Runs the full methodology settled in the proposal doc:
  1. Train 4 candidate models (Logistic Regression, Random Forest, XGBoost, MLP) on
     Open Repair Alliance IT-device repair outcomes.
  2. Report standard metrics (accuracy, macro/weighted F1, full per-class P/R/F1).
  3. Build an explicit, declared cost matrix for asymmetric misclassification costs
     (a repairable/fixed device wrongly called End-of-life -> unnecessary e-waste,
     vs an End-of-life device wrongly called repairable -> wasted technician time).
  4. Sweep the cost ratio 1:1 -> 1:10 and show whether the "best" model changes
     depending on whether you select by accuracy or by the cost-weighted score.
  5. 5-fold stratified cross-validation, to check the finding isn't just one split.
  6. SHAP on the cost-selected model, to see which features actually drive an
     End-of-life call.

Every number below is real, computed from the actual dataset -- nothing invented.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from afterlife.lifecycle_model import (
    CAT_FEATURES, CLASSES, EOL, NUM_FEATURES, TEXT_FEATURE, load_it_frame,
)

RANDOM = 42
OUT = ROOT / "app_data" / "research_results.json"

FIXED, REPAIRABLE = 0, 1  # CLASS_IDX order: Fixed=0, Repairable=1, End of life=2


def make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=25), CAT_FEATURES),
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), NUM_FEATURES),
        ("txt", TfidfVectorizer(max_features=400, strip_accents="unicode", min_df=5, ngram_range=(1, 2)), TEXT_FEATURE),
    ])


def build_models() -> dict:
    return {
        "Logistic Regression": LogisticRegression(max_iter=2000, class_weight="balanced", n_jobs=-1),
        "Random Forest": RandomForestClassifier(
            n_estimators=300, max_depth=18, min_samples_leaf=3,
            class_weight="balanced", n_jobs=-1, random_state=RANDOM),
        "XGBoost": XGBClassifier(
            n_estimators=400, max_depth=6, learning_rate=0.08, subsample=0.9,
            colsample_bytree=0.8, eval_metric="mlogloss", n_jobs=-1, random_state=RANDOM),
        "MLP": MLPClassifier(
            hidden_layer_sizes=(64, 32), max_iter=300, early_stopping=True,
            n_iter_no_change=10, random_state=RANDOM),
    }


def balanced_oversample(X: pd.DataFrame, y: np.ndarray, seed: int = RANDOM):
    """Resample the training set so every class matches the majority count.

    LogReg/RF get class_weight="balanced" and XGBoost gets sample_weight -- both
    are ways of telling the model "treat the minority classes as if they were
    this much bigger." MLPClassifier.fit() accepts neither, so without this it
    trains on the raw imbalanced data and just learns to mostly predict the
    majority class. Oversampling gives it the same effective signal the other
    three models get through their own weighting mechanism, so all four are
    compared on equal footing rather than three balanced models vs one that isn't.
    """
    rng = np.random.RandomState(seed)
    df = X.copy()
    df["_y"] = y
    counts = df["_y"].value_counts()
    target = counts.max()
    parts = []
    for cls, grp in df.groupby("_y"):
        idx = rng.choice(grp.index, size=target, replace=len(grp) < target)
        parts.append(df.loc[idx])
    bal = pd.concat(parts).sample(frac=1, random_state=seed)
    return bal.drop(columns="_y"), bal["_y"].values


def cost_matrix(ratio: float) -> np.ndarray:
    """3x3 cost matrix, rows=true, cols=predicted, CLASSES order [Fixed, Repairable, EoL].

    The expensive error: a device that should be kept/fixed (true Fixed or Repairable)
    gets wrongly called End-of-life -> discarded, forcing replacement -> e-waste +
    embodied-carbon cost. Cost = `ratio`.
    The cheap error: a device that's actually End-of-life gets wrongly called
    Fixed/Repairable -> wastes some technician time/parts, nothing discarded. Cost = 1.
    Confusions within {Fixed, Repairable} are a minor, non-asymmetric labeling
    error (not the effect under study) -> small fixed cost.
    Correct predictions cost 0.
    """
    m = np.zeros((3, 3))
    m[FIXED, EOL] = ratio
    m[REPAIRABLE, EOL] = ratio
    m[EOL, FIXED] = 1.0
    m[EOL, REPAIRABLE] = 1.0
    m[FIXED, REPAIRABLE] = 0.2
    m[REPAIRABLE, FIXED] = 0.2
    return m


def cost_weighted_score(y_true, y_pred, ratio: float) -> float:
    """Average cost per prediction under the given cost matrix (lower = better)."""
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2])
    costs = cost_matrix(ratio)
    return float((cm * costs).sum() / cm.sum())


def per_class_metrics(y_true, y_pred) -> dict:
    rep = classification_report(y_true, y_pred, target_names=CLASSES, output_dict=True, zero_division=0)
    return {c: {"precision": round(rep[c]["precision"], 3), "recall": round(rep[c]["recall"], 3),
               "f1": round(rep[c]["f1-score"], 3)} for c in CLASSES}


def main() -> None:
    t0 = time.time()
    df = load_it_frame()
    print(f"IT devices with usable labels: {len(df):,}")

    X = df[CAT_FEATURES + NUM_FEATURES + [TEXT_FEATURE]]
    y = df["y"].values
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=RANDOM)
    print(f"train {len(Xtr):,} / test {len(Xte):,}\n")
    sw = compute_sample_weight("balanced", ytr)

    # ---------------------------------------------------------------- 1+2. train & evaluate
    fitted, results = {}, []
    for name, model in build_models().items():
        pipe = Pipeline([("prep", make_preprocessor()), ("clf", model)])
        t1 = time.time()
        if isinstance(model, XGBClassifier):
            pipe.fit(Xtr, ytr, clf__sample_weight=sw)
        elif isinstance(model, MLPClassifier):
            Xtr_bal, ytr_bal = balanced_oversample(Xtr, ytr)
            pipe.fit(Xtr_bal, ytr_bal)
        else:
            pipe.fit(Xtr, ytr)
        pred = pipe.predict(Xte)
        acc = float((pred == yte).mean())
        pcm = per_class_metrics(yte, pred)
        row = {
            "model": name, "fit_seconds": round(time.time() - t1, 1),
            "accuracy": round(acc, 3),
            "macro_f1": round(np.mean([pcm[c]["f1"] for c in CLASSES]), 3),
            "per_class": pcm,
            "cost_score_by_ratio": {str(r): round(cost_weighted_score(yte, pred, r), 3) for r in range(1, 11)},
        }
        results.append(row)
        fitted[name] = pipe
        print(f"  {name:<20} acc={row['accuracy']:.3f}  macroF1={row['macro_f1']:.3f}  "
              f"EoL recall={pcm['End of life']['recall']:.3f}  fit={row['fit_seconds']}s")

    # ---------------------------------------------------------------- 3+4. cost-ratio sweep
    print("\n--- cost-ratio sensitivity sweep (which model minimizes cost at each ratio?) ---")
    accuracy_best = max(results, key=lambda r: r["accuracy"])["model"]
    sweep = {}
    for r in range(1, 11):
        best = min(results, key=lambda row: row["cost_score_by_ratio"][str(r)])["model"]
        sweep[str(r)] = best
        flag = "  <-- differs from accuracy-best" if best != accuracy_best else ""
        print(f"  ratio 1:{r:<2}  cost-best = {best}{flag}")
    disagreement_ratios = [r for r, m in sweep.items() if m != accuracy_best]

    # the model to carry forward: cost-best at a representative mid-range ratio (1:5)
    cost_selected = sweep["5"]

    # ---------------------------------------------------------------- 5. 5-fold CV
    print(f"\n--- 5-fold stratified CV (robustness check) ---")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM)
    cv_summary = {}
    for name, model in build_models().items():
        fold_f1, fold_eol_recall, fold_cost5 = [], [], []
        for fold_i, (tr_idx, va_idx) in enumerate(skf.split(X, y)):
            Xf_tr, Xf_va = X.iloc[tr_idx], X.iloc[va_idx]
            yf_tr, yf_va = y[tr_idx], y[va_idx]
            pipe = Pipeline([("prep", make_preprocessor()), ("clf", model)])
            if isinstance(model, XGBClassifier):
                pipe.fit(Xf_tr, yf_tr, clf__sample_weight=compute_sample_weight("balanced", yf_tr))
            elif isinstance(model, MLPClassifier):
                Xf_tr_bal, yf_tr_bal = balanced_oversample(Xf_tr, yf_tr, seed=RANDOM + fold_i)
                pipe.fit(Xf_tr_bal, yf_tr_bal)
            else:
                pipe.fit(Xf_tr, yf_tr)
            pf = pipe.predict(Xf_va)
            pcmf = per_class_metrics(yf_va, pf)
            fold_f1.append(np.mean([pcmf[c]["f1"] for c in CLASSES]))
            fold_eol_recall.append(pcmf["End of life"]["recall"])
            fold_cost5.append(cost_weighted_score(yf_va, pf, 5))
        cv_summary[name] = {
            "macro_f1_mean": round(float(np.mean(fold_f1)), 3), "macro_f1_std": round(float(np.std(fold_f1)), 3),
            "eol_recall_mean": round(float(np.mean(fold_eol_recall)), 3), "eol_recall_std": round(float(np.std(fold_eol_recall)), 3),
            "cost5_mean": round(float(np.mean(fold_cost5)), 3), "cost5_std": round(float(np.std(fold_cost5)), 3),
        }
        print(f"  {name:<20} macroF1={cv_summary[name]['macro_f1_mean']:.3f}±{cv_summary[name]['macro_f1_std']:.3f}  "
              f"cost@1:5={cv_summary[name]['cost5_mean']:.3f}±{cv_summary[name]['cost5_std']:.3f}")
    cv_cost_best = min(cv_summary, key=lambda n: cv_summary[n]["cost5_mean"])

    # ---------------------------------------------------------------- 6. SHAP on cost-selected model
    print(f"\n--- SHAP on cost-selected model: {cost_selected} ---")
    shap_top = []
    try:
        import shap
        pipe = fitted[cost_selected]
        prep, clf = pipe.named_steps["prep"], pipe.named_steps["clf"]
        Xte_t = prep.transform(Xte)
        if hasattr(Xte_t, "toarray"):
            Xte_t = Xte_t.toarray()
        sample_idx = np.random.RandomState(RANDOM).choice(len(Xte_t), size=min(300, len(Xte_t)), replace=False)
        sample = Xte_t[sample_idx]
        names = prep.get_feature_names_out()
        if hasattr(clf, "feature_importances_"):  # tree models -> fast exact explainer
            explainer = shap.TreeExplainer(clf)
            sv = explainer.shap_values(sample)
            # sv shape: (n_samples, n_features, n_classes) in recent SHAP, or list per class
            if isinstance(sv, list):
                eol_sv = sv[EOL]
            else:
                eol_sv = sv[:, :, EOL] if sv.ndim == 3 else sv
            mean_abs = np.abs(eol_sv).mean(axis=0)
            order = np.argsort(mean_abs)[::-1][:15]
            shap_top = [{"feature": names[i], "mean_abs_shap": round(float(mean_abs[i]), 4)} for i in order]
            for f in shap_top[:10]:
                print(f"  {f['feature']:<28} {f['mean_abs_shap']:.4f}")
        else:
            print("  (cost-selected model isn't tree-based -- skipping SHAP, KernelExplainer too slow for this run)")
    except Exception as exc:
        print(f"  SHAP failed: {type(exc).__name__}: {exc}")

    # ---------------------------------------------------------------- save
    out = {
        "n_train": len(Xtr), "n_test": len(Xte),
        "results": results,
        "accuracy_best_model": accuracy_best,
        "cost_ratio_sweep": sweep,
        "disagreement_ratios": disagreement_ratios,
        "cost_selected_model_at_1to5": cost_selected,
        "cv_5fold": cv_summary,
        "cv_cost_best_model": cv_cost_best,
        "shap_top_features_eol": shap_top,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"\nsaved -> {OUT}  (total runtime {out['runtime_seconds']}s)")


if __name__ == "__main__":
    main()
