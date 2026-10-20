r"""S3-05: can the shipped model be smaller without getting worse?

The shipped end-of-life model is a Random Forest (300 trees, depth 18) on word
features, wrapped in an isotonic calibrator with 3 folds, so the saved file
holds three forests: about 28 MB. A smaller file loads faster, needs less
server memory and costs less to ship and start. This script measures that
trade honestly, using the same protocol as scripts/train_lifecycle.py:

  * accuracy: grouped 4-fold cross-validation by data provider (every test
    record comes from a repair venue the model never saw), reporting the
    end-of-life recall and macro F1 the site quotes, plus the calibration
    error of the calibrated model;
  * cost: saved file size (plain and compressed), load time, memory used by
    loading it, and the time for one prediction.

Writes app_data/model_size_experiment.json. scripts/train_lifecycle.py ships
the configuration chosen from it.

    set PYTHONPATH=.
    venv\Scripts\python scripts\measure_model_size.py
"""
from __future__ import annotations

import gc
import json
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

from afterlife.lifecycle_model import CAT_FEATURES, EOL, NUM_FEATURES, TEXT_FEATURE, load_it_frame
from train_lifecycle import FOLDS, RANDOM, _scores, expected_calibration_error, preprocessor

OUT = ROOT / "app_data" / "model_size_experiment.json"
TREES = [300, 150, 100, 50]           # 300 is what shipped until now
COMPRESS = 3                          # joblib zlib level for the "compressed" size


def pipe(trees: int) -> Pipeline:
    return Pipeline([("pre", preprocessor("tokens")),
                     ("clf", RandomForestClassifier(n_estimators=trees, max_depth=18, min_samples_leaf=3,
                                                    class_weight="balanced", n_jobs=-1,
                                                    random_state=RANDOM))])


def accuracy(trees, X, y, groups) -> dict:
    folds, cal_p, truth = [], [], []
    for tr, te in GroupKFold(n_splits=FOLDS).split(X, y, groups):
        base = pipe(trees).fit(X.iloc[tr], y[tr])
        folds.append(_scores(y[te], base.predict(X.iloc[te])))
        cal = CalibratedClassifierCV(pipe(trees), method="isotonic", cv=3).fit(X.iloc[tr], y[tr])
        cal_p.append(cal.predict_proba(X.iloc[te])[:, EOL])
        truth.append((y[te] == EOL).astype(float))
    out = {k: round(float(np.mean([f[k] for f in folds])), 3) for k in ("eol_recall", "macro_f1", "accuracy")}
    out["eol_recall_sd"] = round(float(np.std([f["eol_recall"] for f in folds])), 3)
    out["ece_calibrated"] = round(expected_calibration_error(np.concatenate(cal_p), np.concatenate(truth)), 4)
    return out


def single_thread(model) -> None:
    """Run each forest in one thread (as afterlife/predict.py does after loading)."""
    for c in getattr(model, "calibrated_classifiers_", []):
        c.estimator.named_steps["clf"].n_jobs = 1


def _predict_ms(m, row) -> float:
    m.predict_proba(row)                           # warm up once
    t = time.perf_counter()
    for _ in range(50):
        m.predict_proba(row)
    return round((time.perf_counter() - t) / 50 * 1000, 1)


def cost(trees, X, y) -> dict:
    model = CalibratedClassifierCV(pipe(trees), method="isotonic", cv=3).fit(X, y)
    row = X.iloc[[0]]
    with tempfile.TemporaryDirectory() as d:
        plain, packed = Path(d) / "m.joblib", Path(d) / "mz.joblib"
        joblib.dump(model, plain)
        joblib.dump(model, packed, compress=COMPRESS)
        del model
        res = {"file_mb": round(plain.stat().st_size / 1e6, 2),
               "file_mb_compressed": round(packed.stat().st_size / 1e6, 2)}
        for name, path in (("plain", plain), ("compressed", packed)):
            loads = []
            for _ in range(3):
                gc.collect()
                t = time.perf_counter(); m = joblib.load(path); loads.append(time.perf_counter() - t)
                del m
            gc.collect()
            tracemalloc.start()
            m = joblib.load(path)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            res[f"load_s_{name}"] = round(float(np.median(loads)), 3)
            res[f"load_peak_mb_{name}"] = round(peak / 1e6, 1)
        res["predict_ms_parallel"] = _predict_ms(m, row)
        # One row at a time is how the site predicts; starting parallel
        # workers for a single row costs more than it saves.
        single_thread(m)
        res["predict_ms"] = _predict_ms(m, row)
    return res


def main() -> None:
    df = load_it_frame()
    X = df[CAT_FEATURES + NUM_FEATURES + [TEXT_FEATURE]]
    y = df["y"].to_numpy()
    groups = df["data_provider"].astype(str).to_numpy()
    # --cost-only re-measures size and speed on a quiet machine, keeping the
    # (slow, deterministic) accuracy results from the previous full run.
    cost_only = "--cost-only" in sys.argv and OUT.exists()
    previous = {v["trees"]: v for v in json.loads(OUT.read_text(encoding="utf-8"))["variants"]} if cost_only else {}
    rows = []
    for trees in TREES:
        t = time.perf_counter()
        acc = ({k: previous[trees][k] for k in ("eol_recall", "macro_f1", "accuracy", "eol_recall_sd", "ece_calibrated")}
               if cost_only else accuracy(trees, X, y, groups))
        r = {"trees": trees, **acc, **cost(trees, X, y)}
        r["experiment_s"] = round(time.perf_counter() - t)
        rows.append(r)
        print(json.dumps(r))
    OUT.write_text(json.dumps({
        "protocol": "Grouped 4-fold by data provider (unseen venues); calibrated with isotonic, 3 folds; "
                    "file sizes plain and joblib-compressed (zlib level 3); load time median of 3; "
                    "peak memory while loading (tracemalloc); one prediction averaged over 50.",
        "records": int(len(df)), "variants": rows,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
