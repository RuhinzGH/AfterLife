"""Exploratory analysis of the live EPREL smartphone and tablet registry.

Every figure the Lab 3 write-up quotes is computed here, so the report cannot
drift from the data. Run after scripts/pull_eprel.py has refreshed the pull:

    python scripts/pull_eprel.py && python scripts/eda_eprel.py

Prints a section per finding and writes app_data/eprel_eda.json for the figures.
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, kruskal, spearmanr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "app_data" / "eprel_devices.json"
OUT = ROOT / "app_data" / "eprel_eda.json"

CLASSES = ["A", "B", "C", "D", "E"]


def cramers_v(chi2: float, n: int, r: int, c: int) -> float:
    return float(np.sqrt(chi2 / (n * min(r - 1, c - 1))))


def head(t: str) -> None:
    print(f"\n{'=' * 74}\n{t}\n{'=' * 74}")


def main() -> None:
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    df = pd.DataFrame(raw["devices"])
    res: dict = {"fetched": raw.get("fetched"), "source": raw.get("source"),
                 "regulation": raw.get("regulation")}

    head("1. PROVENANCE AND SHAPE")
    print(f"fetched          : {raw.get('fetched')}")
    print(f"regulation       : {raw.get('regulation')}")
    print(f"models           : {len(df):,}")
    print(f"variables        : {df.shape[1]}")
    # EPREL returns the date as a [year, month, day] array rather than a string,
    # so it has to be assembled before pandas can read it.
    def as_date(v):
        if isinstance(v, list) and len(v) == 3:
            try:
                return pd.Timestamp(year=v[0], month=v[1], day=v[2])
            except Exception:
                return pd.NaT
        return pd.NaT
    dates = df["onMarketStartDate"].map(as_date)

    # Derived variables the raw fields only imply.
    df["countries"] = df["modelAvailabilityInEUEEACountries"].map(
        lambda v: len(v) if isinstance(v, list) else 0)
    df["mohs"] = pd.to_numeric(
        df["screenScratchResistance"].astype(str).str.extract(r"MOHS_(\d+)")[0], errors="coerce")
    # IP rating: the second digit is the water-ingress level, which is the half
    # that varies here and the half a repairer cares about.
    df["ip_water"] = pd.to_numeric(
        df["ingressProtectionRating"].astype(str).str.extract(r"IP\d(\d)")[0], errors="coerce")
    print(f"on-market range  : {dates.min():%Y-%m-%d} .. {dates.max():%Y-%m-%d}")
    res["n"] = int(len(df))
    res["variables"] = int(df.shape[1])
    res["date_min"] = str(dates.min().date())
    res["date_max"] = str(dates.max().date())

    head("2. MISSINGNESS PER VARIABLE")
    miss = (df.isna() | df.eq("")).mean().sort_values(ascending=False) * 100
    for k, v in miss.items():
        if v > 0:
            print(f"  {k:<38} {v:5.1f}%")
    if (miss == 0).all():
        print("  no field is missing on any record")
    res["missing_pct"] = {k: round(float(v), 2) for k, v in miss.items() if v > 0}

    head("3. THE TARGET: REPAIRABILITY CLASS")
    rc = df["repairabilityClass"].value_counts().reindex(CLASSES).fillna(0).astype(int)
    for k, v in rc.items():
        print(f"  {k}  {v:>5,}  {100 * v / len(df):5.1f}%")
    print(f"\n  repairabilityIndex: mean {df['repairabilityIndex'].mean():.2f}, "
          f"median {df['repairabilityIndex'].median():.2f}, "
          f"min {df['repairabilityIndex'].min():.2f}, max {df['repairabilityIndex'].max():.2f}")
    res["repairability_class"] = {k: int(v) for k, v in rc.items()}
    res["repairability_index"] = {
        "mean": round(float(df["repairabilityIndex"].mean()), 3),
        "median": round(float(df["repairabilityIndex"].median()), 3),
        "min": round(float(df["repairabilityIndex"].min()), 3),
        "max": round(float(df["repairabilityIndex"].max()), 3),
    }

    head("4. BRAND CONCENTRATION")
    b = df["supplierOrTrademark"].value_counts()
    print(f"  distinct brands  : {len(b)}")
    print(f"  top 10 share     : {100 * b.head(10).sum() / len(df):.1f}%")
    print(f"  brands with 1 model: {(b == 1).sum()}")
    for k, v in b.head(8).items():
        print(f"    {k:<20} {v:>4}  ({100 * v / len(df):.1f}%)")
    res["brands_total"] = int(len(b))
    res["brands_top10_share"] = round(float(100 * b.head(10).sum() / len(df)), 1)
    res["brands_singleton"] = int((b == 1).sum())
    res["brands_top"] = {k: int(v) for k, v in b.head(8).items()}

    head("5. DOES REPAIRABILITY DEPEND ON DEVICE TYPE?")
    ct = pd.crosstab(df["deviceType"], df["repairabilityClass"])
    print(ct.to_string())
    chi2, p, dof, _ = chi2_contingency(ct)
    v = cramers_v(chi2, int(ct.values.sum()), *ct.shape)
    print(f"\n  chi2 = {chi2:,.1f}, df = {dof}, p = {p:.3g}, Cramer's V = {v:.3f}")
    for t in ct.index:
        sub = df[df["deviceType"] == t]["repairabilityIndex"]
        print(f"  {t:<12} mean index {sub.mean():.2f}  (n = {len(sub):,})")
    res["devicetype_chi2"] = {"chi2": round(float(chi2), 1), "df": int(dof),
                              "p": float(p), "v": round(v, 3)}
    res["devicetype_index_mean"] = {t: round(float(df[df["deviceType"] == t]["repairabilityIndex"].mean()), 3)
                                    for t in ct.index}

    head("6. USER-REPLACEABLE BATTERY vs REPAIRABILITY")
    g = df.groupby("batteryUserReplaceable")["repairabilityIndex"]
    for k, sub in g:
        print(f"  replaceable={str(k):<5} n={len(sub):>5,}  mean {sub.mean():.2f}  median {sub.median():.2f}")
    a = df[df["batteryUserReplaceable"] == True]["repairabilityIndex"].dropna()
    bb = df[df["batteryUserReplaceable"] == False]["repairabilityIndex"].dropna()
    st, pv = kruskal(a, bb)
    print(f"\n  Kruskal-Wallis H = {st:.1f}, p = {pv:.3g}")
    print(f"  difference in means = {a.mean() - bb.mean():.2f} index points")
    res["battery"] = {"replaceable_mean": round(float(a.mean()), 3),
                      "fixed_mean": round(float(bb.mean()), 3),
                      "H": round(float(st), 1), "p": float(pv),
                      "n_replaceable": int(len(a)), "n_fixed": int(len(bb))}

    head("7. WHAT THE INDEX IS MADE OF (SPEARMAN vs INDEX)")
    parts = ["disassemblyDepthScore", "fastenersScore", "toolsScore",
             "softwareUpdatesScore", "minYearsSoftwareUpdates",
             "batteryEnduranceInCycles", "ratedBatteryCapacity", "guaranteeDuration",
             "mohs", "ip_water", "countries"]
    corr = {}
    for c in parts:
        s = pd.to_numeric(df[c], errors="coerce")
        ok = s.notna() & df["repairabilityIndex"].notna()
        if ok.sum() < 30:
            continue
        rho, pv = spearmanr(s[ok], df["repairabilityIndex"][ok])
        corr[c] = round(float(rho), 3)
        print(f"  {c:<28} rho = {rho:+.3f}  (p = {pv:.2g}, n = {ok.sum():,})")
    res["spearman_vs_index"] = corr

    head("8. DURABILITY vs REPAIRABILITY -- INDEPENDENT AXES?")
    ct2 = pd.crosstab(df["repeatedFreeFallReliabilityClass"], df["repairabilityClass"])
    chi2b, pb, dofb, _ = chi2_contingency(ct2)
    vb = cramers_v(chi2b, int(ct2.values.sum()), *ct2.shape)
    print(ct2.to_string())
    print(f"\n  chi2 = {chi2b:,.1f}, df = {dofb}, p = {pb:.3g}, Cramer's V = {vb:.3f}")
    fall = df["repeatedFreeFallReliabilityClass"].value_counts().reindex(CLASSES).fillna(0).astype(int)
    print("\n  fall-reliability distribution:", dict(fall))
    res["durability_chi2"] = {"chi2": round(float(chi2b), 1), "df": int(dofb),
                              "p": float(pb), "v": round(vb, 3)}
    res["fall_class"] = {k: int(v) for k, v in fall.items()}

    head("9. DATA-QUALITY DEFECTS")
    sw = pd.to_numeric(df["minYearsSoftwareUpdates"], errors="coerce")
    print("  minYearsSoftwareUpdates:", dict(sorted(Counter(sw.dropna().astype(int)).items())))
    print(f"    legal floor is 5 years; {int((sw < 5).sum())} record(s) below it, "
          f"{int((sw > 10).sum())} above 10")
    cap = pd.to_numeric(df["ratedBatteryCapacity"], errors="coerce")
    print(f"  ratedBatteryCapacity mAh: min {cap.min():,.0f}, max {cap.max():,.0f}, "
          f"median {cap.median():,.0f}")
    cyc = pd.to_numeric(df["batteryEnduranceInCycles"], errors="coerce")
    print(f"  batteryEnduranceInCycles: min {cyc.min():,.0f}, max {cyc.max():,.0f}, "
          f"median {cyc.median():,.0f}")
    empty_countries = int((df["countries"] == 0).sum())
    print(f"  models listing NO EU/EEA country: {empty_countries:,} "
          f"({100 * empty_countries / len(df):.1f}%)")
    dupes = int(df["modelIdentifier"].duplicated().sum())
    print(f"  duplicate modelIdentifier values: {dupes}")
    res["quality"] = {
        "sw_years": {str(k): int(v) for k, v in sorted(Counter(sw.dropna().astype(int)).items())},
        "sw_above_10": int((sw > 10).sum()),
        "capacity_min": float(cap.min()), "capacity_max": float(cap.max()),
        "cycles_min": float(cyc.min()), "cycles_max": float(cyc.max()),
        "duplicate_model_ids": dupes,
        "no_country_listed": empty_countries,
    }

    head("10. GROWTH OF THE REGISTRY (on-market year)")
    yr = dates.dt.year.value_counts().sort_index()
    for k, v in yr.items():
        if not np.isnan(k):
            print(f"  {int(k)}  {v:>5,}")
    res["by_year"] = {str(int(k)): int(v) for k, v in yr.items() if not np.isnan(k)}

    OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
