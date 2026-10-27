"""Measure one version of AfterLife for the green before/after study (S3-05).

    set PYTHONPATH=.
    venv\\Scripts\\python scripts\\measure_green.py --label after --root .
    venv\\Scripts\\python scripts\\measure_green.py --label before --root <checkout of the CIA-3 commit>

Run both on the same machine, one after the other, with nothing else heavy
running. Each run starts that version's own API server and website build and
measures, the same way for both:

  server   memory after start-up and after the model has loaded (RSS);
           per request: median wall time, CPU seconds and response size, for an
           instant-scan passport (runs the model), an assessment, and the
           research data
  model    file size on disk
  website  production build: first-page JavaScript and CSS (gzip), and in
           headless Chrome the bytes transferred and the load time of the home
           page (median of 5 fresh loads)

Energy is ESTIMATED, not metered: server CPU seconds x the power of one busy
core, taken as the CPU's rated TDP divided by its physical cores (--tdp,
--cores; this laptop: Intel i7-1165G7, 28 W, 4 cores). Carbon uses the
assessment's own grid figure for India. Both are labelled as estimates in the
output, with the formula.

Writes docs/green/<label>.json; scripts/green_report.py compares the two.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent.parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
N = 30

SCAN = {
    "os": "Windows 11 (build 15.0.0)", "os_family": "Windows", "architecture": "x86 64",
    "gpu": "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "cpu_cores": 8, "ram_gb": 8, "screen": "1920x1080", "timezone": "Asia/Kolkata", "source": "browser-scan",
    "device_age": 6, "product_category": "Laptop", "problem": "battery drains fast",
}
ASSESS = {"eol_risk": 0.18, "age_years": 6, "fault_described": True, "make_model": SCAN["os"], "os": SCAN["os"],
          "product_category": "Laptop", "timezone": "Asia/Kolkata"}


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def call(url: str, body: dict | None = None) -> tuple[float, int]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    t = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        n = len(r.read())
    return time.perf_counter() - t, n


def server_tree_cpu(p: psutil.Process) -> float:
    procs = [p] + p.children(recursive=True)
    return sum(sum(x.cpu_times()[:2]) for x in procs if x.is_running())


def server_tree_rss(p: psutil.Process) -> int:
    procs = [p] + p.children(recursive=True)
    return sum(x.memory_info().rss for x in procs if x.is_running())


def measure_server(root: Path, port: int) -> dict:
    env = {**os.environ, "PYTHONPATH": str(root)}
    env.pop("REDIS_URL", None)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(port), "--log-level", "warning"],
                            cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ps = psutil.Process(proc.pid)
    base = f"http://127.0.0.1:{port}/api"
    try:
        for _ in range(120):
            try:
                call(base + "/health"); break
            except Exception:
                time.sleep(0.5)
        time.sleep(1)
        out = {"rss_mb_idle": round(server_tree_rss(ps) / 2**20, 1)}
        call(base + "/scan-passport", SCAN)                       # first call loads the model
        out["rss_mb_model_loaded"] = round(server_tree_rss(ps) / 2**20, 1)
        endpoints = {
            "scan_passport": ("/scan-passport", SCAN),
            "assess": ("/assess", ASSESS),
            "findings": ("/findings", None),
        }
        for name, (path, body) in endpoints.items():
            call(base + path, body)                                # warm
            cpu0 = server_tree_cpu(ps)
            times, sizes = [], []
            for _ in range(N):
                t, n = call(base + path, body)
                times.append(t); sizes.append(n)
            cpu = server_tree_cpu(ps) - cpu0
            out[name] = {"median_ms": round(statistics.median(times) * 1000, 1),
                         "cpu_ms_per_request": round(cpu / N * 1000, 1),
                         "response_kb": round(statistics.median(sizes) / 1024, 1)}
        out["rss_mb_after_requests"] = round(server_tree_rss(ps) / 2**20, 1)
        return out
    finally:
        for c in ps.children(recursive=True):
            c.kill()
        proc.kill()


def gz(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), 9))


def build_frontend(root: Path) -> dict:
    fe = root / "frontend"
    subprocess.run("npm run build", cwd=fe, shell=True, check=True, capture_output=True)
    dist = fe / "dist"
    html = (dist / "index.html").read_text(encoding="utf-8")
    first = re.findall(r'(?:src|href)="/?(assets/[^"]+\.(?:js|css))"', html)
    js = [dist / a for a in first if a.endswith(".js")]
    css = [dist / a for a in first if a.endswith(".css")]
    all_files = [f for f in dist.rglob("*") if f.is_file()]
    return {
        "first_page_js_kb_gzip": round(sum(gz(f) for f in js) / 1024, 1),
        "first_page_css_kb_gzip": round(sum(gz(f) for f in css) / 1024, 1),
        "build_total_kb": round(sum(f.stat().st_size for f in all_files) / 1024, 1),
        "build_files": len(all_files),
    }


async def page_load(url: str, runs: int = 5) -> dict:
    import websockets
    loads, bytes_ = [], []
    for _ in range(runs):
        port = free_port()
        chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={port}",
                                   f"--user-data-dir={tempfile.mkdtemp()}", "--disable-gpu", "about:blank"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(60):
                try:
                    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json")); break
                except Exception:
                    time.sleep(0.25)
            ws_url = [t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"]
            async with websockets.connect(ws_url, max_size=2**26) as ws:
                n = 0
                total = 0
                done = asyncio.Event()

                async def cmd(m, **p):
                    nonlocal n; n += 1
                    await ws.send(json.dumps({"id": n, "method": m, "params": p}))
                    return n

                await cmd("Network.enable"); await cmd("Page.enable")
                await cmd("Network.setCacheDisabled", cacheDisabled=True)
                t0 = time.perf_counter()
                await cmd("Page.navigate", url=url)
                load_t = None
                deadline = time.perf_counter() + 60
                while time.perf_counter() < deadline:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
                    except asyncio.TimeoutError:
                        if load_t is not None:
                            break
                        continue
                    if msg.get("method") == "Network.loadingFinished":
                        total += msg["params"].get("encodedDataLength", 0)
                    if msg.get("method") == "Page.loadEventFired" and load_t is None:
                        load_t = time.perf_counter() - t0
                loads.append(load_t or float("nan")); bytes_.append(total)
        finally:
            chrome.kill()
    return {"home_load_ms_median": round(statistics.median(loads) * 1000), "home_transfer_kb_median": round(statistics.median(bytes_) / 1024, 1)}


def measure_site(root: Path, api_port: int) -> dict:
    """Serve the build with vite preview (it proxies /api to localhost:8000) and load the home page."""
    env = {**os.environ, "PYTHONPATH": str(root)}
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--port", "8000", "--log-level", "warning"],
                           cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    web_port = free_port()
    web = subprocess.Popen(f"npx vite preview --port {web_port} --strictPort", cwd=root / "frontend", shell=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                call("http://127.0.0.1:8000/api/health"); urllib.request.urlopen(f"http://127.0.0.1:{web_port}/", timeout=5); break
            except Exception:
                time.sleep(0.5)
        return asyncio.run(page_load(f"http://127.0.0.1:{web_port}/"))
    finally:
        for p in (api, web):
            try:
                for c in psutil.Process(p.pid).children(recursive=True):
                    c.kill()
            except psutil.Error:
                pass
            p.kill()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--root", default=str(HERE))
    ap.add_argument("--tdp", type=float, default=28.0, help="CPU rated power, W (i7-1165G7: 28)")
    ap.add_argument("--cores", type=int, default=4, help="physical cores (i7-1165G7: 4)")
    ap.add_argument("--grid", type=float, default=670.0, help="gCO2e per kWh (India, as on the site)")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    model = root / "models" / "lifecycle_model.joblib"
    result = {
        "label": args.label,
        "commit": subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "measured": time.strftime("%Y-%m-%d"),
        "machine": {"cpu": "Intel Core i7-1165G7 (this laptop)", "tdp_w": args.tdp, "physical_cores": args.cores,
                    "logical_cpus": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1)},
        "model_file_mb": round(model.stat().st_size / 2**20, 2) if model.exists() else None,
        "server": measure_server(root, free_port()),
        "website_build": build_frontend(root),
    }
    result["website_load"] = measure_site(root, 8000)

    w_per_core = args.tdp / args.cores
    per_k = {}
    for name in ("scan_passport", "assess"):
        cpu_s = result["server"][name]["cpu_ms_per_request"] / 1000
        wh = cpu_s * w_per_core / 3600 * 1000            # Wh per 1,000 requests
        per_k[name] = {"wh_per_1000": round(wh, 3), "g_co2e_per_1000": round(wh / 1000 * args.grid, 3)}
    result["energy_estimate"] = {
        "method": f"server CPU seconds x {w_per_core:.1f} W per busy core (TDP {args.tdp:g} W / {args.cores} cores); "
                  f"carbon at {args.grid:g} gCO2e/kWh. An estimate from measured CPU time, not a meter reading.",
        **per_k,
    }
    out = HERE / "docs" / "green" / f"{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
