# Re-running the data pipeline

Every figure on the site is read from a file in `app_data/` or `models/`, and
every one of those files is made by a script in `scripts/` from a public source.
This page lists the order to run them. Raw downloads go to `data/raw/` and
intermediate files to `data/derived/`; both folders are git-ignored, so a fresh
clone starts empty and the scripts fill them.

Run everything from the repository root with the project's Python:

```
set PYTHONPATH=.
venv\Scripts\python scripts\<script>.py
```

## 1. Download the raw data

| Step | Script | Makes | Source |
|---|---|---|---|
| 1 | `fetch_openrepair.py` | `data/raw/openrepair_202507.csv` | Open Repair Alliance, July 2025 aggregate, pinned to commit `4a5209d` of github.com/openrepair/data (the file was removed from the main branch on 12 Oct 2026) |
| 2 | `pull_eol.py` | `data/raw/external/endoflife_support_horizons.csv` | endoflife.date API |
| 3 | `fetch_steam_hwsurvey_history.py` | `data/raw/steam_hwsurvey_history.csv` | Steam Hardware Survey archive (github.com/jdegene/steamHWsurvey) |
| 4 | `fetch_steam_requirements.py` | `data/raw/steam_requirements.json` | Steam store API (titles from SteamSpy top-100 lists) |
| 5 | `fetch_blender_opendata.py` | `data/raw/blender_opendata.json` | Blender Open Data |
| 6 | `fetch_failslow_latency.py <file>` | `data/raw/alibaba_nvme_ssd_hdd_latency.zip` | Lu et al., USENIX ATC 2022 release. **Manual:** download needs a sign-in on OpenI (openi.pcl.ac.cn/Cx/NVMe-SSD-Open-Dataset); the script checks the published MD5 and copies it into place |
| 7 | `pull_eprel.py` | `app_data/eprel_devices.json` | EU EPREL registry; needs a free `EPREL_API_KEY` in `.env` |

Grid carbon intensity (Our World in Data), manufacturer carbon declarations
(Boavizta), CVEs (NVD), exploited CVEs (CISA KEV) and exploit forecasts (EPSS)
are downloaded by the build scripts in step 2 themselves.

## 2. Build the files the site reads

| Step | Script | Reads | Makes |
|---|---|---|---|
| 8 | `build_device_support.py` | step 2 | `app_data/device_support.json` (support end dates) |
| 9 | `build_geo_lookup.py` | step 1 | `app_data/geo_lookup.json` (time zone to country, records per country) |
| 10 | `build_grid_intensity.py` | Our World in Data, step 9 | `app_data/grid_intensity.json` |
| 11 | `build_embodied_carbon.py` | Boavizta | `app_data/embodied_carbon.json` |
| 12 | `build_repair_evidence.py` | step 1 | `app_data/repair_evidence.json` (repair rates per fault) |
| 13 | `train_lifecycle.py` | step 1 | `models/lifecycle_model.joblib`, `app_data/lifecycle_metrics.json` |
| 14 | `measure_model_size.py` | step 1 | `app_data/model_size_experiment.json` (why 150 trees; run before 13 to re-check the choice) |
| 15 | `research_experiment.py` | step 1 | `app_data/research_results.json` |
| 16 | `build_cve_corpus.py --major 10` and `--major 11` | NVD | `app_data/win10_cve_classified.csv`, `win11_...` |
| 17 | `enrich_cve_kev.py`, then `enrich_cve_epss.py` | step 16, CISA, FIRST | adds exploited / forecast columns; `kev_summary.json`, `epss_summary.json` |
| 18 | `export_decay_series.py` | step 3 | `app_data/decay.json` (how long unsupported Windows stays in use) |
| 19 | `analyze_failslow.py`, then `survival_failslow.py` | step 6 | `app_data/failslow_results.json`, `survival_failslow.json` |
| 20 | `build_persona_tiers.py` | step 5 | `models/persona_tiers.json` (graphics tiers) |
| 21 | `fit_requirement_growth.py` | step 4 | `models/requirement_growth.json` (requirement growth per year) |
| 22 | `eda_eprel.py` | step 7 | `app_data/eprel_eda.json` (EU grade spread) |

## 3. Check

```
venv\Scripts\python -m pytest
```

Several tests re-derive published figures from these files (for example the
requirement-growth fit, the assumptions table and the sensitivity analysis), so
a pipeline run that changes a figure shows up as a failing test rather than a
silently different page.

## What may differ on a re-run

Sources that are refreshed upstream (endoflife.date, NVD, KEV, EPSS, Steam,
EPREL) will give newer figures than the committed files. The Open Repair data
is pinned to a commit, so the model and the repair figures reproduce exactly
(23,748 records from 8 data providers).
