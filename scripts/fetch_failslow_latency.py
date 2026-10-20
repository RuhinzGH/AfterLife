r"""Put the NVMe/HDD write-latency dataset where the fail-slow analysis reads it (S2-15).

scripts/analyze_failslow.py replicates the fail-slow analysis of Lu et al.,
"NVMe SSD Failures in the Field: the Fail-Stop and the Fail-Slow" (USENIX ATC
2022), on the authors' public release. That release can only be downloaded
after signing in, so this step is manual:

  1. Sign in and download ssd_hdd_latency.zip from the dataset page:
       https://openi.pcl.ac.cn/Cx/NVMe-SSD-Open-Dataset
     (also listed on Alibaba Tianchi, dataset 128972).
  2. Run this script with the path of the downloaded file:
       venv\Scripts\python scripts\fetch_failslow_latency.py C:\path\to\ssd_hdd_latency.zip

It checks the file's MD5 against the checksum published on the dataset page,
checks the zip holds the folders the analysis reads, and copies it to
data/raw/alibaba_nvme_ssd_hdd_latency.zip.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data" / "raw" / "alibaba_nvme_ssd_hdd_latency.zip"
PUBLISHED_MD5 = "fd1e2475750918ff3be85a4d0351d771"     # from the OpenI dataset page
NEEDED = ("SSD_HDD_WriteLatency/ssd_meta.csv", "SSD_HDD_WriteLatency/hdd_meta.csv")


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    src = Path(sys.argv[1])
    digest = md5(src)
    print(f"MD5 {digest} ({'matches' if digest == PUBLISHED_MD5 else 'DOES NOT match'} the published checksum)")
    with zipfile.ZipFile(src) as zf:
        missing = [n for n in NEEDED if n not in zf.namelist()]
    if missing:
        raise SystemExit(f"not the expected archive: missing {missing}")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, DEST)
    print(f"copied to {DEST}; next: venv\\Scripts\\python scripts\\analyze_failslow.py")


if __name__ == "__main__":
    main()
