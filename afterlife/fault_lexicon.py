"""A language-independent fault signature for multilingual repair text.

WHY THIS EXISTS
---------------
The Open Repair Alliance records are written by volunteers in whatever language
the repair event runs in -- German, Dutch, French and English all appear in the
same column. Roughly 19% of rows carry English markers, 6% German, 6% Dutch,
5% French.

Language therefore tracks *venue*: Dutch fault text is a Dutch repair cafe. Any
token-based representation (word TF-IDF) consequently encodes which group logged
the record, and a model trained on it can score well by recognising the venue
instead of reading the fault. That is not hypothetical here -- measured on this
dataset, a random train/test split scores 21 accuracy points higher than a split
that holds out whole venues, and the gap is the model recognising its training
venues.

This module maps free text in any of those languages onto the same small set of
fault categories, so the representation cannot encode the language it was
written in and therefore cannot leak the venue. It is a deliberately blunt
instrument: nine binary features against several hundred TF-IDF columns.

WHAT IT IS AND IS NOT
---------------------
This is lexicon-based feature extraction, a long-established technique -- not a
new method. What is specific here is the application: using it as a
*venue-invariant* representation for repair-outcome prediction, on a dataset
that had no published machine-learning baseline to compare against.

The keyword sets are shared with scripts/build_repair_evidence.py, so the fault
themes the research page reports and the features the model trains on can never
drift apart.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

#: Fault themes as multilingual keyword unions. Recall matters more than
#: precision: a theme that matches too broadly is diluted evidence, but a theme
#: that misses the German phrasing is a feature that silently only works in
#: English-speaking countries -- which is the exact failure this module exists to
#: prevent.
THEMES: dict[str, dict[str, object]] = {
    "battery": {
        "label": "Battery",
        "plain": "battery won't hold charge, or has swollen",
        "kw": ["akku", "batterij", "battery", "batterie", "accu", "pile",
               "aufgebl", "opgezwollen", "swollen"],
    },
    "power": {
        "label": "Power / won't start",
        "plain": "won't turn on, or won't charge",
        "kw": ["netzteil", "ladeger", "oplader", "charger", "adapter", "power supply",
               "start nicht", "startet nicht", "gaat niet aan", "start niet",
               "won't turn on", "wont turn on", "no power", "geen stroom",
               "doet het niet", "dead"],
    },
    "storage": {
        "label": "Storage",
        "plain": "hard drive or SSD failing",
        "kw": ["festplatte", "harde schijf", "hard drive", "harddisk", "hard disk",
               "hdd", "ssd", "disque dur"],
    },
    "screen": {
        "label": "Screen",
        "plain": "display cracked, dim or blank",
        "kw": ["bildschirm", "display", "scherm", "screen", "beeldscherm",
               "ecran", "écran", "lcd", "backlight"],
    },
    "overheating": {
        "label": "Overheating / fan",
        "plain": "runs hot, or the fan is loud",
        "kw": ["lüfter", "lufter", "ventilator", "ventilateur", "fan",
               "überhitz", "uberhitz", "overheat", "oververhit", "te heet",
               "heiß", "warmleitpaste", "wärmeleitpaste", "thermal paste"],
    },
    "keyboard": {
        "label": "Keyboard / trackpad",
        "plain": "keys or trackpad not responding",
        "kw": ["tastatur", "toetsenbord", "keyboard", "clavier", "trackpad",
               "touchpad", "maus", "muis"],
    },
    "software": {
        "label": "Software / operating system",
        "plain": "slow, won't update, or won't boot into Windows",
        "kw": ["windows", "software", "betriebssystem", "besturingssysteem",
               "update", "virus", "langsam", "traag", "slow", "bios", "boot",
               "systeem", "system", "linux", "ubuntu"],
    },
    "physical": {
        "label": "Hinge / casing",
        "plain": "hinge, lid or case broken",
        "kw": ["scharnier", "hinge", "charnière", "gehäuse", "behuizing",
               "casing", "gebroken", "gebrochen", "cracked", "kapot"],
    },
    "ports": {
        "label": "Ports / connectors",
        "plain": "a socket or port has stopped working",
        "kw": ["usb", "anschluss", "aansluiting", "buchse", "connector",
               "port", "hdmi", "jack", "klinke"],
    },
}

THEME_KEYS: list[str] = list(THEMES)

_PATTERNS: dict[str, re.Pattern] = {
    key: re.compile("|".join(re.escape(w) for w in meta["kw"]), re.IGNORECASE)
    for key, meta in THEMES.items()
}


def theme_features(X) -> np.ndarray:
    """Free text -> an (n, 9) binary fault signature.

    A module-level named function, deliberately, rather than a lambda inside the
    pipeline: joblib pickles the fitted model by reference, and a lambda cannot
    be pickled -- the model would train fine and then fail to load in production,
    which is the worst place to discover it.

    Accepts either a DataFrame (uses the `problem` column) or anything Series-
    like, so the same transformer works inside a ColumnTransformer and standalone.
    """
    if isinstance(X, pd.DataFrame):
        text = X["problem"] if "problem" in X.columns else X.iloc[:, 0]
    else:
        text = pd.Series(np.asarray(X).ravel())
    text = text.fillna("").astype(str)
    return np.column_stack([
        text.str.contains(_PATTERNS[k], regex=True).to_numpy(dtype=float)
        for k in THEME_KEYS
    ])


def feature_names() -> list[str]:
    return [f"fault:{k}" for k in THEME_KEYS]
