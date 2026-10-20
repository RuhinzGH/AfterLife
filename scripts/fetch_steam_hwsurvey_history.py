r"""Download the Steam Hardware Survey history, 2008 onwards (S2-15).

Writes data/raw/steam_hwsurvey_history.csv, which scripts/export_decay_series.py
turns into app_data/decay.json (how long an unsupported Windows version stays
in use after its end of support). Source: the community archive of Valve's
monthly survey at github.com/jdegene/steamHWsurvey.

    venv\Scripts\python scripts\fetch_steam_hwsurvey_history.py
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "steam_hwsurvey_history.csv"
URL = "https://raw.githubusercontent.com/jdegene/steamHWsurvey/master/shs.csv"
UA = {"User-Agent": "AfterLife-research/1.0 (course project)"}


def main() -> None:
    r = requests.get(URL, headers=UA, timeout=180)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), low_memory=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(df):,} rows; columns {list(df.columns)})")


if __name__ == "__main__":
    main()
