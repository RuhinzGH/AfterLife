"""Afterlife API — FastAPI backend.

Serves the trained ML lifecycle model, the signed device passport, the passport
verifier, and the research findings the frontend renders. Run:

    venv/Scripts/uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import re
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from afterlife.passport import build_scan_passport, verify_payload
from afterlife.predict import predict_lifecycle

APP_DATA = ROOT / "app_data"

app = FastAPI(title="Afterlife API", version="1.0.0",
              description="Device lifecycle intelligence — ML, passports, findings.")

_ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173",
                    *[o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]]

# Every Vercel deploy of this project (production and each preview build) gets a
# distinct afterlife-*/frontend-* origin. Enumerating them in CORS_ORIGINS is a
# losing game (a new one every deploy), so match the pattern instead. Scoped to
# our own prefixes, not all of *.vercel.app.
import re as _re
_ALLOWED_ORIGIN_REGEX = r"https://(afterlife|frontend)[a-z0-9-]*\.vercel\.app"
_origin_re = _re.compile(_ALLOWED_ORIGIN_REGEX)


def _origin_allowed(origin: str | None) -> bool:
    return bool(origin) and (origin in _ALLOWED_ORIGINS or bool(_origin_re.fullmatch(origin)))


app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=_ALLOWED_ORIGIN_REGEX,
    allow_methods=["*"], allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """An uncaught exception's default 500 response bypasses CORSMiddleware, so the
    browser sees a bare network failure ("Failed to fetch") instead of a readable
    error. Re-attaching the CORS header here turns any future crash into a visible error
    instead of a silent, undebuggable one."""
    print(f"Unhandled error on {request.url.path}: {type(exc).__name__}: {exc}")
    origin = request.headers.get("origin")
    headers = {"Access-Control-Allow-Origin": origin} if _origin_allowed(origin) else {}
    return JSONResponse(status_code=500, content={"detail": "internal server error"}, headers=headers)


# ----------------------------------------------------------- security headers
# This API serves only JSON -- never HTML or scripts -- so a
# maximally strict CSP is safe here and turns the API origin into dead ground for
# anyone trying to host injected content on it. The SPA sets its own (looser) CSP
# at the edge (vercel.json); this hardens the API domain itself.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    return resp


# ---------------------------------------------------------------- schemas
class PredictIn(BaseModel):
    product_category: str = Field(examples=["Laptop"])
    brand: str = "Unknown"
    country: str = "Unknown"
    device_age: float | None = Field(default=None, examples=[6])
    problem: str = Field(default="", examples=["won't power on, no charge light"])
    event_year: int = 2026


class VerifyIn(BaseModel):
    passport: dict


def _load_json(name: str) -> dict:
    p = APP_DATA / name
    return json.loads(p.read_text()) if p.exists() else {}


# ---------------------------------------------------------------- routes
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "afterlife"}


@app.get("/api/esu")
def esu_programmes() -> dict:
    """Both Windows 10 Extended Security Updates programmes, as they stand today.

    Read straight from afterlife.esu, the same table the score uses, so the
    countdown page cannot show a different date from the one the assessment
    applies.
    """
    from afterlife import esu
    return {
        "as_of": __import__("datetime").date.today().isoformat(),
        "consumer": esu.describe(esu.PROGRAMMES["windows10"]),
        "commercial": esu.describe(esu.PROGRAMMES["windows10-commercial"]),
    }


@app.get("/api/grid-countries")
def grid_countries() -> dict:
    """The countries the carbon calculator can price, and the device classes it
    holds declared embodied-carbon distributions for."""
    from afterlife import embodied_carbon, grid
    g = grid._load()
    countries = sorted(
        ({"code": k, "name": v["name"], "gco2_kwh": v["gco2_kwh"], "year": v["year"]}
         for k, v in (g.get("countries") or {}).items()),
        key=lambda c: c["name"])
    classes = embodied_carbon._load().get("classes", {})
    return {
        "countries": countries,
        "world": g.get("world"),
        "source": g.get("source"),
        "device_classes": [{"name": k, "n": v["n"], "median_kg": v["median_kg"],
                            "p25_kg": v["p25_kg"], "p75_kg": v["p75_kg"]}
                           for k, v in classes.items()],
    }


@app.get("/api/carbon-calc")
def carbon_calc(country: str | None = None, device_class: str = "Laptop",
                old_tdp_w: float = 45.0, new_tdp_w: float = 28.0) -> dict:
    """Keep vs replace, by carbon, for a device class on a country's grid.

    Embodied carbon is the class median from manufacturer declarations (with
    its interquartile range, so the spread is visible); the break-even maths is
    grid.break_even, the same function the assessment uses. An unknown class is
    a 404 rather than a silent default: there is no honest median for it.
    """
    from afterlife import embodied_carbon, grid
    if not (1 <= old_tdp_w <= 500 and 1 <= new_tdp_w <= 500):
        raise HTTPException(400, "power draw must be between 1 and 500 W")
    stats = embodied_carbon.class_estimate(device_class)
    if not stats:
        raise HTTPException(404, f"no embodied-carbon declarations held for {device_class!r}")
    result = grid.break_even(country, stats["median_kg"], old_tdp_w, new_tdp_w,
                             embodied_basis=f"median of {stats['n']} declarations")
    if result is None:
        raise HTTPException(503, "grid intensity data not loaded")
    return {**result, "device_class": device_class,
            "embodied_range_kg": [stats["p25_kg"], stats["p75_kg"]],
            "declarations": stats["n"], "caveat": embodied_carbon.caveat()}


@app.get("/api/thesis")
def thesis() -> dict:
    """The four findings the product's argument actually rests on, computed.

    These already existed, scattered: two inside /api/findings, one in a JSON
    artifact nothing served, one only reachable by running an assessment. The
    argument they add up to was stated in prose in a README and nowhere a
    visitor could reach it.

    Assembled rather than restated. Every figure here is read from the same
    artifact the research page reads, so the thesis page and the evidence page
    cannot drift apart -- which is exactly how this project once ended up
    asserting two different CVE totals on one screen.
    """
    import json as _json
    from afterlife import esu, grid

    out: dict = {"claims": []}

    # 1. Age does not predict hardware degradation.
    try:
        surv = _json.loads((APP_DATA / "survival_failslow.json").read_text(encoding="utf-8"))
        out["claims"].append({
            "key": "age",
            "headline": "Age barely predicts whether a drive is failing",
            "figure": f"{surv['model_spread_x']}x",
            "unit": "spread between drive models, against no trend with age",
            "detail": surv["trend"]["note"],
            "basis": f"{surv['n_drives']:,} drives, {surv['drive_days']:,} drive-days",
            "source": surv["source"],
        })
    except Exception:  # noqa: BLE001
        pass

    # 2. Flaws needing local access are measurably less exploited.
    try:
        ep = _json.loads((APP_DATA / "epss_summary.json").read_text(encoding="utf-8"))["by_version"]["10"]
        ratio = round(ep["serious_remote"]["median"] / ep["serious_local"]["median"], 1)
        out["claims"].append({
            "key": "exploitation",
            "headline": "The flaws that strand a machine are the least exploited ones",
            "figure": f"{ratio}x",
            "unit": "more exploitation on remote flaws than local-access ones",
            "detail": f"Serious Windows 10 flaws needing an attacker already on the device "
                      f"score a median {ep['serious_local']['median']} against "
                      f"{ep['serious_remote']['median']} for remotely reachable ones. "
                      f"When a flaw needs an attacker who already has access, controlling "
                      f"access (a password, a locked screen, no untrusted accounts) "
                      f"reduces its practical risk. Unsupported status alone is "
                      f"therefore not a reason to replace a device.",
            "basis": f"{ep['serious']:,} serious CVEs, all carrying an EPSS score",
            "source": "FIRST Exploit Prediction Scoring System",
        })
    except Exception:  # noqa: BLE001
        pass

    # 3. Replacing costs more carbon than it saves, almost everywhere.
    try:
        laptop = _json.loads((APP_DATA / "embodied_carbon.json").read_text(
            encoding="utf-8"))["classes"]["Laptop"]
        kg = float(laptop["median_kg"])
        france = grid.break_even("FR", kg)
        india = grid.break_even("IN", kg)
        out["claims"].append({
            "key": "carbon",
            "headline": "A replacement rarely repays the carbon of building it",
            "figure": f"{india['years']}–{france['years']} yr",
            "unit": "to break even, depending on the grid",
            "detail": "On a coal-heavy grid a newer machine's efficiency repays its "
                      "manufacturing carbon in about two decades. On a clean one it "
                      "effectively never does. No laptop lives that long either way.",
            "basis": f"{kg:.0f} kg embodied carbon (median of {laptop['n']} laptop "
                     f"declarations), measured grid intensity per country",
            "source": grid.intensity("FR")["source"],
        })
    except Exception:  # noqa: BLE001
        pass

    # 4. The date that is actually driving retirement, read from esu.py.
    try:
        prog = esu.for_product("Windows 10")
        d = esu.describe(prog)
        end = prog.esu_end
        out["claims"].append({
            "key": "cliff",
            "headline": "What retires a working machine is a date, not a fault",
            "figure": f"{end.day} {end:%b %Y}",
            "unit": "when Extended Security Updates for Windows 10 home users end",
            "detail": d["headline"],
            "basis": "Microsoft's Windows 10 Extended Security Updates programme",
            "source": d["source"],
        })
    except Exception:  # noqa: BLE001
        pass

    out["count"] = len(out["claims"])
    out["note"] = ("Every figure on this page is read from the same artifacts the "
                   "research page reads. Neither restates the other, so they cannot "
                   "drift apart.")
    return out


@app.get("/api/sources")
def sources() -> dict:
    """Every dataset this product stands on, with freshness computed per source.

    Deliberately not a hand-written list. This project has already shipped a
    page that quoted a confident CVE count from a corpus two years stale, so a
    provenance page that itself needs remembering to update would be the same
    failure wearing a different hat. Every figure here is read out of the
    artifact on disk at request time.
    """
    from afterlife.sources import manifest
    return manifest()


@app.post("/api/predict")
def predict(body: PredictIn) -> dict:
    try:
        return predict_lifecycle(**body.model_dump())
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc))


@app.get("/api/pubkey")
def pubkey() -> dict:
    """The issuer's public key, published so anyone can pin it and verify a
    passport WITHOUT trusting this API -- the point of "verify, don't trust us."
    Set this value as AFTERLIFE_ISSUER_PUBKEY to pin it."""
    from afterlife.passport import issuer_public_key_b64
    key = issuer_public_key_b64()
    return {
        "issuer_pubkey": key,
        "algorithm": "Ed25519",
        "signature_scheme": "Ed25519Signature2020 over canonical JSON of a W3C VC v2 envelope",
    }


@app.post("/api/verify")
def verify(body: VerifyIn) -> dict:
    raw = body.passport
    if not (isinstance(raw, dict) and "payload" in raw and "signature" in raw):
        raise HTTPException(400, "malformed passport: expected payload and signature")

    from afterlife.passport import issued_by_afterlife
    ok = verify_payload(raw)
    ident = raw.get("payload", {}).get("device_id", "device")
    genuine = issued_by_afterlife(raw)

    # A valid signature by an UNKNOWN key is not "trusted" -- it only means the
    # doc is internally consistent. Only a valid signature by the pinned AfterLife
    # key earns the strong claim; say so, rather than letting a self-signed
    # forgery inherit the same green "verified" as a genuine passport.
    if not ok:
        message = "Signature INVALID — this passport was altered. Do not trust."
    elif genuine is False:
        message = (f"Signature is internally valid, but {ident} was NOT signed by "
                   "AfterLife's key. Treat as unverified.")
    elif genuine is True:
        message = f"Verified — {ident} was issued by AfterLife and not edited since."
    else:
        message = f"Signature valid — {ident} was not edited since issue."

    return {"valid": ok, "issued_by_afterlife": genuine, "device_id": ident, "message": message}


class AssessIn(BaseModel):
    # An instant scan sends no hardware score and starts from the documented
    # default (assessment.BROWSER_START_TRUST); a deep scan sends its measured one.
    hardware_trust: int = Field(default_factory=lambda: _browser_start_trust())
    eol_risk: float | None = None
    battery_health: float | None = None
    age_years: float | None = None
    fault_described: bool = False
    fault_detail: str | None = None   # which fault theme was recognised, e.g. "Battery"
    trust_measured: bool = False      # deep scan: battery and age are already inside hardware_trust
    make_model: str | None = None
    manufacturer: str | None = None
    cpu: str | None = None
    os: str | None = None
    win11: str | None = None
    win11_blockers: list[str] | None = None
    win11_permanently_blocked: bool | None = None
    win11_firmware_fixable: bool | None = None
    storage: str | None = None
    product_category: str | None = None
    # The browser's own timezone, e.g. "Asia/Kolkata". Country is resolved from
    # it rather than from the visitor's IP: the IANA mapping is public domain,
    # no personal data is read or stored, and a VPN changes an IP but not a
    # clock. `country` is the user's explicit correction and always wins.
    timezone: str | None = None
    country: str | None = None
    # What the device is used for. Instant scan: the user's answer ("persona",
    # self-reported). Deep scan: the collector's installed-tool categories
    # ("persona_signals", auto-detected). Both feed the usage-fit card, the
    # memory upgrade on the repair outlook, and the key points.
    persona: str | None = None
    persona_signals: dict | None = None
    cores: int | None = None
    ram_gb: float | None = None
    gpu: str | None = None
    # The fault text typed into "anything wrong?", read only to look up repair
    # records for the same fault (the score uses the recognised theme above).
    problem: str | None = None
    storage_problem: bool = False   # deep scan: the drive reported a warning or heavy wear
    # A phone or tablet's model code as Chrome on Android reports it ("SM-S931B"),
    # or a model name the owner typed, for the EU repairability grade (S3-01).
    model_code: str | None = None
    os_supported: bool | None = None


def _browser_start_trust() -> int:
    from afterlife.assessment import BROWSER_START_TRUST
    return BROWSER_START_TRUST


def _support_cliff(product: str | None) -> dict | None:
    """Days and date to the end of extended support, or None."""
    import datetime as _dt

    from afterlife import esu

    prog = esu.for_product(product)
    if prog is None:
        return None
    today = _dt.date.today()
    if today > prog.esu_end:
        return None
    return {
        "product": prog.product,
        "date": prog.esu_end.isoformat(),
        "days_away": (prog.esu_end - today).days,
        "state": prog.state(today).value,
        "source": prog.source,
    }


@app.post("/api/assess")
def assess(body: AssessIn) -> dict:
    """Combined lifecycle assessment: deterministic blended score + years pipeline +
    rule-based summary + the five Lifecycle Pathways (see afterlife/pathways.py)."""
    from afterlife.assessment import blend_score, estimate_years, key_points, narrate
    from afterlife.pathways import compute_pathways, narrate_pathways
    from afterlife.device_support import (
        lookup as support_lookup, reassess_note, risk_detail as support_risk_detail,
    )
    from afterlife.geo import resolve as resolve_geo

    # Resolved before anything that depends on jurisdiction or currency.
    geo = resolve_geo(body.timezone, body.country)

    # eol_risk used to arrive as a bare float chosen by the caller -- the single
    # guess in an otherwise measurement-driven score. Resolve it against a
    # published security-end date where one exists, and hand the date back with
    # it so the number can be checked instead of trusted.
    #
    # An explicit client value still wins. Absence stays absence -- no published end date means no support horizon in
    # the response, never an invented one.
    horizon = support_lookup(body.make_model, body.os)
    eol_risk = body.eol_risk if body.eol_risk is not None else (
        horizon.eol_risk if horizon else None)

    # Which of the two quantities this is, carried alongside the number itself.
    # An explicit client value arrives from the instant scan, where it is the
    # repair classifier's End-of-life probability embedded in the signed profile;
    # otherwise the score uses the published support date resolved above. The
    # label says which, so a support date is never credited to the model.
    if body.eol_risk is not None:
        eol_source, eol_detail = "ml", None
    elif horizon:
        eol_source, eol_detail = "support", support_risk_detail(horizon)
    else:
        eol_source, eol_detail = None, None

    blend = blend_score(body.hardware_trust, eol_risk, body.battery_health,
                        body.age_years, body.fault_described,
                        eol_source=eol_source, eol_detail=eol_detail,
                        fault_detail=body.fault_detail, trust_measured=body.trust_measured)
    years = estimate_years(blend["combined_score"], body.age_years, body.battery_health)
    context = {**blend, **years,
               "make_model": body.make_model, "cpu": body.cpu, "os": body.os,
               "win11": body.win11, "battery_health": body.battery_health,
               "age_years": body.age_years, "measured": body.trust_measured}
    points = key_points(blend, years, body.win11,
                        battery_health=body.battery_health, age_years=body.age_years)
    pathways = compute_pathways(
        blend["grade"], body.win11, body.win11_blockers,
        body.win11_permanently_blocked, body.win11_firmware_fixable, body.storage,
    )

    # The summary and the pathway framing line are independent of each other,
    # so they are built side by side.
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_narrative = pool.submit(narrate, context)
        fut_pathways = pool.submit(narrate_pathways, pathways, blend["grade"])
        narrative = fut_narrative.result()
        pathways_narrative = fut_pathways.result()

    # The carbon trade-off, on the grid this device is actually plugged into.
    #
    # The research page quotes ~21 years to break even "even on the dirtiest
    # grid". That is the conservative framing and it is true, but it is not the
    # user's number -- the break-even varies by an order of magnitude between
    # grids, and geo.py already knows which one they are on.
    #
    # Joined to the device's own declared embodied carbon where Boavizta has an
    # LCA for it, so the numerator is measured rather than assumed too.
    carbon_tradeoff = None
    try:
        from afterlife import grid
        from afterlife.embodied_carbon import lookup as carbon_lookup

        declared = carbon_lookup(body.manufacturer, body.make_model,
                                 device_class=body.product_category)
        from afterlife.cpu_power import rated_power
        from afterlife.persona import classify_signals as _classify
        # The usage answer picks the highlighted scenario (light / typical /
        # heavy), and a deep scan's processor name sets the old machine's
        # rated power instead of the 45 W default (S2-13).
        use = (_classify(body.persona_signals)["persona"] if body.persona_signals is not None
               else body.persona)
        carbon_tradeoff = grid.payback_range(
            geo.country,
            # A matched model carries its own declared figure; a class estimate
            # carries the median of its class. Either is a measured value.
            embodied_kg=(declared or {}).get("gwp_total_kg") or (declared or {}).get("median_kg"),
            embodied_basis=(declared or {}).get("basis"),
            cpu=rated_power(body.cpu, body.product_category) if body.trust_measured else None,
            use=use,
            device_class=body.product_category,
        )
    except Exception:  # noqa: BLE001
        carbon_tradeoff = None

    # What it is used for, and whether it is up to that work (S2-07).
    from afterlife.persona import assess_fit, classify_signals
    usage_fit = None
    try:
        if body.persona_signals is not None:
            detected = classify_signals(body.persona_signals)
            usage_fit = assess_fit(body.cores, body.ram_gb, body.gpu, detected["persona"],
                                   "auto-detected", detected["reasons"])
        elif body.persona:
            usage_fit = assess_fit(body.cores, body.ram_gb, body.gpu, body.persona, "self-reported")
    except Exception:  # noqa: BLE001 -- an add-on card must never sink an assessment
        usage_fit = None
    if usage_fit:
        use = usage_fit["label"].lower()
        if usage_fit["current_tier"]:
            points["strengths"].append(f"Up to {usage_fit['current_tier']} ({use})")
        else:
            points["weaknesses"].append(f"Short of the lightest {use} tier checked")

    # What fixing it would buy, and how often a repair like it succeeds (S2-05).
    from afterlife.repair_evidence import evidence_block
    from afterlife.uplift import capability_uplift, condition_uplift
    condition = condition_uplift(
        body.hardware_trust, eol_risk, body.battery_health, body.age_years,
        body.fault_described, fault_detail=body.fault_detail,
        trust_measured=body.trust_measured, storage=body.storage, eol_source=eol_source)
    capability = None
    if usage_fit:
        from afterlife.persona import BROWSER_RAM_CAP
        capability = capability_uplift(
            usage_fit["persona"], body.cores, body.ram_gb, body.gpu,
            ram_is_lower_bound=usage_fit["source"] == "self-reported"
            and (body.ram_gb or 0) >= BROWSER_RAM_CAP)
    repair_evidence = evidence_block(
        battery_health=body.battery_health,
        storage_health="FAILING" if body.storage_problem else None,
        os_supported=body.os_supported,
        problem=body.problem)

    # What the law entitles the owner to (S2-06), for the country resolved above.
    from afterlife.repair_rights import assess as repair_rights_for
    repair_rights = repair_rights_for(
        body.product_category, in_eea=geo.in_eea if geo.country else None,
        country=geo.country or None, country_name=geo.country_name if geo.country else None)

    # The official EU repairability grade for a phone or tablet (S3-01): what
    # the maker declared to the EPREL registry, shown next to the model's
    # prediction. Laptops are not in the registry and get nothing, never a guess.
    eprel = None
    try:
        from afterlife.eprel import class_spread, find as eprel_find, is_covered
        if is_covered(body.product_category) and (body.model_code or "").strip():
            rec = eprel_find(body.model_code, body.product_category)
            eprel = ({**rec, "matched": True, "spread": class_spread()} if rec
                     else {"matched": False, "query": body.model_code.strip()[:60]})
    except Exception:  # noqa: BLE001 -- an enrichment must never sink an assessment
        eprel = None

    return {"blend": blend, "pipeline": years, "narrative": narrative, "key_points": points,
            "eprel": eprel,
            "pathways": pathways, "pathways_narrative": pathways_narrative, "win11": body.win11,
            "carbon_tradeoff": carbon_tradeoff,
            "usage_fit": usage_fit,
            "uplift": ({"condition": condition, "capability": capability}
                       if condition or capability else None),
            "repair_evidence": repair_evidence,
            "repair_rights": repair_rights,
            # The date security updates stop, the months left, and the sentence
            # that turns a static verdict into one with a review date on it.
            # Null when no end date has been published for this device or OS.
            "support_horizon": ({**horizon.as_dict(), "note": reassess_note(horizon)}
                                if horizon else None),
            # The extended-support end date, when one is published for this OS.
            # support_horizon above is when ordinary updates stopped; this is
            # when the home-user Extended Security Updates programme stops.
            # They are different dates, and conflating them would understate
            # how long the machine is still patched.
            #
            # Null where no programme exists or where the cliff has already
            # passed -- absence stays absence, and a cliff behind the device is
            # not a forecast.
            "support_cliff": _support_cliff(body.os or body.make_model),
            # Where we think the user is, how we worked it out, and how much of
            # the repair corpus actually comes from there. Returned so the
            # interface can show it -- a wrong country gives a wrong carbon
            # figure, so this must never be silent.
            "geo": geo.as_dict()}


@app.get("/api/assumptions")
def assumptions() -> dict:
    """Every number AfterLife assumes, its kind (learned / looked up / chosen),
    the reason for its value, its limit and its source (S2-12). Values are read
    from the code when asked, never typed into the page."""
    from afterlife.assumptions import table
    return table()


class ExplainIn(BaseModel):
    assessment: dict
    tier: str | None = None


@app.post("/api/explain")
def explain_assessment(body: ExplainIn, request: Request) -> dict:
    """The plain-language explanation (S2-08). A language model words the
    already-computed result; afterlife/explain.py rejects any reply containing a
    number that is not on the page, and falls back to the rule-based summary.
    Rate-limited per visitor, because the model's free tier has a daily cap."""
    from afterlife import kvstore
    from afterlife.explain import explain
    who = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
           or (request.client.host if request.client else "unknown"))
    if not kvstore.hit(f"explain:{who}", 30, 600):
        rule = ((body.assessment.get("narrative") or {}).get("summary")) or ""
        return {"text": rule, "source": "rule-based", "checked": True,
                "reason": "too many explanations from this address in 10 minutes"}
    return explain(body.assessment, body.tier)


class PriceIn(BaseModel):
    price_new: float
    product_category: str | None = None
    age_years: float | None = None
    grade: str = "C - serviceable"
    cosmetic: str | None = None
    currency: str = "USD"


@app.post("/api/price-estimate")
def price_estimate(body: PriceIn) -> dict:
    """Resale range from the formula in afterlife/pricing.py. The grade is the
    one the assessment awarded; the price new and the cosmetic condition are the
    owner's own answers."""
    from afterlife.pricing import estimate_resale
    if body.price_new <= 0 or body.price_new > 10_000_000:
        raise HTTPException(400, "price_new must be a positive amount")
    return estimate_resale(body.price_new, body.product_category, body.age_years,
                           body.grade, body.cosmetic, body.currency[:3].upper())


@app.post("/api/scan-passport")
def scan_passport(scan: dict) -> dict:
    """Sign a browser-scanned device profile and issue a passport.

    The lifecycle assessment (score/grade) is computed by the frontend in a
    separate call to /api/assess right after this one.
    """
    if not scan:
        raise HTTPException(400, "empty scan payload")
    doc = build_scan_passport(scan)
    doc["verified"] = verify_payload(doc)
    return doc


# ---------------------------------------------------------------- deep scan
# The browser opens a deep scan with a random one-time token, shows the user a
# one-line command, and polls GET /api/deep-scan/{token}. The command downloads
# the collector (read-only; collector/collect_device.ps1), which reads the
# machine and POSTs its findings to /api/deep-scan/{token}. The server signs a
# full-scan passport and keeps it for an hour under that token, then forgets it.
# Nothing is linked to a person unless they later choose to save the scan.
_DEEP_TTL = 3600
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def _check_token(token: str) -> None:
    if not _TOKEN.fullmatch(token):
        raise HTTPException(400, "malformed scan token")


@app.get("/api/collector.ps1")
def collector_ps1() -> PlainTextResponse:
    """The Windows collector, served as plain text so a browser shows the source
    rather than offering to run it."""
    return PlainTextResponse((ROOT / "collector" / "collect_device.ps1").read_text(encoding="utf-8"))


@app.get("/api/collector.sh")
def collector_sh() -> PlainTextResponse:
    """The macOS and Linux collector, served the same way."""
    return PlainTextResponse((ROOT / "collector" / "collect_device.sh").read_text(encoding="utf-8"))


@app.post("/api/deep-scan/{token}")
def deep_scan_ingest(token: str, device: dict) -> dict:
    """The collector posts here; sign a full-scan passport and keep it for the
    browser that is polling with the same token."""
    _check_token(token)
    if not device:
        raise HTTPException(400, "empty device payload")
    from afterlife import kvstore
    from afterlife.passport import build_deep_passport
    doc = build_deep_passport(device)
    doc["verified"] = verify_payload(doc)
    # Beside the passport, never inside it: only this browser session needs it.
    doc["persona_signals"] = device.get("persona_signals")
    # The findings below ride beside the passport, not inside its signature:
    # they are display detail, and keeping them out keeps the QR small. Each is
    # isolated so one failure can never stop a scan from being delivered.
    try:
        from afterlife.hardware_signals import summarize
        doc["hardware"] = summarize(device)
    except Exception as exc:  # noqa: BLE001
        doc["hardware"] = {"findings": [], "clean": None, "unreadable": ["all"],
                           "summary": f"unavailable: {exc}"}
    try:
        from afterlife.hardening import build_report
        rep = build_report(os_caption=device.get("os_caption"),
                           mitigation_state=device.get("mitigation_state"),
                           os_upgradable=doc["payload"].get("win11") == "ELIGIBLE")
        doc["mitigation"] = rep.as_dict() if rep else {"available": False}
    except Exception as exc:  # noqa: BLE001
        doc["mitigation"] = {"available": False, "reason": f"unavailable: {exc}"}
    try:
        from afterlife.secure_boot import assess as secure_boot_assess
        doc["secure_boot"] = secure_boot_assess(device)
    except Exception as exc:  # noqa: BLE001
        doc["secure_boot"] = {"status": "unknown", "headline": f"unavailable: {exc}"}
    try:
        from afterlife.wipe import check as wipe_check
        doc["wipe"] = wipe_check(device.get("clean_state"))
    except Exception as exc:  # noqa: BLE001
        doc["wipe"] = {"status": "unknown", "checks": [], "failures": [], "note": f"unavailable: {exc}"}
    kvstore.put(f"deep:{token}", doc, _DEEP_TTL)
    return {"ok": True, "device_id": doc["payload"]["device_id"]}


@app.get("/api/deep-scan/{token}")
def deep_scan_poll(token: str) -> dict:
    """The browser polls this until the collector has delivered."""
    _check_token(token)
    from afterlife import kvstore
    return kvstore.get(f"deep:{token}") or {"pending": True}


# ---------------------------------------------------------------- saved scans
class SaveScanIn(BaseModel):
    passport: dict
    scan_type: str = "instant"
    assessment: dict | None = None


@app.get("/api/account-status")
def account_status() -> dict:
    """Whether accounts are switched on here (they need Supabase settings)."""
    from afterlife import auth
    return {"accounts": auth.configured()}


@app.post("/api/save-scan")
def save_scan_route(body: SaveScanIn, authorization: str | None = Header(default=None)) -> dict:
    """Add a finished scan to the signed-in user's history. The browser calls
    this once the assessment is in, so a saved row is ready to compare.

    Only a genuine, unedited AfterLife passport is saved: the history is a
    record the user may later show to a buyer, so it must not hold anything the
    verifier would reject. The assessment rides along for display; it is
    recomputed from the passport, never trusted for anything."""
    from afterlife import auth
    from afterlife.passport import issued_by_afterlife
    if body.scan_type not in ("instant", "deep"):
        raise HTTPException(400, "scan_type must be 'instant' or 'deep'")
    user_id = auth.user_from_token(authorization)
    if not user_id:
        raise HTTPException(401, "sign in to save scans")
    doc = body.passport
    if not (isinstance(doc, dict) and "payload" in doc and "signature" in doc):
        raise HTTPException(400, "malformed passport")
    if not verify_payload(doc) or issued_by_afterlife(doc) is False:
        raise HTTPException(400, "only a genuine, unedited AfterLife passport can be saved")
    keep = {k: doc[k] for k in ("payload", "signature", "issuer_pubkey", "issuer", "validFrom") if k in doc}
    result = auth.save_scan(user_id, doc["payload"].get("device_id"), body.scan_type,
                            {**keep, "assessment": body.assessment})
    return {"saved": result in ("inserted", "refreshed"), "result": result}


@app.get("/api/my-scans")
def my_scans(authorization: str | None = Header(default=None)) -> dict:
    """The signed-in user's saved scans, newest first."""
    from afterlife import auth
    user_id = auth.user_from_token(authorization)
    if not user_id:
        raise HTTPException(401, "sign in to see your saved scans")
    return {"scans": auth.list_scans(user_id)}


@app.get("/api/findings")
def findings() -> dict:
    """Everything the frontend dashboard renders, from the real exported artifacts."""
    decay = _load_json("decay.json")
    metrics = _load_json("lifecycle_metrics.json")
    experiments = _load_json("model_experiments.json")
    failslow = _load_json("failslow_results.json")
    research = _load_json("research_results.json")
    # Provenance only -- which KEV catalogue the corpus was tagged against, and
    # the caveat that absence from it is not evidence of safety. The counts
    # themselves come from the corpus via _security_summary(), so this file
    # cannot drift out of step with them.
    kev = _load_json("kev_summary.json")
    # Only the summary block is read here; the per-model table in the same file
    # is for the device lookup, not the research page.
    embodied = _load_json("embodied_carbon.json")
    _laptop_carbon = embodied.get("classes", {}).get("Laptop", {})
    # Break-even per grid, computed with the same function and the same embodied
    # figure the per-device carbon card and The Argument use.
    from afterlife import grid
    _embodied_kg = _laptop_carbon.get("median_kg") or grid.DEFAULT_EMBODIED_KG
    _breakeven: dict[str, float] = {}
    for _label, _code in (("France", "FR"), ("Germany", "DE"), ("United States", "US"),
                          ("World", None), ("India", "IN")):
        _be = grid.break_even(_code, _embodied_kg)
        if _be and _be.get("repays"):
            _breakeven[_label] = _be["years"]
    dm = decay.get("meta", {})
    # Computed from the corpus rather than hardcoded in the page. These figures
    # change every time the CVE catalogue is refreshed, and a headline finding
    # that silently goes stale is worse than not showing one -- it has already
    # happened once on this page with an end-of-support day count.
    mitigation_summary = _mitigation_summary()
    return {
        "decay": {
            "series": decay.get("series", {}),
            "projection": decay.get("projection", []),
            "win7_settled_months": dm.get("win7_months_to_5pct"),
            "win10_projected_months": dm.get("months_to_5pct"),
            "win10_pi": [dm.get("months_to_5pct_early"), dm.get("months_to_5pct_late")],
            "r_squared": dm.get("r_squared"),
        },
        # Counted from the same shipped corpus the mitigation block below reads,
        # never hardcoded. These sat frozen at a 1,981-CVE pull while the block
        # directly beneath them was already reporting 6,606 from the refreshed
        # corpus -- one page asserting two different totals for one dataset. The
        # numbers are only trustworthy if there is exactly one place they can
        # come from.
        "security": _security_summary(),
        "kev": {
            "catalog_version": kev.get("catalog_version"),
            "date_released": kev.get("date_released"),
            "kev_total": kev.get("kev_total"),
            "kev_ransomware": kev.get("kev_ransomware"),
            "caveat": kev.get("caveat"),
            "source": kev.get("source"),
        },
        # Embodied-carbon figure follows the GHG Protocol's Corporate Value Chain
        # (Scope 3) Standard -- the actual named methodology for accounting a
        # device's manufacturing emissions -- cross-checked against ADEME's Base
        # Empreinte, its public emissions-factor database, rather than an
        # invented per-device number.
        "carbon": {
            # Measured, not quoted. This was a flat 300 kg with a [200, 300]
            # range taken from methodology documents; it is now the median and
            # interquartile range of 452 manufacturer LCA declarations for
            # laptops. The old figure was close -- 300 against a measured 307 --
            # but "close" was luck, and the page separately admitted the number
            # was a class-wide range rather than a measurement of anything.
            "embodied_kg": _laptop_carbon.get("median_kg", 300),
            "embodied_kg_range": [_laptop_carbon.get("p25_kg", 200),
                                  _laptop_carbon.get("p75_kg", 300)],
            "embodied_n": _laptop_carbon.get("n"),
            # The share that is manufacturing rather than use, which is the
            # number the whole repair-versus-replace argument turns on: at ~80%,
            # replacing a working laptop discards most of its footprint no
            # matter how clean the grid it runs on.
            "manufacturing_ratio": _laptop_carbon.get("median_manufacturing_ratio"),
            "by_class": embodied.get("classes", {}),
            "embodied_source": "Boavizta manufacturer LCA declarations, cross-checked against "
                               "the GHG Protocol Scope 3 Standard and ADEME Base Empreinte",
            "embodied_caveat": embodied.get("caveat"),
            "breakeven_years": _breakeven,
            "laptop_lifespan": 6,
        },
        # Reshaped when the trainer moved to grouped validation. Every model now
        # carries BOTH a random-split and a held-out-venue score, because the gap
        # between them is the finding -- reporting only one would hide it.
        "model": {
            "n_records": metrics.get("n_records"), "n_groups": metrics.get("n_groups"),
            "folds": metrics.get("folds"),
            "distribution": metrics.get("distribution"),
            "results": metrics.get("results"),
            "winner": metrics.get("winner"),
            "winner_representation": metrics.get("winner_representation"),
            "winner_grouped": metrics.get("winner_grouped"),
            "best_macro_f1": metrics.get("best_macro_f1"),
            "venue_leakage": metrics.get("venue_leakage"),
            "calibration": metrics.get("calibration"),
            # Per device type, because laptops are half the data and a single
            # headline could be a laptop score wearing a general label.
            "by_category": metrics.get("by_category", []),
            # What was tried and rejected, kept because a page that only
            # reports what worked is not a record of an investigation.
            "experiments": experiments.get("experiments", []),
            "also_checked": experiments.get("also_checked", []),
            "protocol": metrics.get("protocol"),
        },
        # SSD versus HDD on persistent slowness, which does not go the way most
        # people assume.
        "failslow": failslow,
        # The cross-validated four-model comparison and the cost-ratio sweep that
        # shows the cost-sensitive choice is robust rather than a knife-edge.
        "research": {
            "n_train": research.get("n_train"), "n_test": research.get("n_test"),
            "results": research.get("results", []),
            "cv_5fold": research.get("cv_5fold", {}),
            "cost_ratio_sweep": research.get("cost_ratio_sweep", {}),
            "accuracy_best_model": research.get("accuracy_best_model"),
            "cv_cost_best_model": research.get("cv_cost_best_model"),
            "shap_top_features_eol": research.get("shap_top_features_eol", []),
        },
        # The keep-or-replace finding, recomputed from the live corpus.
        "mitigation": mitigation_summary,
        # Observed repair outcomes by fault type, from the same ORA records the
        # classifier trains on (scripts/build_repair_evidence.py).
        "repair_evidence": _load_repair_evidence(),
    }


def _load_repair_evidence() -> dict:
    from afterlife.repair_evidence import load
    try:
        return load()
    except Exception:  # noqa: BLE001
        return {}


#: NVD's attack-vector enum -> the word a person reads on the chart.
_VECTOR_LABEL = {
    "LOCAL": "Local", "NETWORK": "Network",
    "ADJACENT_NETWORK": "Adjacent", "PHYSICAL": "Physical",
}


def _security_summary(major: str = "10") -> dict:
    """Attack-vector breakdown for one Windows version, counted from the corpus.

    Kept separate from _mitigation_summary() because it answers a different
    question -- that one asks "can this be closed without new hardware?", this
    one asks "where does the attacker have to be standing?" -- but both now read
    the same file, so they can no longer drift apart.
    """
    from afterlife.hardening import SERIOUS, load_classified

    rows = load_classified(major)
    serious = [r for r in rows if (r.get("severity") or "").upper() in SERIOUS]
    vectors: dict[str, int] = {}
    for r in serious:
        label = _VECTOR_LABEL.get((r.get("attack_vector") or "").upper())
        if label:
            vectors[label] = vectors.get(label, 0) + 1
    # Physical presence is a local-access problem too -- an attacker at the
    # keyboard is not a remote one -- so it counts on the same side of the
    # argument the chart is making.
    local_like = vectors.get("Local", 0) + vectors.get("Physical", 0)

    # "Serious" is CVSS's opinion about what a flaw would do if exploited. KEV is
    # an observation that it has been, against real targets. Counted from the
    # same rows as everything else above, so the two can never disagree.
    def _flag(name: str, of=rows) -> int:
        return sum(1 for r in of if (r.get(name) or "").lower() == "true")

    # Severity is an opinion, KEV is a rare observation, EPSS is the forecast in
    # between -- and it is what turns "4,843 serious flaws" from a number too
    # large to act on into a distribution with a mass and a tail. Absent until
    # scripts/enrich_cve_epss.py has run; the block is omitted rather than
    # zero-filled, because a missing forecast is not a forecast of zero.
    epss_block = None
    scored = [float(r["epss"]) for r in serious if r.get("epss")]
    if scored:
        from afterlife.epss import ACT_THRESHOLD, expected_exploited
        import statistics
        epss_block = {
            "scored": len(scored),
            "unscored": len(serious) - len(scored),
            "median": round(statistics.median(scored), 5),
            "mean": round(statistics.mean(scored), 5),
            "over_threshold": sum(1 for v in scored if v >= ACT_THRESHOLD),
            "act_threshold": ACT_THRESHOLD,
            # Expectation, not prediction. Linear, so it needs no independence
            # assumption between CVEs -- which is just as well.
            "expected_exploited_30d": expected_exploited(scored),
        }

    return {
        "total_cves": len(rows),
        "serious_cves": len(serious),
        # Descending, so the chart's own ordering comes from the data instead of
        # a dict literal someone has to remember to re-sort after a refresh.
        "vectors": dict(sorted(vectors.items(), key=lambda kv: kv[1], reverse=True)),
        "local_share": round(local_like / len(serious), 3) if serious else 0.0,
        "known_exploited": _flag("known_exploited"),
        "serious_known_exploited": _flag("known_exploited", serious),
        "ransomware": _flag("ransomware"),
        "epss": epss_block,
        # Who assigned the severities this whole block is counted from. NIST
        # stopped routinely enriching CVEs in April 2026, so this ratio drifts
        # toward the vendors whose products are being scored, and a drift
        # nobody is looking at is how the last stale corpus survived two years.
        "scoring": _scoring_provenance(rows),
    }


def _scoring_provenance(rows: list[dict]) -> dict:
    """Where this corpus's CVSS severities actually came from."""
    from collections import Counter

    counts = Counter((r.get("metric_source") or "").strip() or "unscored" for r in rows)
    total = len(rows) or 1
    nist = counts.get("nvd@nist.gov", 0)
    return {
        "nist": nist,
        "nist_share": round(nist / total, 3),
        "vendor": total - nist - counts.get("unscored", 0),
        "unscored": counts.get("unscored", 0),
        "note": "From April 2026 NIST stopped routinely enriching CVEs and now relies "
                "on the scores CNAs supply. Microsoft self-scores its own flaws, so "
                "coverage holds -- but the basis of a severity is increasingly the "
                "vendor's rating of its own product, not an independent one.",
    }


def _mitigation_summary() -> dict:
    """The headline CVE breakdown per Windows version, straight from the corpus.

    Returned per version rather than for Windows 10 alone so the page can state
    both and show the finding holds across a supported OS as well as an
    end-of-support one.
    """
    from afterlife.hardening import WINDOWS_VERSIONS, build_report

    out: dict = {}
    for major, meta in WINDOWS_VERSIONS.items():
        try:
            rep = build_report(os_caption=f"Windows {major}")
        except Exception:  # noqa: BLE001
            continue
        if not rep:
            continue
        out[major] = {
            "label": meta["label"],
            "supported": bool(meta["supported"]),
            "serious": rep.serious_cves,
            "fixable": rep.fixable_cves,
            "isolation": rep.isolation_cves,
            "local_access": rep.local_access_cves,
            "remote_no_lever": rep.remote_no_lever_cves,
            "remote_no_creds": rep.remote_no_creds_cves,
            "addressable_pct": round(rep.addressable_share * 100, 1),
        }
    return out
