// Keep vs replace, by carbon. Every figure on this page comes from
// GET /api/grid-countries or GET /api/carbon-calc (afterlife/grid.py); the page
// draws bars from those numbers and never supplies one of its own.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import "./carbon.css";

// A handful of common time zones whose country is unambiguous. Anything else
// falls back to the region in the browser's language tag, and failing that the
// world average. It is a guess, labelled as one, and the visitor can change it.
const TZ_COUNTRY = {
  "Asia/Kolkata": "IN", "Asia/Calcutta": "IN", "Europe/London": "GB", "Europe/Dublin": "IE",
  "Europe/Paris": "FR", "Europe/Berlin": "DE", "Europe/Madrid": "ES", "Europe/Rome": "IT",
  "Europe/Amsterdam": "NL", "Europe/Brussels": "BE", "Europe/Vienna": "AT", "Europe/Zurich": "CH",
  "Europe/Stockholm": "SE", "Europe/Oslo": "NO", "Europe/Copenhagen": "DK", "Europe/Helsinki": "FI",
  "Europe/Warsaw": "PL", "Europe/Prague": "CZ", "Europe/Lisbon": "PT", "Europe/Athens": "GR",
  "Asia/Tokyo": "JP", "Asia/Seoul": "KR", "Asia/Shanghai": "CN", "Asia/Singapore": "SG",
  "Asia/Dubai": "AE", "Asia/Karachi": "PK", "Asia/Dhaka": "BD", "Asia/Jakarta": "ID",
  "Asia/Manila": "PH", "Asia/Bangkok": "TH", "Asia/Kathmandu": "NP", "Asia/Colombo": "LK",
  "Africa/Johannesburg": "ZA", "Africa/Lagos": "NG", "Africa/Nairobi": "KE", "Africa/Cairo": "EG",
  "America/Sao_Paulo": "BR", "America/Mexico_City": "MX", "America/Argentina/Buenos_Aires": "AR",
  "Pacific/Auckland": "NZ",
};

function guessCountry(codes) {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (TZ_COUNTRY[tz] && codes.has(TZ_COUNTRY[tz])) return TZ_COUNTRY[tz];
    if (/^(America\/(New_York|Chicago|Denver|Los_Angeles|Phoenix|Anchorage|Detroit))/.test(tz) && codes.has("US")) return "US";
    if (/^Australia\//.test(tz) && codes.has("AU")) return "AU";
    if (/^America\/(Toronto|Vancouver|Edmonton|Winnipeg|Halifax)/.test(tz) && codes.has("CA")) return "CA";
  } catch { /* no Intl time zone: fall through */ }
  try {
    const region = new Intl.Locale(navigator.language).maximize().region;
    if (region && codes.has(region)) return region;
  } catch { /* no locale: world average */ }
  return "";
}

function errorText(err) {
  try { return JSON.parse(err.message).detail || err.message; } catch { return err?.message || "request failed"; }
}

const fmt = (n, d = 0) => (typeof n === "number" && Number.isFinite(n)
  ? n.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d }) : null);

function PowerControl({ label, hint, value, onChange }) {
  const id = useId();
  const [draft, setDraft] = useState(null);
  const bad = draft != null;
  return (
    <div className="cc-field cc-power">
      <label htmlFor={id} className="cc-label">{label}</label>
      <div className="cc-power-row">
        <input id={id} type="range" min={1} max={300} step={1} value={Math.min(value, 300)}
          onChange={(e) => { setDraft(null); onChange(Number(e.target.value)); }} aria-describedby={`${id}-hint`} />
        <span className="cc-power-num">
          <input type="number" min={1} max={500} step={1} value={draft ?? value} aria-label={`${label}, in watts`}
            aria-invalid={bad} aria-describedby={`${id}-hint`}
            onChange={(e) => {
              const n = Number(e.target.value);
              if (e.target.value !== "" && e.target.checkValidity() && Number.isFinite(n)) { setDraft(null); onChange(n); }
              else setDraft(e.target.value);
            }} />
          <span aria-hidden="true">W</span>
        </span>
      </div>
      <p id={`${id}-hint`} className={`v2-note ${bad ? "cc-bad" : ""}`}>
        {bad ? "Outside the range the calculator accepts (whole watts, within the field's limits) — the result still shows the last valid value." : hint}
      </p>
    </div>
  );
}

function EmbodiedBar({ res, classes }) {
  const [p25, p75] = res.embodied_range_kg || [];
  const median = res.embodied_kg;
  if (typeof p25 !== "number" || typeof p75 !== "number" || typeof median !== "number") {
    return <p className="v2-note">No declared range came back for this class.</p>;
  }
  // Scale: zero to the widest upper quartile among all classes, so the classes
  // can be compared by eye when the visitor switches between them.
  const max = Math.max(p75, ...classes.map((c) => c.p75_kg).filter((x) => typeof x === "number"));
  const at = (v) => `${((v / max) * 100).toFixed(2)}%`;
  return (
    <div className="cc-emb">
      <div className="cc-emb-track" role="img"
        aria-label={`Embodied carbon for ${res.device_class}: middle half of declarations ${fmt(p25)} to ${fmt(p75)} kg, median ${fmt(median)} kg`}>
        <div className="cc-emb-band" style={{ left: at(p25), width: `calc(${at(p75)} - ${at(p25)})` }} />
        <div className="cc-emb-med" style={{ left: at(median) }} />
      </div>
      <div className="cc-emb-legend">
        <span><span><b className="v2-num">{fmt(p25)}</b> kg</span><small>25th percentile</small></span>
        <span className="is-med"><span><b className="v2-num">{fmt(median)}</b> kg</span><small>median</small></span>
        <span><span><b className="v2-num">{fmt(p75)}</b> kg</span><small>75th percentile</small></span>
      </div>
      <p className="v2-note">
        Manufacturer declarations for “{res.device_class}”: {res.embodied_basis}. The band is the middle half
        of those declarations and the break-even above uses the median. The bar runs from zero to the highest
        75th percentile of any device class, so classes compare by eye.
      </p>
    </div>
  );
}

function GridCompare({ grid, world }) {
  const rows = [];
  if (grid.basis === "country") rows.push({ k: "you", name: grid.region, v: grid.gco2_kwh, year: grid.year });
  if (world && typeof world.gco2_kwh === "number") rows.push({ k: "world", name: "World average", v: world.gco2_kwh, year: world.year });
  const max = Math.max(...rows.map((r) => r.v));
  return (
    <div className="cc-grid">
      {rows.map((r) => (
        <div key={r.k} className={`cc-grid-row is-${r.k}`}>
          <div className="cc-grid-head">
            <span>{r.name}{r.year ? ` (${r.year})` : ""}</span>
            <span><b className="v2-num">{fmt(r.v)}</b> gCO₂e/kWh</span>
          </div>
          <div className="cc-grid-bar" aria-hidden="true"><span style={{ width: `${max > 0 ? (r.v / max) * 100 : 0}%` }} /></div>
        </div>
      ))}
      {grid.basis === "world" && (
        <p className="cc-flag" role="note">
          Using the <b>world average</b>, not your own grid — no country is selected, or the chosen one has no
          figure in the dataset. Pick your country for an answer about your electricity.
        </p>
      )}
    </div>
  );
}

function neverReason(res) {
  const a = res.assumptions || {};
  if (typeof a.old_tdp_w === "number" && typeof a.new_tdp_w === "number" && a.new_tdp_w >= a.old_tdp_w) {
    return "The replacement draws as much power as the old device or more, so it saves no electricity to repay its manufacturing carbon with.";
  }
  return "The grid is so clean that the electricity saved is too small to ever repay the manufacturing carbon credibly.";
}

export default function CarbonCalc({ onNavigate }) {
  const [meta, setMeta] = useState(null);
  const [metaError, setMetaError] = useState(null);
  const [country, setCountry] = useState("");
  const [guessed, setGuessed] = useState(false);
  const [deviceClass, setDeviceClass] = useState("");
  const [oldTdp, setOldTdp] = useState(null);
  const [newTdp, setNewTdp] = useState(null);
  const [res, setRes] = useState(null);
  const [calcError, setCalcError] = useState(null);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);
  // The inputs the current result answers. Seeding the sliders and class from
  // the first response changes state to those same values; without this the
  // page would immediately re-request an identical calculation.
  const answered = useRef(null);
  const countryId = useId(), classId = useId();

  useEffect(() => {
    let live = true;
    api.gridCountries().then((d) => {
      if (!live) return;
      const g = guessCountry(new Set((d.countries || []).map((c) => c.code)));
      setCountry(g); setGuessed(Boolean(g)); setMeta(d);
    }).catch((e) => live && setMetaError(errorText(e)));
    return () => { live = false; };
  }, []);

  // Recompute on every input change, debounced. The first call sends no power
  // figures so the server's own defaults seed the sliders.
  useEffect(() => {
    if (!meta) return undefined;
    const key = JSON.stringify([country, deviceClass, oldTdp, newTdp]);
    if (key === answered.current) return undefined;
    const id = ++seq.current;
    const t = setTimeout(() => {
      setBusy(true);
      api.carbonCalc({ country, deviceClass: deviceClass || undefined, oldTdp, newTdp })
        .then((r) => {
          if (id !== seq.current) return;
          setRes(r); setCalcError(null);
          answered.current = JSON.stringify([country, deviceClass || r.device_class,
            oldTdp ?? r.assumptions?.old_tdp_w, newTdp ?? r.assumptions?.new_tdp_w]);
          if (oldTdp == null && r.assumptions) setOldTdp(r.assumptions.old_tdp_w);
          if (newTdp == null && r.assumptions) setNewTdp(r.assumptions.new_tdp_w);
          if (!deviceClass && r.device_class) setDeviceClass(r.device_class);
        })
        .catch((e) => id === seq.current && setCalcError(errorText(e)))
        .finally(() => id === seq.current && setBusy(false));
    }, oldTdp == null ? 0 : 250);
    return () => clearTimeout(t);
  }, [meta, country, deviceClass, oldTdp, newTdp]);

  const classes = meta?.device_classes || [];
  const countries = meta?.countries || [];
  const a = res?.assumptions;
  const equalPower = useMemo(() => oldTdp != null && newTdp != null && oldTdp === newTdp, [oldTdp, newTdp]);

  if (metaError) {
    return (
      <section className="cc">
        <p className="v2-eyebrow">Carbon calculator</p>
        <h1 className="v2-h2">The grid and device data could not be loaded.</h1>
        <p className="v2-note">{metaError}. The calculator shows nothing it cannot read from the server.</p>
      </section>
    );
  }

  return (
    <section className="cc">
      <header className="cc-hero">
        <p className="v2-eyebrow">Carbon calculator · keep vs replace</p>
        <h1 className="v2-h1">Does a new device <span className="v2-grad-text">ever pay back</span> its own making?</h1>
        <p className="v2-lede">
          Building a computer emits most of the carbon it will ever account for. A more efficient replacement saves
          some electricity every year. This works out how many years of use it takes for those savings to repay the
          carbon spent manufacturing the replacement — on your grid.
        </p>
      </header>

      <div className="cc-layout">
        <form className="v2-card cc-controls" onSubmit={(e) => e.preventDefault()} aria-label="Calculator inputs">
          <div className="cc-field">
            <label htmlFor={countryId} className="cc-label">Where the device is used</label>
            <select id={countryId} value={country} disabled={!meta}
              onChange={(e) => { setCountry(e.target.value); setGuessed(false); }}>
              <option value="">World average (no country)</option>
              {countries.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
            </select>
            {guessed && <p className="v2-note">Guessed from your browser's time zone or language — change it if wrong.</p>}
          </div>
          <div className="cc-field">
            <label htmlFor={classId} className="cc-label">Kind of device</label>
            <select id={classId} value={deviceClass} disabled={!meta || !classes.length}
              onChange={(e) => setDeviceClass(e.target.value)}>
              {!deviceClass && <option value="">Loading…</option>}
              {classes.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
          </div>
          {oldTdp != null && newTdp != null ? (
            <>
              <PowerControl label="Old device's processor power" value={oldTdp} onChange={setOldTdp}
                hint="The rated TDP of the processor you would retire." />
              <PowerControl label="Replacement's processor power" value={newTdp} onChange={setNewTdp}
                hint="Set it equal to the old one for a like-for-like swap." />
            </>
          ) : <div className="cc-skel" aria-hidden="true" />}
        </form>

        <div className={`v2-card cc-result ${busy ? "is-busy" : ""}`} aria-live="polite" aria-busy={busy}>
          {calcError && <p className="cc-flag is-error" role="alert">{calcError}</p>}
          {!res && !calcError && <div className="cc-skel is-tall" aria-hidden="true" />}
          {res && (
            <>
              <p className="v2-eyebrow">Years until a replacement repays its manufacturing carbon</p>
              {res.repays && typeof res.years === "number" ? (
                <p className="cc-big"><span className="v2-num v2-grad-text">{fmt(res.years, 1)}</span><span className="cc-big-unit">years</span></p>
              ) : (
                <>
                  <p className="cc-big is-never"><span className="v2-num">Never</span><span className="cc-big-unit">repays</span></p>
                  <p className="cc-reason">{neverReason(res)}</p>
                </>
              )}
              <p className="cc-headline">{res.headline}</p>
              {equalPower && res.repays && <p className="v2-note">Power values are equal but the server still found a saving; see the assumptions below.</p>}

              <div className="cc-stats">
                <div>
                  <span className="cc-stat-k">Carbon saved per year</span>
                  <span className="cc-stat-v"><b className="v2-num">{fmt(res.annual_saving_kg, 1) ?? "—"}</b> kg CO₂e</span>
                </div>
                <div>
                  <span className="cc-stat-k">Electricity saved per year</span>
                  <span className="cc-stat-v">
                    {fmt(res.annual_kwh_saved, 1) != null
                      ? <><b className="v2-num">{fmt(res.annual_kwh_saved, 1)}</b> kWh</>
                      : <span className="cc-na">not computed — no saving to repay with</span>}
                  </span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {res && (
        <div className="cc-detail">
          <div className="v2-card cc-panel">
            <h2 className="v2-h3">Carbon to build the replacement</h2>
            <EmbodiedBar res={res} classes={classes} />
            {res.caveat && <p className="v2-note cc-caveat">{res.caveat}</p>}
          </div>
          <div className="v2-card cc-panel">
            <h2 className="v2-h3">How dirty the electricity is</h2>
            {res.grid && <GridCompare grid={res.grid} world={meta?.world} />}
            <p className="v2-note">Source: {res.grid?.source || meta?.source || "not stated"}{res.grid?.year ? `, ${res.grid.year} figure` : ""}.</p>
          </div>
          {a && (
            <div className="v2-card cc-panel cc-assume">
              <h2 className="v2-h3">What this assumes</h2>
              <dl className="cc-assume-list">
                <div><dt>Hours of use a year</dt><dd className="v2-num">{fmt(a.hours_per_year) ?? "—"}</dd></div>
                <div><dt>Average load (share of TDP)</dt><dd className="v2-num">{typeof a.load_factor === "number" ? `${fmt(a.load_factor * 100)}%` : "—"}</dd></div>
                <div><dt>Whole-system multiplier</dt><dd className="v2-num">{typeof a.system_overhead === "number" ? `${fmt(a.system_overhead, 1)}×` : "—"}</dd></div>
              </dl>
              {a.note && <p className="v2-note">{a.note}</p>}
            </div>
          )}
        </div>
      )}

      <div className="cc-ctas">
        <button type="button" className="v2-btn" onClick={() => onNavigate?.("scan")}>Scan your own device</button>
        <button type="button" className="v2-btn ghost" onClick={() => onNavigate?.("thesis")}>Read the argument</button>
      </div>
    </section>
  );
}
