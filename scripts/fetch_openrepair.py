"""Pull the latest Open Repair Alliance aggregate and characterise the IT slice."""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import requests

UA = {"User-Agent": "Afterlife-research/0.1"}
BASE = "https://raw.githubusercontent.com/openrepair/data/master/"
LATEST = "aggregated/202507/OpenRepairData_v0.3_aggregate_202507.csv"
OUT = ROOT / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

print(f"GET {LATEST}")
r = requests.get(BASE + LATEST, headers=UA, timeout=300)
r.raise_for_status()
dest = OUT / "openrepair_202507.csv"
dest.write_text(r.text, encoding="utf-8")

df = pd.read_csv(io.StringIO(r.text), low_memory=False)
print(f"rows={len(df):,}  cols={len(df.columns)}  -> {dest.name} ({dest.stat().st_size/1e6:.0f} MB)")
print("columns:", list(df.columns))

print("\n=== repair_status (the label) ===")
print(df["repair_status"].value_counts().to_string())

print("\n=== product_category: IT-relevant slice ===")
IT = ["Laptop", "Desktop computer", "Mobile", "Tablet", "Mobile phone",
      "Monitor", "Printer", "Games console", "Desktop"]
cats = df["product_category"].value_counts()
print(cats.head(15).to_string())

it = df[df["product_category"].isin(cats.index[cats.index.isin(IT)])]
print(f"\nIT-device records: {len(it):,} ({100*len(it)/len(df):.1f}% of all)")
print(it["product_category"].value_counts().to_string())

print("\n=== repair_status within IT devices ===")
print(it["repair_status"].value_counts().to_string())
known = it[it["repair_status"].isin(["Fixed", "Repairable", "End of life"])]
print(f"\nusable labelled IT records: {len(known):,}")
print((100 * known["repair_status"].value_counts(normalize=True)).round(1).to_string())

if "repair_barrier_if_end_of_life" in df.columns:
    print("\n=== why IT devices became end-of-life ===")
    eol = it[it["repair_status"] == "End of life"]
    print(eol["repair_barrier_if_end_of_life"].value_counts().to_string())

print("\n=== year_of_manufacture completeness (IT slice) ===")
yom = pd.to_numeric(it["year_of_manufacture"], errors="coerce")
print(f"parseable: {yom.notna().sum():,} / {len(it):,} ({100*yom.notna().mean():.1f}%)")
if yom.notna().any():
    valid = yom[(yom > 1990) & (yom <= 2026)]
    print(f"median year of manufacture: {valid.median():.0f}")
    print(f"implied median age at repair: {2026 - valid.median():.0f} years")

print("\n=== brands (IT slice) ===")
print(it["brand"].value_counts().head(12).to_string())
