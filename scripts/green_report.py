"""Compare docs/green/before.json and after.json into docs/green/README.md (S3-05).

    venv\\Scripts\\python scripts\\green_report.py
"""
from __future__ import annotations

import json
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "docs" / "green"


def main() -> None:
    b = json.loads((D / "before.json").read_text(encoding="utf-8"))
    a = json.loads((D / "after.json").read_text(encoding="utf-8"))

    def row(label, get, unit, lower_is_better=True):
        x, y = get(b), get(a)
        if x in (None, 0) or y is None:
            change = "n/a"
        else:
            pct = (y - x) / x * 100
            change = f"{pct:+.0f}%" if abs(pct) >= 0.5 else "same"
        return f"| {label} | {x} {unit} | {y} {unit} | {change} |"

    s = lambda k, f: (lambda r: r["server"][k][f])
    lines = [
        "# Green computing: before vs after (S3-05)",
        "",
        f"Same script (`scripts/measure_green.py`), same laptop ({a['machine']['cpu']}, "
        f"{a['machine']['ram_gb']} GB RAM), measured {a['measured']}.",
        f"**Before** = the CIA-3 submission (commit `{b['commit']}`, 11 Oct 2026). **After** = commit `{a['commit']}`.",
        "Each server figure is the median of 30 requests after a warm-up; page figures are the median of 5 fresh loads in headless Chrome with the cache off.",
        "",
        "| Measure | Before | After | Change |",
        "|---|---|---|---|",
        row("Model file", lambda r: r["model_file_mb"], "MB"),
        row("Server memory, model loaded", lambda r: r["server"]["rss_mb_model_loaded"], "MB"),
        row("Server memory, after 90 requests", lambda r: r["server"]["rss_mb_after_requests"], "MB"),
        row("Signed passport with model prediction: time", s("scan_passport", "median_ms"), "ms"),
        row("Signed passport with model prediction: CPU", s("scan_passport", "cpu_ms_per_request"), "ms"),
        row("Assessment: time", s("assess", "median_ms"), "ms"),
        row("Research data: time", s("findings", "median_ms"), "ms"),
        row("First-page JavaScript (gzip)", lambda r: r["website_build"]["first_page_js_kb_gzip"], "kB"),
        row("First-page CSS (gzip)", lambda r: r["website_build"]["first_page_css_kb_gzip"], "kB"),
        row("Home page transferred", lambda r: r["website_load"]["home_transfer_kb_median"], "kB"),
        row("Home page load time (local)", lambda r: r["website_load"]["home_load_ms_median"], "ms"),
        row("Whole build on disk (incl. on-demand parts)", lambda r: r["website_build"]["build_total_kb"], "kB"),
        row("Estimated energy per 1,000 passports", lambda r: r["energy_estimate"]["scan_passport"]["wh_per_1000"], "Wh"),
        row("Estimated carbon per 1,000 passports", lambda r: r["energy_estimate"]["scan_passport"]["g_co2e_per_1000"], "g CO2e"),
        "",
        "## Reading it",
        "",
        "- **The model** went from 300 trees to 150, saved compressed: a much smaller file and about a third of the CPU per "
        "prediction, with the same end-of-life recall and calibration (`app_data/model_size_experiment.json`).",
        "- **The first page stayed the same size** although about fifteen features were added, because new pages, the sign-in "
        "window, the results page and the PDF reader load only when used.",
        "- **The whole build is bigger on disk** mainly because of the PDF reader added for verifying PDF passports "
        "(about 1.4 MB). It is downloaded only by someone who uploads a PDF, so it costs nothing for everyone else.",
        "- **The assessment response grew** (more cards: usage fit, repair outlook, rights, carbon range) for the same time and CPU.",
        "",
        f"**Energy method (an estimate, not a meter reading):** {a['energy_estimate']['method']} "
        "Absolute values are tiny because each request is short; the useful number is the relative change.",
    ]
    (D / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
