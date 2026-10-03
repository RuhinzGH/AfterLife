"""Replicate the fail-slow analysis from Lu et al., USENIX ATC 2022 (§5).

Fail-slow is the failure mode SMART cannot see: a drive that keeps working but
degrades to a fraction of its rated speed. The source paper found it affects
NVMe SSDs ~6x more than HDDs, and -- their Finding 9 -- that it does NOT
correlate with any SMART attribute. That matters directly to Afterlife, whose
storage assessment is entirely SMART-based: it establishes a real ceiling on
what a one-shot health scan can ever detect.

METHOD (paper §5.1), reimplemented:
  1. Relative latency RL[k,i] = latency[k,i] / median(latency[all 12 drives, i]).
     Comparing a drive against its own node-peers at the same instant controls
     for the node simply being busy, which a raw latency threshold cannot.
  2. A fail-slow EVENT is a window where mean(RL) >= 2 (drive is 2x slower than
     its peers) sustained for >= 5/15/30/60 minutes (20/60/120/240 records at
     one record per 15s).
  3. A drive is FAIL-SLOW if its median latency is a distribution outlier
     (> Q3 + 2*IQR) AND it has at least one event.

TWO DELIBERATE DEVIATIONS, both of which inflate our numbers vs the paper's:
  - The paper computes the outlier threshold per CLUSTER. Cluster IDs are not in
    the public release, so workload is used as the proxy (the paper notes each
    service runs on dedicated clusters, making this the closest available proxy).
  - The paper excludes drives under heavy traffic using IOPS/throughput to avoid
    false positives. The public release contains latency only, so that filter
    cannot be applied and some genuinely-busy drives will be counted as slow.
  Our rates should therefore read as an UPPER BOUND, not a reproduction.

Run:  venv/Scripts/python.exe scripts/analyze_failslow.py
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ZIP = ROOT / "data" / "raw" / "alibaba_nvme_ssd_hdd_latency.zip"
OUT = ROOT / "app_data"

RECORD_SECONDS = 15
SPANS = {"5min": 20, "15min": 60, "30min": 120, "60min": 240}
SLOWDOWN_DEGREE = 2.0


def detect_events(rl: np.ndarray) -> dict[str, bool]:
    """Does this drive have a sustained >=2x slowdown at each duration?

    Uses a cumulative-sum sliding window rather than a rolling mean: at 20k files
    x 12 drives x 4 span lengths the naive version dominates total runtime.
    """
    out = {}
    n = len(rl)
    csum = np.concatenate([[0.0], np.nancumsum(rl)])
    for name, w in SPANS.items():
        if n < w:
            out[name] = False
            continue
        means = (csum[w:] - csum[:-w]) / w
        out[name] = bool(np.any(means >= SLOWDOWN_DEGREE))
    return out


def process_file(fh, drive_count_hint: int) -> list[dict]:
    df = pd.read_csv(fh)
    if "ts" not in df.columns or len(df) < 20:
        return []
    disk_cols = [c for c in df.columns if c != "ts"]
    if not disk_cols:
        return []

    vals = df[disk_cols].to_numpy(dtype=float)  # (records, drives)
    # Peer median per timestamp. A node with a single reporting drive has no peer
    # group, so relative latency is undefined and the node is skipped.
    if vals.shape[1] < 2:
        return []
    peer_med = np.nanmedian(vals, axis=1)
    # Guard against a whole-node stall producing a zero/NaN denominator, which
    # would manufacture infinite slowdown ratios out of nothing.
    peer_med = np.where((peer_med > 0) & np.isfinite(peer_med), peer_med, np.nan)

    rows = []
    for j, col in enumerate(disk_cols):
        series = vals[:, j]
        if np.all(np.isnan(series)):
            continue
        rl = series / peer_med
        # Gaps are neutral (RL=1) rather than dropped: dropping them would shrink
        # the window and let a brief spike masquerade as a sustained event.
        rl = np.where(np.isfinite(rl), rl, 1.0)
        ev = detect_events(rl)
        rows.append({
            "drive": col,
            "median_latency_us": float(np.nanmedian(series)),
            "mean_rl": float(np.nanmean(rl)),
            **{f"event_{k}": v for k, v in ev.items()},
        })
    return rows


def analyze(kind: str, meta: pd.DataFrame, zf: zipfile.ZipFile) -> pd.DataFrame:
    prefix = f"SSD_HDD_WriteLatency/{kind}_data/"
    records = []
    total = len(meta)
    for n, (_, m) in enumerate(meta.iterrows(), 1):
        name = f"{prefix}{m['index']}.csv"
        try:
            with zf.open(name) as fh:
                rows = process_file(fh, m.get("drive_count", 12))
        except KeyError:
            continue
        for r in rows:
            r.update({"node_id": m["node_id"], "model": m.get("model"),
                      "workload": m.get("workload"), "date": m.get("date"),
                      "age": m.get("age"), "usage": m.get("usage")})
            records.append(r)
        if n % 2000 == 0:
            print(f"  {kind}: {n:,}/{total:,} node-days")
    return pd.DataFrame(records)


def flag_failslow(df: pd.DataFrame) -> pd.DataFrame:
    """Outlier-latency test, applied within workload as the cluster proxy."""
    df = df.copy()
    df["workload_key"] = df["workload"].fillna("unknown")
    df["latency_outlier"] = False
    for wl, grp in df.groupby("workload_key"):
        q1, q3 = grp["median_latency_us"].quantile([0.25, 0.75])
        bar = q3 + 2 * (q3 - q1)
        df.loc[grp.index, "latency_outlier"] = grp["median_latency_us"] > bar
    for span in SPANS:
        df[f"failslow_{span}"] = df["latency_outlier"] & df[f"event_{span}"]
    return df


def summarize(df: pd.DataFrame, label: str) -> dict:
    # A drive is counted once, not once per day it was observed.
    per_drive = df.groupby(["node_id", "drive"]).agg(
        {**{f"failslow_{s}": "any" for s in SPANS},
         "model": "first", "workload": "first", "age": "max", "usage": "max"}).reset_index()
    out = {"label": label, "drives": int(len(per_drive))}
    print(f"\n{'='*74}\n{label}: {len(per_drive):,} distinct drives "
          f"({len(df):,} drive-days)")
    for s in SPANS:
        rate = per_drive[f"failslow_{s}"].mean()
        out[f"slow_drive_pct_{s}"] = round(100 * rate, 3)
        print(f"  fail-slow @ {s:>6}: {100*rate:6.2f}%  ({per_drive[f'failslow_{s}'].sum():,} drives)")
    return out, per_drive


def breakdown(per_drive: pd.DataFrame, col: str, span: str = "5min") -> pd.DataFrame:
    g = per_drive.groupby(col).agg(
        drives=("drive", "size"), slow=(f"failslow_{span}", "sum"))
    g["slow_pct"] = (100 * g["slow"] / g["drives"]).round(2)
    return g.sort_values("slow_pct", ascending=False)


CACHE = ROOT / "data" / "derived"


def load_or_build(kind: str, meta: pd.DataFrame, zf: zipfile.ZipFile) -> pd.DataFrame:
    """Cache the expensive per-drive-day pass so thresholds can be re-swept cheaply."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"failslow_{kind}_drivedays.parquet"
    if path.exists():
        print(f"  {kind}: using cached {path.name}")
        return pd.read_parquet(path)
    df = analyze(kind, meta, zf)
    df.to_parquet(path, index=False)
    return df


def sweep_thresholds(ssd_raw: pd.DataFrame, hdd_raw: pd.DataFrame) -> None:
    """Test whether the SSD:HDD disagreement is threshold-driven.

    The paper's outlier bar is far stricter than Q3+2*IQR -- it describes marking
    drives above the "top 0.04% latency variances". If our inverted ratio is an
    artifact of a permissive threshold letting merely-busy HDDs through (rather
    than a real contradiction), tightening the bar should move the ratio back
    toward the published direction. If it does not move, the disagreement is real
    and the caveat is not a sufficient explanation.
    """
    print(f"\n{'='*74}\nTHRESHOLD SENSITIVITY -- is the SSD:HDD inversion an artifact?")
    print(f"{'outlier rule':<22}{'SSD %':>9}{'HDD %':>9}{'ratio':>9}")
    rules = [("Q3 + 2*IQR", None), ("p99.0", 99.0), ("p99.5", 99.5),
             ("p99.9", 99.9), ("p99.96 (paper)", 99.96)]
    for label, pctile in rules:
        rates = {}
        for kind, raw in (("SSD", ssd_raw), ("HDD", hdd_raw)):
            df = raw.copy()
            df["workload_key"] = df["workload"].fillna("unknown")
            df["latency_outlier"] = False
            for _, grp in df.groupby("workload_key"):
                if pctile is None:
                    q1, q3 = grp["median_latency_us"].quantile([0.25, 0.75])
                    bar = q3 + 2 * (q3 - q1)
                else:
                    bar = np.percentile(grp["median_latency_us"].dropna(), pctile)
                df.loc[grp.index, "latency_outlier"] = grp["median_latency_us"] > bar
            df["fs"] = df["latency_outlier"] & df["event_5min"]
            per_drive = df.groupby(["node_id", "drive"])["fs"].any()
            rates[kind] = 100 * per_drive.mean()
        ratio = rates["SSD"] / rates["HDD"] if rates["HDD"] else float("nan")
        print(f"{label:<22}{rates['SSD']:>9.2f}{rates['HDD']:>9.2f}{ratio:>8.2f}x")
    print("paper's published figures:    1.41     0.20    6.05x")


if __name__ == "__main__":
    zf = zipfile.ZipFile(ZIP)
    with zf.open("SSD_HDD_WriteLatency/ssd_meta.csv") as fh:
        ssd_meta = pd.read_csv(fh)
    with zf.open("SSD_HDD_WriteLatency/hdd_meta.csv") as fh:
        hdd_meta = pd.read_csv(fh)

    print(f"SSD node-days: {len(ssd_meta):,}   HDD node-days: {len(hdd_meta):,}")
    ssd_raw = load_or_build("ssd", ssd_meta, zf)
    hdd_raw = load_or_build("hdd", hdd_meta, zf)
    sweep_thresholds(ssd_raw, hdd_raw)
    ssd = flag_failslow(ssd_raw)
    hdd = flag_failslow(hdd_raw)

    ssd_sum, ssd_drives = summarize(ssd, "NVMe SSD")
    hdd_sum, hdd_drives = summarize(hdd, "SATA HDD")

    ratio = {s: (ssd_sum[f"slow_drive_pct_{s}"] / hdd_sum[f"slow_drive_pct_{s}"]
                 if hdd_sum[f"slow_drive_pct_{s}"] else None) for s in SPANS}
    print("\nSSD : HDD fail-slow ratio (paper reports 6.05x at 5min, 51x at 60min):")
    for s, r in ratio.items():
        print(f"  {s:>6}: {r:.2f}x" if r else f"  {s:>6}: n/a")

    print("\n--- SSD fail-slow by drive model (5min) ---")
    print(breakdown(ssd_drives, "model").to_string())
    print("\n--- SSD fail-slow by workload (5min) ---")
    print(breakdown(ssd_drives, "workload").to_string())
    print("\n--- SSD fail-slow by P/E usage bucket (5min) ---")
    print(breakdown(ssd_drives, "usage").to_string())

    # Age is reported per node in days; bucket it to test the paper's Finding 7
    # that fail-slow correlates with age only past ~41 months (~1250 days).
    ssd_drives["age_months"] = (ssd_drives["age"] / 30.4).round()
    bins = [0, 12, 24, 36, 41, 60, 200]
    ssd_drives["age_band"] = pd.cut(ssd_drives["age_months"], bins=bins)
    print("\n--- SSD fail-slow by age band, months (5min) ---")
    print(breakdown(ssd_drives, "age_band").to_string())

    OUT.mkdir(exist_ok=True)
    (OUT / "failslow_results.json").write_text(json.dumps({
        "source": "Lu et al., NVMe SSD Failures in the Field, USENIX ATC 2022 (CC BY-NC-SA 4.0)",
        "caveats": ["workload used as cluster proxy (cluster IDs not in public release)",
                    "no IOPS/throughput filter available -> rates are an upper bound"],
        "ssd": ssd_sum, "hdd": hdd_sum,
        "ssd_hdd_ratio": {k: (round(v, 2) if v else None) for k, v in ratio.items()},
        "by_model": breakdown(ssd_drives, "model").reset_index().to_dict("records"),
        "by_workload": breakdown(ssd_drives, "workload").reset_index().to_dict("records"),
    }, indent=2, default=str))
    print(f"\nwrote {OUT / 'failslow_results.json'}")
