import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { scanDevice, SCAN_STEPS } from "./scan.js";
import PassportCard from "./PassportCard.jsx";
import AssessmentDashboard from "./AssessmentDashboard.jsx";
import { b64encodeCompressed } from "./b64.js";
import { useCountUp } from "./useCountUp.js";
import { fetchAssessment } from "./assess.js";
import { defaultProductCategory } from "./deviceCategory.js";
import { markScanned } from "./deviceStore.js";

const STAGE = { idle: 0, consent: 1, scanning: 2, complete: 3, done: 4 };

const CATEGORIES = ["Laptop", "Desktop computer", "Tablet", "Mobile", "Games console"];
const PERSONAS = [
  { value: "general", label: "General use (browsing, docs, streaming)" },
  { value: "gamer", label: "Gaming" },
  { value: "coder", label: "Coding & development" },
  { value: "editor", label: "Video or photo editing" },
];

export default function Scanner({ onNavigate }) {
  const [stage, setStage] = useState(STAGE.idle);
  const [scan, setScan] = useState(null);
  const [revealed, setRevealed] = useState(0);
  const [passport, setPassport] = useState(null);
  const [qr, setQr] = useState(null);
  const [err, setErr] = useState(null);
  const [scanFailed, setScanFailed] = useState(null);   // reason string when an instant scan errored
  // Defaults to the category of the device actually doing the scanning (phone,
  // tablet, laptop/desktop) instead of always "Laptop" -- someone scanning from
  // their phone who forgets to change the dropdown would otherwise have that
  // scan mis-filed under laptop/desktop history.
  const [extra, setExtra] = useState({ product_category: defaultProductCategory(), device_age: 4, problem: "", persona: "general" });
  const [minting, setMinting] = useState(false);
  const [assessment, setAssessment] = useState(null);
  const timers = useRef([]);

  async function runScan() {
    setStage(STAGE.scanning);
    setErr(null);
    setScanFailed(null);
    setRevealed(0);
    let data;
    try {
      data = await scanDevice();
    } catch (e) {
      // A dedicated failed state, not just a banner over the scan tiles: the
      // reader gets a clear reason and a one-click Retry rather than having to
      // work out that re-clicking a tile is how you try again.
      setScanFailed(e.message || "Something interrupted the read.");
      setStage(STAGE.idle);
      return;
    }
    setScan(data);

    // reveal fields one-by-one for the "it's reading my machine" moment
    SCAN_STEPS.forEach((_, i) => {
      const t = setTimeout(() => setRevealed(i + 1), 260 * (i + 1));
      timers.current.push(t);
    });

    const total = 260 * SCAN_STEPS.length + 400;
    const next = setTimeout(() => setStage(STAGE.complete), total);
    timers.current.push(next);
  }

  async function mint() {
    setMinting(true); setErr(null);
    try {
      const doc = await api.scanPassport({
        ...scan,
        product_category: extra.product_category,
        device_age: extra.device_age === "" ? null : Number(extra.device_age),
        problem: extra.problem,
      });
      setPassport(doc);
      // An instant scan reads this browser's own machine, so this is the moment
      // to record that this device was seen here. See deviceStore.js.
      markScanned(doc.payload?.device_id);
      // QR generation is a nice-to-have, not load-bearing -- isolated so a
      // large/edge-case payload that overflows a QR code's data capacity only
      // means "no QR," never silently skips the assessment below too (see the
      // same fix in DeepScan.jsx for the bug this caused there).
      try {
        // issuer/validFrom are load-bearing -- see the matching comment in
        // DeepScan.jsx. Dropping them makes verify_payload() check the
        // signature against the wrong bytes and always fail.
        const signed = {
          payload: doc.payload, signature: doc.signature, issuer_pubkey: doc.issuer_pubkey,
          issuer: doc.issuer, validFrom: doc.validFrom,
        };
        const data = b64encodeCompressed(signed);
        const url = `${window.location.origin}/?verify=${data}`;
        setQr(await (await import("qrcode")).default.toDataURL(url, {
          margin: 4, scale: 6, errorCorrectionLevel: "L",
          color: { dark: "#0e1518", light: "#ffffff" },
        }));
      } catch (qrErr) {
        console.warn("QR generation failed (passport still valid):", qrErr);
      }
      setStage(STAGE.done);
      fetchAssessment(doc.payload, extra).then(setAssessment).catch(() => {});
    } catch (e) {
      setErr("Backend unreachable: " + e.message);
    } finally {
      setMinting(false);
    }
  }

  function reset() {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setStage(STAGE.idle);
    setScan(null); setPassport(null); setQr(null); setRevealed(0); setErr(null); setScanFailed(null);
  }

  function savePassport() {
    const blob = new Blob([JSON.stringify(passport, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${passport.payload.device_id}.passport.json`;
    a.click();
  }

  function saveQr() {
    const a = document.createElement("a");
    a.href = qr;
    a.download = `${passport.payload.device_id}.qr.png`;
    a.click();
  }

  const idleHero = stage === STAGE.idle && !scanFailed;

  return (
    <div className="view">
      {idleHero ? (
        <Hero onScan={() => setStage(STAGE.consent)} onNavigate={onNavigate} />
      ) : (
        <div>
          <div className="eyebrow">Scan &amp; assess this device</div>
          <h1 className="title">Turn this machine into a signed passport</h1>
          <p className="lede">
            An instant read of what your browser can see. From it Afterlife creates a secure, tamper-proof passport with a QR you can save, share, and
            verify. Nothing is read or sent until you allow it.
          </p>
        </div>
      )}

      {err && <div className="badge bad">⚠ {err}</div>}

      {stage === STAGE.idle && scanFailed && (
        <div className="empty-state">
          <div className="empty-icon">⚠️</div>
          <div className="empty-title">That scan didn't finish</div>
          <p className="empty-sub">{scanFailed}</p>
          <p className="note" style={{ maxWidth: "34rem" }}>
            Usually the permission was dismissed, or the browser blocked the read. Nothing was
            saved — you can try again.
          </p>
          <div style={{ display: "flex", gap: "0.7rem", flexWrap: "wrap", justifyContent: "center", marginTop: "0.4rem" }}>
            <button className="cta" onClick={runScan}>↻ Try again</button>
            <button className="ghost" onClick={() => setScanFailed(null)}>Back</button>
          </div>
        </div>
      )}

      {stage === STAGE.idle && !scanFailed && (
        <div className="tier-choice">
          <button className="tier" onClick={() => setStage(STAGE.consent)}>
            <div className="tier-icon">⚡</div>
            <div className="tier-name">Instant scan</div>
            <div className="tier-desc">No download. Reads what the browser exposes — graphics, cores,
              memory, architecture. Signed profile in seconds.</div>
            <div className="pill muted">browser · profile tier</div>
            <div className="tier-go">Scan now <span aria-hidden="true">→</span></div>
          </button>
        </div>
      )}

      {idleHero && <ProofBand />}

      {stage === STAGE.consent && (
        <div className="card pad-lg consent">
          <div className="perm-icon">🔍</div>
          <h2>Allow Afterlife to read this device?</h2>
          <ul className="perm-list">
            <li>✓ Operating system, graphics, CPU cores, memory</li>
            <li>✓ Display, timezone, architecture</li>
            <li>✗ No files, no browsing history, no personal data</li>
          </ul>
          <div style={{ display: "flex", gap: "0.7rem" }}>
            <button className="cta" onClick={runScan}>Allow &amp; scan</button>
            <button className="ghost" onClick={reset}>Cancel</button>
          </div>
        </div>
      )}

      {stage === STAGE.scanning && scan && (
        <div className="card pad-lg">
          <div className="scanning-head">
            <span className="spinner" /> reading device profile… judging silently
          </div>
          <div className="scan-fields">
            {SCAN_STEPS.map((step, i) => {
              const raw = scan[step.key];
              const shown = i < revealed;
              const val = raw == null ? "—" : step.fmt ? step.fmt(raw) : raw;
              return (
                <div className={`scan-row ${shown ? "in" : ""}`} key={step.key}>
                  <span className="sk">{step.label}</span>
                  <span className="sv">{shown ? val : "scanning…"}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {stage === STAGE.complete && scan && (
        <div className="grid g-eq" style={{ alignItems: "start" }}>
          <div className="card pad-lg">
            <div className="scanning-head" style={{ color: "var(--green)" }}>✓ hardware read</div>
            <div className="scan-fields">
              {SCAN_STEPS.slice(0, 5).map((step) => (
                <div className="scan-row in" key={step.key}>
                  <span className="sk">{step.label}</span>
                  <span className="sv">{scan[step.key] == null ? "—" : step.fmt ? step.fmt(scan[step.key]) : scan[step.key]}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="card pad-lg">
            <h2 style={{ fontWeight: 400 }}>Complete the picture</h2>
            <p className="note" style={{ marginBottom: "1rem" }}>
              A browser can't see age or faults. Add them and the ML model runs its lifecycle outlook.
            </p>
            <div className="form">
              <div className="row2">
                <div className="field">
                  <label>Device type</label>
                  <select value={extra.product_category}
                    onChange={(e) => setExtra({ ...extra, product_category: e.target.value })}>
                    {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label>Age (years)</label>
                  <input type="number" min="0" max="30" value={extra.device_age}
                    onChange={(e) => setExtra({ ...extra, device_age: e.target.value })} />
                </div>
              </div>
              <div className="field">
                <label>Anything wrong? (optional — sharpens the outlook)</label>
                <textarea value={extra.problem} placeholder="e.g. battery drains fast — or leave blank for a healthy device"
                  onChange={(e) => setExtra({ ...extra, problem: e.target.value })} />
              </div>
              <div className="field">
                <label>What do you mainly use it for? (optional — a browser can't see installed software)</label>
                <select value={extra.persona} onChange={(e) => setExtra({ ...extra, persona: e.target.value })}>
                  {PERSONAS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              <button className="cta" onClick={mint} disabled={minting}>
                {minting ? "Assessing…" : "Assess & mint passport"}
              </button>
            </div>
          </div>
        </div>
      )}

      {stage === STAGE.done && passport && (
        <div className="results-wrap">
          <div className="results-left" id="tour-passport">
            <PassportCard doc={passport} qr={qr}
              final={assessment?.blend ? { score: assessment.blend.combined_score, grade: assessment.blend.grade } : null} />
            <div className="passport-actions">
              <button className="cta" onClick={savePassport}>Save passport (JSON)</button>
              <button className="ghost" onClick={saveQr} disabled={!qr}>{qr ? "Save QR (PNG)" : "QR unavailable"}</button>
              <button className="ghost" onClick={reset}>Scan again</button>
              <span className="note">
                Scan the QR with any phone camera to open the verifier, or save it and upload it there later.
              </span>
            </div>
          </div>
          <div className="results-right">
            {assessment ? (
              <AssessmentDashboard data={assessment} payload={passport?.payload} />
            ) : (
              <div className="center"><span className="spinner" /> crunching real numbers, not vibes…</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- proof band */
// The strip of evidence under the tier cards -- four corpus sizes, counted up.
//
// Every number is read live from /api/findings, never typed here. The hero
// learned that lesson the hard way: a hardcoded CVE count survived a corpus
// refresh and the first sentence on the site was wrong for weeks. Corpus sizes
// drift the same way, so the same rule applies -- and if the fetch fails the
// band renders nothing at all rather than a stale or invented figure.
function ProofStat({ value, label, src }) {
  const n = useCountUp(value, 1100);
  return (
    <div className="proof-cell">
      <div className="proof-num">{Number.isFinite(n) ? Math.round(n).toLocaleString() : "—"}</div>
      <div className="proof-label">{label}</div>
      <div className="proof-src">{src}</div>
    </div>
  );
}

function ProofBand() {
  const [f, setF] = useState(null);
  useEffect(() => {
    api.findingsOnce().then(setF).catch(() => {});
  }, []);
  if (!f) return null;

  const stats = [
    { value: f.model?.n_records, label: "repair outcomes learned from", src: "Open Repair Alliance" },
    { value: f.security?.total_cves, label: "Windows CVEs classified", src: "NVD · CISA KEV" },
    { value: f.carbon?.embodied_n, label: "manufacturer carbon declarations", src: "Boavizta" },
  ].filter((s) => Number.isFinite(s.value));
  if (stats.length < 2) return null;   // a band of one number looks broken

  return (
    <div className="proof" role="group" aria-label="The data behind every verdict">
      {stats.map((s) => <ProofStat key={s.label} {...s} />)}
    </div>
  );
}

/* ---------------------------------------------------------------- hero */
// A passive demo, not a real scan: the checklist shows what gets read (field
// labels only, no fabricated values), and the dial counts up to a labeled
// "example" score. Nothing here reads the visitor's device or claims to.
function Hero({ onScan, onNavigate }) {
  const [revealed, setRevealed] = useState(0);
  const [dialValue, setDialValue] = useState(0);
  // The headline count is read live rather than typed into the copy. It was
  // hardcoded at 1,513 and stayed there through a corpus refresh that moved it
  // to 4,809 -- so the first sentence a visitor read was the one number on the
  // site that was wrong. Until it loads the sentence simply omits the figure
  // instead of rendering a placeholder or a stale one.
  const [seriousCves, setSeriousCves] = useState(null);
  useEffect(() => {
    api.findingsOnce()
      .then((f) => setSeriousCves(f?.security?.serious_cves ?? null))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const timers = SCAN_STEPS.map((_, i) =>
      setTimeout(() => setRevealed((r) => Math.max(r, i + 1)), 240 * (i + 1))
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    let raf;
    const start = performance.now(), dur = 1300, target = 92;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / dur);
      setDialValue(Math.round(target * (1 - Math.pow(1 - t, 3))));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="hero">
      <div className="hero-copy">
        <div className="eyebrow">Device lifecycle intelligence</div>
        <h1 className="hero-title">Should this device<br />continue existing?</h1>
        {/* Deliberately not "N days past end of support" any more: Microsoft
            extended free Windows 10 security updates to October 2027, so counting
            days since 2025 argues from a deadline that moved. The CVE finding is
            both current and a stronger opening anyway. */}
        <p className="hero-sub">
          {seriousCves
            ? `Of ${seriousCves.toLocaleString()} serious Windows 10 vulnerabilities, not one`
            : "Not one serious Windows 10 vulnerability"} can be reached over a network
          without credentials and no fix short of new hardware. Afterlife scans your device,
          checks it against real-world data, and gives you a secure, verified verdict.
          No vibes, no upsell — just the numbers.
        </p>
        <div className="hero-cta">
          <button className="cta" onClick={onScan}>Scan your device →</button>
          <button className="ghost" onClick={() => onNavigate?.("findings")}>See the research</button>
        </div>
      </div>

      <div className="hero-visual">
        <div className="hero-dial-wrap">
          <HeroDial value={dialValue} />
          <div className="note">example score</div>
        </div>
        <div className="hero-checklist">
          {SCAN_STEPS.map((s, i) => (
            <div key={s.key} className={`hero-check ${i < revealed ? "in" : ""}`}>
              <span className="hero-check-dot" />{s.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// The score->grade->colour language used across the app (A>=85 green,
// B>=70 brand, C>=55 amber, else red). The landing dial previews it so a
// visitor learns "green = healthy, amber = ageing" here, before they ever see
// a real card -- instead of the old fixed purple that taught nothing.
function heroTone(v) {
  if (v >= 85) return { base: "var(--green)", lite: "#7ef0b4" };
  if (v >= 70) return { base: "var(--brand)", lite: "var(--brand-glow)" };
  if (v >= 55) return { base: "var(--amber)", lite: "#ffd27a" };
  return { base: "var(--red)", lite: "#ff9a9a" };
}

function HeroDial({ value }) {
  const r = 52, c = 2 * Math.PI * r;
  // No count-up here: the value arriving in this prop is ALREADY being counted
  // up by the effect in Hero(). Wrapping it in another one made the inner
  // animation restart on every frame of the outer, so the dial sat at 0 and
  // never moved.
  const off = c * (1 - value / 100);
  const tone = heroTone(value);
  return (
    <svg width="148" height="148" viewBox="0 0 136 136">
      <defs>
        {/* The arc used to be flat --brand; a two-stop gradient makes it read as
            lit from one end, and the blurred underlay is the same arc acting as
            its own glow -- SVG-only, no CSS filter on the composited layer.
            The stops track the score's grade so the colour teaches the reader. */}
        <linearGradient id="dialGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={tone.base} />
          <stop offset="100%" stopColor={tone.lite} />
        </linearGradient>
        <filter id="dialGlow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="5" />
        </filter>
      </defs>
      <circle cx="68" cy="68" r={r} fill="none" stroke="var(--line)" strokeWidth="9" />
      <circle cx="68" cy="68" r={r} fill="none" stroke="url(#dialGrad)" strokeWidth="9"
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
        transform="rotate(-90 68 68)" filter="url(#dialGlow)" opacity="0.55" />
      <circle cx="68" cy="68" r={r} fill="none" stroke="url(#dialGrad)" strokeWidth="9"
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
        transform="rotate(-90 68 68)" />
      <text x="68" y="68" textAnchor="middle" dominantBaseline="central"
        fontFamily="var(--font-display)" fontSize="34" fontWeight="700" letterSpacing="-0.03em" fill="var(--ink)">{value}</text>
      <text x="68" y="90" textAnchor="middle" fontSize="10" fill="var(--muted)">/ 100</text>
    </svg>
  );
}
