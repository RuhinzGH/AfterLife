"""Do drives wear out with age, or fail at random? Measure it.

WHY THIS IS THE QUESTION AFTERLIFE NEEDS ANSWERED
-------------------------------------------------
The product's argument is that devices are retired years before they
functionally fail -- pushed out by OS support cliffs and perception rather than
by hardware giving up. That rests on a premise nobody here had checked: that age
is a poor predictor of hardware failure in the first place.

If failure risk climbs steeply with age then "old" really does mean "about to
break", retirement-by-age is defensible, and the thesis needs qualifying. If the
rate is flat, age is a bad proxy for condition and the argument gains a measured
foundation instead of a rhetorical one.

WHY THIS IS NOT A WEIBULL FIT
-----------------------------
A parametric lifetime model is the obvious approach and was the first thing
tried. It does not survive contact with the data, and the reason is recorded
here because it would otherwise be re-attempted.

The dataset covers 25,855 SSDs over about sixteen weeks. Drive ages span 10 to
1,368 days -- nearly four years -- but the MEDIAN DRIVE IS OBSERVED FOR FOUR
DAYS OF ITS OWN AGE, and a quarter appear on a single day. Fitting a lifetime
distribution to that means extrapolating a four-year hazard curve from a
twenty-day keyhole per drive, with entry times scattered across the whole range.

lifelines said so plainly rather than failing quietly. The Weibull variance
matrix came back with negative diagonal entries ("be suspicious of the fitted
parameters too"); Kaplan-Meier refused outright ("too few early truncation
times... S(t)==0 for all t>19"); and per-model shape parameters ranged from 0.11
to 1.43, disagreeing with the pooled fit and with each other. A pooled rho of
1.335 with a tight-looking confidence interval was available and would have been
a publishable-looking number resting on nothing.

So the question gets answered the way this data can answer it.

WHAT IS COMPUTED INSTEAD
------------------------
The empirical hazard: fail-slow events per thousand drive-days, bucketed by
drive age. Every observed drive-day counts once, in the bucket matching that
drive's age that day. No functional form is assumed and nothing is extrapolated
past the observation window. An exact Poisson interval accompanies every band,
because a rate computed from few drive-days is not a rate worth reading.

THREE THINGS THAT WOULD OTHERWISE BIAS IT
-----------------------------------------
1. NO SURVIVORSHIP FILTER. Drive-days are counted as they occur. There is no
   "observed at least N days" cut, which would preferentially keep long-lived
   drives -- exactly the ones most likely to have had an event.

2. FAIL-SLOW IS NOT FAILURE. The event is a drive going persistently, hugely
   slower than its peers -- degraded, not dead. Arguably the more useful event
   for this product, since a machine nobody can stand to use gets replaced
   whether or not it still works, but it is a different claim and is labelled
   as one everywhere.

3. ENTERPRISE, NOT CONSUMER. The caveat this codebase already applies to the
   NVMe model, unchanged: datacenter drives under datacenter workloads. What
   might transfer is the SHAPE of the age relationship, never the absolute rates.

    python scripts/survival_failslow.py
"""
from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pandas as pd
from scipy.stats import chi2, spearmanr

SRC = ROOT / "data" / "derived" / "failslow_ssd_drivedays.parquet"
OUT = ROOT / "app_data" / "survival_failslow.json"

#: The fail-slow threshold to model. The dataset flags several; 30 minutes of
#: cumulative slowness in a day is the middle one and the least sensitive to
#: transient spikes.
EVENT = "event_30min"

#: Age bands in days. Roughly half-year steps to three years, then everything
#: older together -- chosen so each band holds enough drive-days to support a
#: rate, not to make any particular shape appear.
BANDS = [(0, 182), (182, 365), (365, 547), (547, 730),
         (730, 912), (912, 1095), (1095, 10_000)]

#: Below this a band's rate is reported but flagged as too thin to read.
_MIN_DRIVE_DAYS = 500


def _rate_ci(events: int, drive_days: int) -> tuple[float, float, float]:
    """Events per 1,000 drive-days, with an exact Poisson 95% interval.

    Exact rather than normal-approximate: several bands have single-digit event
    counts, where the normal interval is meaningless and can run negative.
    """
    if drive_days <= 0:
        return 0.0, 0.0, 0.0
    lo = chi2.ppf(0.025, 2 * events) / 2 if events > 0 else 0.0
    hi = chi2.ppf(0.975, 2 * events + 2) / 2
    k = 1000.0 / drive_days
    return events * k, lo * k, hi * k


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC} -- run scripts/analyze_failslow.py first")

    df = pd.read_parquet(SRC).dropna(subset=["age"]).copy()
    df["age"] = df["age"].astype(float)

    total_days = len(df)
    total_events = int(df[EVENT].sum())
    n_drives = df.groupby(["node_id", "drive"]).ngroups
    print(f"{n_drives:,} drives, {total_days:,} drive-days, "
          f"{total_events:,} fail-slow days "
          f"({1000 * total_events / total_days:.2f} per 1,000 drive-days)")
    print(f"age {df['age'].min():.0f}-{df['age'].max():.0f} days\n")

    rows = []
    print(f"{'age band (days)':<18}{'drive-days':>12}{'events':>9}{'per 1k':>9}{'95% CI':>18}")
    for lo, hi in BANDS:
        sel = df[(df["age"] >= lo) & (df["age"] < hi)]
        dd, ev = len(sel), int(sel[EVENT].sum())
        rate, rlo, rhi = _rate_ci(ev, dd)
        label = f"{lo}-{hi}" if hi < 10_000 else f"{lo}+"
        thin = dd < _MIN_DRIVE_DAYS
        rows.append({
            "band": label, "from_days": lo,
            "to_days": None if hi >= 10_000 else hi,
            "drive_days": dd, "events": ev,
            "rate_per_1k_drive_days": round(rate, 3),
            "ci95": [round(rlo, 3), round(rhi, 3)],
            "thin": bool(thin),
        })
        print(f"{label:<18}{dd:>12,}{ev:>9,}{rate:>9.2f}"
              f"{f'{rlo:.2f}-{rhi:.2f}':>18}{'  (thin)' if thin else ''}")

    solid = [r for r in rows if not r["thin"] and r["drive_days"] > 0]

    # Does the rate trend with age? Spearman on band midpoints. With this few
    # bands a rank correlation is the honest summary; a fitted slope would
    # overstate how much precision is available.
    verdict, note, rho_s, p_s = "indeterminate", "Too few usable bands to judge.", None, None
    if len(solid) >= 4:
        mids = [r["from_days"] + 91 for r in solid]
        rates = [r["rate_per_1k_drive_days"] for r in solid]
        rho_s, p_s = spearmanr(mids, rates)
        first, last = solid[0]["rate_per_1k_drive_days"], solid[-1]["rate_per_1k_drive_days"]
        ratio = (last / first) if first > 0 else float("inf")

        if p_s < 0.05 and rho_s > 0:
            verdict = "wear-out"
            note = (f"Fail-slow rate rises with age (Spearman rho={rho_s:.2f}, "
                    f"p={p_s:.3g}); the oldest usable band runs {ratio:.1f}x the "
                    f"youngest. Age carries real information about degradation.")
        elif p_s < 0.05 and rho_s < 0:
            verdict = "improves with age"
            note = (f"Fail-slow rate FALLS with age (Spearman rho={rho_s:.2f}, "
                    f"p={p_s:.3g}). Drives surviving early life get steadier.")
        else:
            verdict = "age-independent"
            note = (f"No monotone trend with age (Spearman rho={rho_s:.2f}, "
                    f"p={p_s:.3g}). Within the observed range, age is a poor "
                    f"predictor of whether a drive is degrading.")

    print(f"\nverdict: {verdict}\n  {note}")

    # Per model, because "a drive" is not one population. The spread between
    # models is the check on whether a pooled age trend is really about age.
    by_model = {}
    for m, sub in df.groupby("model"):
        dd, ev = len(sub), int(sub[EVENT].sum())
        if dd < _MIN_DRIVE_DAYS:
            continue
        rate, rlo, rhi = _rate_ci(ev, dd)
        by_model[str(m)] = {
            "drive_days": dd, "events": ev,
            "rate_per_1k_drive_days": round(rate, 3),
            "ci95": [round(rlo, 3), round(rhi, 3)],
            "median_age_days": round(float(sub["age"].median()), 1),
        }
    print("\nper model:")
    for m, v in sorted(by_model.items(), key=lambda kv: -kv[1]["rate_per_1k_drive_days"]):
        print(f"  {m:<14} {v['rate_per_1k_drive_days']:>6.2f} per 1k  "
              f"(n={v['drive_days']:,} drive-days, median age {v['median_age_days']:.0f}d)")

    spread = None
    if len(by_model) >= 2:
        rates = [v["rate_per_1k_drive_days"] for v in by_model.values()]
        spread = round(max(rates) / min(rates), 1) if min(rates) > 0 else None
        print(f"\n  spread between models: {spread}x")

    payload = {
        "source": "Alibaba Fail-Slow Detection Open Dataset (Tianchi 144479)",
        "url": "https://tianchi.aliyun.com/dataset/144479",
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "method": "Empirical hazard: fail-slow events per 1,000 drive-days, bucketed "
                  "by drive age. Non-parametric and confined to the observation "
                  "window. See the module docstring for why a Weibull fit was "
                  "attempted, rejected, and is not reported.",
        "event_definition": f"a drive-day flagged fail-slow at the {EVENT} threshold",
        "n_drives": int(n_drives),
        "drive_days": int(total_days),
        "events": total_events,
        "overall_rate_per_1k_drive_days": round(1000 * total_events / total_days, 3),
        "age_range_days": [float(df["age"].min()), float(df["age"].max())],
        "bands": rows,
        "trend": {"verdict": verdict, "note": note,
                  "spearman_rho": None if rho_s is None else round(float(rho_s), 3),
                  "p_value": None if p_s is None else float(p_s)},
        "by_model": by_model,
        "model_spread_x": spread,
        "caveats": [
            "Enterprise datacenter SSDs under datacenter workloads. A consumer "
            "laptop SSD is a different population -- what might transfer is the "
            "SHAPE of the age relationship, never the absolute rates.",
            "The event is fail-SLOW, not failure: a drive persistently far slower "
            "than its peers, degraded rather than dead.",
            "The window is about sixteen weeks and the median drive is seen for "
            "four days of its own age, so this describes rates WITHIN the observed "
            "age range and supports no extrapolation beyond it.",
            "Bands marked thin hold under 500 drive-days; their rates are not "
            "estimates worth reading.",
        ],
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
