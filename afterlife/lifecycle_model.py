"""Lifecycle-outcome classifier trained on Open Repair Alliance data.

Target: repair_status for a device brought to a repair event — Fixed, Repairable,
or End of life. These are real labels assigned by technicians, not invented by this
project, which is what makes the supervised problem legitimate.

The class that matters for Afterlife's thesis is END OF LIFE — "is this device
genuinely beyond saving?" So models are selected on End-of-life recall, not overall
accuracy. That distinction is deliberate: a model that scores well on accuracy by
predicting the majority "Fixed" class while missing the e-waste cases is useless for
the decision we care about. (Same trap documented in an earlier project; not repeated.)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "raw" / "openrepair_202507.csv"
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

IT_CATEGORIES = ["Laptop", "Mobile", "Tablet", "Desktop computer", "Games console"]
CLASSES = ["Fixed", "Repairable", "End of life"]
CLASS_IDX = {c: i for i, c in enumerate(CLASSES)}
EOL = CLASS_IDX["End of life"]

CAT_FEATURES = ["product_category", "brand", "country"]
NUM_FEATURES = ["device_age", "event_year"]
TEXT_FEATURE = "problem"


def load_it_frame() -> pd.DataFrame:
    """IT-device subset with engineered, model-ready columns."""
    df = pd.read_csv(DATA, low_memory=False)
    df = df[df["product_category"].isin(IT_CATEGORIES)].copy()
    df = df[df["repair_status"].isin(CLASSES)].copy()

    # age: prefer the explicit product_age, fall back to year_of_manufacture
    age = pd.to_numeric(df.get("product_age"), errors="coerce")
    yom = pd.to_numeric(df.get("year_of_manufacture"), errors="coerce")
    ev = pd.to_datetime(df.get("event_date"), errors="coerce")
    df["event_year"] = ev.dt.year
    age_from_yom = df["event_year"] - yom
    df["device_age"] = age.where(age.between(0, 40), age_from_yom.where(age_from_yom.between(0, 40)))

    df["brand"] = df["brand"].fillna("Unknown").replace({"": "Unknown"})
    df["country"] = df["country"].fillna("Unknown")
    df["problem"] = df["problem"].fillna("").astype(str)
    df["y"] = df["repair_status"].map(CLASS_IDX)
    return df


@dataclass
class EvalRow:
    model: str
    accuracy: float
    macro_f1: float
    eol_recall: float
    eol_precision: float
    fixed_recall: float


def class_distribution(df: pd.DataFrame) -> dict[str, Any]:
    counts = df["repair_status"].value_counts()
    return {c: int(counts.get(c, 0)) for c in CLASSES}
