"""Derive real fault -> outcome evidence from Open Repair Alliance records.

The repair advice in this app used to be generic hygiene ("replace the battery,
it's cheaper than a new device") -- reasonable, but asserted. This grounds it in
the same dataset the classifier already trains on, so every line the app shows
about a fault can be backed by a count.

One honest limitation shaped the whole design: ORA records what was *wrong*
(`problem`, free text) and how it *ended* (`repair_status`), but there is no
column recording which repair was performed. So this does NOT claim "the fix for
a swollen battery is a new battery" -- that would be inventing a field. What it
computes is strictly what the data supports:

    for devices brought in with fault X, what share left working,
    and when they didn't, what stopped the repair

which is more useful anyway: it answers "is this worth attempting?" with a rate
instead of a platitude.

The text is multilingual (German, Dutch, French and English all appear in the
same column, since these are community repair events across Europe), so theme
matching is a multilingual keyword union rather than an English-only search. A
record matching several themes counts toward each -- a laptop that arrived with
a swollen battery *and* a cracked hinge is evidence about both.

    python scripts/build_repair_evidence.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

SRC = ROOT / "data" / "raw" / "openrepair_202507.csv"
OUT = ROOT / "app_data" / "repair_evidence.json"

#: Only computer-shaped devices. A coffee maker's fix rate says nothing about a
#: laptop's, and this app never assesses one.
IT_CATEGORIES = ["Laptop", "Desktop computer", "Tablet", "Mobile", "Games console"]

#: Below this, a percentage is noise dressed up as a finding. The same threshold
#: the country map already uses to grey out low-n countries.
MIN_N = 50

#: Fault themes now live in afterlife/fault_lexicon.py, because the model
#: trains on exactly these keyword sets as its venue-invariant text
#: representation. Two copies would let the card and the classifier drift
#: into describing different faults from one dataset.
from afterlife.fault_lexicon import THEMES  # noqa: E402


def _matcher(keywords: list[str]) -> re.Pattern:
    return re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC} -- run scripts/fetch_openrepair.py first")

    df = pd.read_csv(SRC, low_memory=False)
    it = df[df["product_category"].isin(IT_CATEGORIES)].copy()
    it["problem"] = it["problem"].fillna("").astype(str)
    # "Unknown" is an unrecorded outcome, not a failed repair -- counting it as
    # either would bend the rate in a direction the data does not support.
    known = it[it["repair_status"].isin(["Fixed", "Repairable", "End of life"])]

    themes = []
    for key, meta in THEMES.items():
        hit = known[known["problem"].str.contains(_matcher(meta["kw"]), na=False)]
        n = len(hit)
        if n < MIN_N:
            continue
        fixed = int((hit["repair_status"] == "Fixed").sum())
        eol = int((hit["repair_status"] == "End of life").sum())
        barriers = (hit.loc[hit["repair_status"] == "End of life",
                            "repair_barrier_if_end_of_life"]
                    .dropna().value_counts())
        themes.append({
            "key": key,
            "label": meta["label"],
            "plain": meta["plain"],
            "n": n,
            "fixed": fixed,
            "fixed_pct": round(fixed / n * 100, 1),
            "eol": eol,
            "eol_pct": round(eol / n * 100, 1),
            "top_barrier": barriers.index[0] if len(barriers) else None,
            "top_barrier_n": int(barriers.iloc[0]) if len(barriers) else 0,
        })

    themes.sort(key=lambda t: t["n"], reverse=True)

    overall_fixed = int((known["repair_status"] == "Fixed").sum())
    payload = {
        "source": "Open Repair Alliance, openrepair_202507",
        "categories": IT_CATEGORIES,
        "min_n": MIN_N,
        "n_records": int(len(known)),
        "overall_fixed_pct": round(overall_fixed / len(known) * 100, 1),
        "themes": themes,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"{len(known):,} IT repair records, {payload['overall_fixed_pct']}% fixed overall")
    for t in themes:
        print(f"  {t['label']:<28} n={t['n']:>5}  fixed {t['fixed_pct']:>5.1f}%  "
              f"eol {t['eol_pct']:>4.1f}%  barrier: {t['top_barrier']}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
