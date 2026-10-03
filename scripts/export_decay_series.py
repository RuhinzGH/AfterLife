"""Align Windows 7 and Windows 10 decay on months-since-end-of-support.

Emits the JSON the headline chart renders from, including a fitted projection
for Windows 10 with the fit's own uncertainty band.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

SRC = ROOT / "data" / "raw" / "steam_hwsurvey_history.csv"
OUT = ROOT / "app_data"
OUT.mkdir(parents=True, exist_ok=True)

EOL = {"Windows 7": "2020-01-14", "Windows 10": "2025-10-14"}

df = pd.read_csv(SRC, parse_dates=["date"])
osv = df[df["category"] == "OS Version"]


def aligned(label: str, eol: str) -> pd.DataFrame:
    eol_ts = pd.Timestamp(eol)
    sel = osv[osv["name"].str.contains(rf"^{label}\b", case=False, na=False, regex=True)]
    s = sel.groupby("date")["percentage"].sum().sort_index()
    months = (s.index.year - eol_ts.year) * 12 + (s.index.month - eol_ts.month)
    out = pd.DataFrame({"month": months, "share": s.values * 100, "date": s.index})
    return out[(out["month"] >= -24) & (out["month"] <= 84)].reset_index(drop=True)


payload: dict = {"series": {}, "eol": EOL, "meta": {}}

for label, eol in EOL.items():
    a = aligned(label, eol)
    payload["series"][label] = [
        {"month": int(r.month), "share": round(float(r.share), 3),
         "date": r.date.strftime("%Y-%m")}
        for r in a.itertuples()
    ]
    at_eol = a[a["month"] <= 0]
    print(f"{label}: {len(a)} points, share at EOL "
          f"{at_eol['share'].iloc[-1] if len(at_eol) else float('nan'):.2f}%")

# --- projection for Windows 10, fitted on observed post-EOL points only ---
w10 = pd.DataFrame(payload["series"]["Windows 10"])
post = w10[(w10["month"] > 0) & (w10["share"] > 0)]
x, y = post["month"].values.astype(float), np.log(post["share"].values)
n = len(x)
k, logA = np.polyfit(x, y, 1)

resid = y - (k * x + logA)
dof = max(n - 2, 1)
s_err = float(np.sqrt((resid**2).sum() / dof))
sxx = float(((x - x.mean()) ** 2).sum()) or 1.0

future = np.arange(int(post["month"].max()) + 1, 85)
fit = np.exp(k * future + logA)
# prediction interval on the log scale, widening with distance from the fit centre
se = s_err * np.sqrt(1 + 1 / n + (future - x.mean()) ** 2 / sxx)
lo, hi = np.exp(k * future + logA - 1.96 * se), np.exp(k * future + logA + 1.96 * se)

payload["projection"] = [
    {"month": int(m), "fit": round(float(f), 3),
     "lo": round(float(l), 3), "hi": round(float(h), 3)}
    for m, f, l, h in zip(future, fit, lo, hi)
]

cross = future[fit < 5.0]
cross_lo = future[hi < 5.0]
cross_hi = future[lo < 5.0]
payload["meta"] = {
    "monthly_decay_pct": round(float((np.exp(k) - 1) * 100), 2),
    "n_observed_post_eol": int(n),
    "months_to_5pct": int(cross[0]) if len(cross) else None,
    "months_to_5pct_early": int(cross_hi[0]) if len(cross_hi) else None,
    "months_to_5pct_late": int(cross_lo[0]) if len(cross_lo) else None,
    "r_squared": round(float(1 - (resid**2).sum() / ((y - y.mean())**2).sum()), 4),
}

print(f"\nfit on n={n} post-EOL points, R^2={payload['meta']['r_squared']}")
print(f"monthly decay: {payload['meta']['monthly_decay_pct']}%")
print(f"months to <5%: {payload['meta']['months_to_5pct']} "
      f"(95% PI {payload['meta']['months_to_5pct_early']}"
      f"..{payload['meta']['months_to_5pct_late']})")

# Windows 7's first dip below 5% is not durable -- the survey is noisy and the
# series bounces back above the line several times. The comparable metric against
# Windows 10's smooth fitted projection is when it SETTLED below 5% for good.
w7 = pd.DataFrame(payload["series"]["Windows 7"])
post7 = w7[w7["month"] > 0]
first = post7[post7["share"] < 5]
above = post7[post7["share"] >= 5]
payload["meta"]["win7_first_below_5pct"] = int(first["month"].iloc[0]) if len(first) else None
payload["meta"]["win7_months_to_5pct"] = (
    int(above["month"].iloc[-1]) + 1 if len(above) else payload["meta"]["win7_first_below_5pct"]
)
payload["meta"]["win7_excursions"] = int(
    len(above[above["month"] > (payload["meta"]["win7_first_below_5pct"] or 0)])
)
print(f"Windows 7 first dipped <5% at month {payload['meta']['win7_first_below_5pct']}, "
      f"settled from month {payload['meta']['win7_months_to_5pct']} "
      f"({payload['meta']['win7_excursions']} excursions back above)")

(OUT / "decay.json").write_text(json.dumps(payload, indent=2))
print(f"\nsaved -> app_data/decay.json")
