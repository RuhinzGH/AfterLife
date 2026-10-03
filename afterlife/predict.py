"""Load the trained lifecycle model and predict from device features."""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from .lifecycle_model import CAT_FEATURES, CLASSES, MODEL_DIR, NUM_FEATURES, TEXT_FEATURE

MODEL_PATH = MODEL_DIR / "lifecycle_model.joblib"


@functools.lru_cache(maxsize=1)
def _model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError("train the model first: scripts/train_lifecycle.py")
    return joblib.load(MODEL_PATH)


def predict_lifecycle(
    product_category: str,
    brand: str = "Unknown",
    country: str = "Unknown",
    device_age: float | None = None,
    problem: str = "",
    event_year: int = 2026,
) -> dict[str, Any]:
    """Return the predicted lifecycle outcome and full class probabilities."""
    row = pd.DataFrame([{
        "product_category": product_category,
        "brand": brand or "Unknown",
        "country": country or "Unknown",
        "device_age": device_age,
        "event_year": event_year,
        "problem": problem or "",
    }])[CAT_FEATURES + NUM_FEATURES + [TEXT_FEATURE]]

    model = _model()
    probs = model.predict_proba(row)[0]
    idx = int(probs.argmax())
    ranked = sorted(
        ({"label": CLASSES[i], "probability": round(float(p), 4)} for i, p in enumerate(probs)),
        key=lambda d: -d["probability"],
    )
    return {
        "prediction": CLASSES[idx],
        "confidence": round(float(probs[idx]), 4),
        "probabilities": ranked,
        "eol_risk": round(float(probs[CLASSES.index("End of life")]), 4),
    }
