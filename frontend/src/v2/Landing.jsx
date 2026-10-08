// The full-bleed home page: a scroll story from the question, through the
// evidence, to the tools. Every figure is read from the API (/api/findings,
// /api/thesis, /api/esu); a section whose data fails to load is left out
// rather than filled with a stand-in. The only invented number is the hero
// ring's score, and it is labelled "example" on screen.
import { useEffect, useState } from "react";
import { api } from "../api.js";
import { HowSteps, Reveal, prefersReducedMotion, useInView } from "./HowItWorks.jsx";
import "./landing.css";

function useApi(fetcher) {
  const [data, setData] = useState(null);
  useEffect(() => {
    let live = true;
    fetcher().then((d) => { if (live) setData(d); }).catch(() => {});
    return () => { live = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return data;
}

const fmtDate = (iso) => {
  if (!iso || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return null;
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null
    : d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
};

//: "https://www.microsoft.com/..." -> "microsoft.com"; anything else unchanged.
const sourceLabel = (s) => {
  if (!s) return null;
  try { return /^https?:\/\//.test(s) ? new URL(s).hostname.replace(/^www\./, "") : s; }
  catch { return s; }
};

/* ------------------------------------------------------------ count-up */

function CountUp({ value, duration = 1500 }) {
  const [ref, inView] = useInView();
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!inView) return undefined;
    if (prefersReducedMotion()) { setN(value); return undefined; }
    let raf; let t0;
    const tick = (t) => {
      if (t0 === undefined) t0 = t;
      const p = Math.min(1, (t - t0) / duration);
      setN(Math.round(value * (1 - (1 - p) ** 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, value, duration]);
  const final = value.toLocaleString("en-US");
  return (
    <span ref={ref} className="lp-count">
      <span aria-hidden="true">{n.toLocaleString("en-US")}</span>
      <span className="lp-sr">{final}</span>
    </span>
  );
}

/* ------------------------------------------------------------ hero */

// Purely illustrative: the ring fills to a fixed example value. It does not
// read this device, and it says so in the label and the caption.
const EXAMPLE_SCORE = 78;

function ExampleRing() {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (prefersReducedMotion()) { setN(EXAMPLE_SCORE); return undefined; }
    let raf; let t0;
    const tick = (t) => {
      if (t0 === undefined) t0 = t;
      const p = Math.min(1, (t - t0 - 350) / 1800);
      if (p > 0) setN(Math.round(EXAMPLE_SCORE * (1 - (1 - p) ** 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  const r = 92;
  const c = 2 * Math.PI * r;
  return (
    <figure className="lp-ring" aria-label="Example score ring, illustrative only. Not a reading of this device.">
      <div className="lp-ring-glow" aria-hidden="true" />
      <div className="lp-ring-badge">Example</div>
      <svg viewBox="0 0 240 240" aria-hidden="true">
        <defs>
          <linearGradient id="lp-ring-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#7c3aed" />
            <stop offset="0.55" stopColor="#2563eb" />
            <stop offset="1" stopColor="#059669" />
          </linearGradient>
        </defs>
        <circle cx="120" cy="120" r={r} className="lp-ring-track" />
        <circle cx="120" cy="120" r={r} className="lp-ring-arc" stroke="url(#lp-ring-g)"
                strokeDasharray={c} strokeDashoffset={c * (1 - n / 100)}
                transform="rotate(-90 120 120)" />
        <circle cx="120" cy="120" r="70" className="lp-ring-inner" />
      </svg>
      <div className="lp-ring-center" aria-hidden="true">
        <div className="lp-ring-num v2-num">{n}</div>
        <div className="lp-ring-lbl">example score</div>
      </div>
      <div className="lp-chip lp-chip-a" aria-hidden="true"><i className="dot cool" />Hardware trust</div>
      <div className="lp-chip lp-chip-b" aria-hidden="true"><i className="dot amber" />End-of-life risk</div>
      <div className="lp-chip lp-chip-c" aria-hidden="true"><i className="dot hot" />Signed passport</div>
      <figcaption className="v2-note">Example only. Not a reading of your device.</figcaption>
    </figure>
  );
}

function Hero({ onNavigate }) {
  return (
    <section className="lp-hero" aria-labelledby="lp-title">
      <div className="lp-hero-bg" aria-hidden="true" />
      <div className="v2-wrap lp-hero-grid">
        <div className="lp-hero-copy">
          <div className="lp-kicker"><span className="lp-kicker-dot" aria-hidden="true" />Obsolete? Says who?</div>
          <h1 id="lp-title" className="lp-display">
            Should this device <span className="v2-grad-text">continue existing?</span>
          </h1>
          <p className="v2-lede">
            AfterLife scans a laptop or phone, scores it, predicts its end-of-life risk from real repair
            records, and tells you whether to keep, repair, sell or recycle it. Then it signs the answer,
            so anyone can check it.
          </p>
          <div className="lp-cta-row">
            <button className="v2-btn lp-btn-lg" onClick={() => onNavigate("scan")}>
              Scan this device <span aria-hidden="true">→</span>
            </button>
            <button className="v2-btn ghost lp-btn-lg" onClick={() => onNavigate("thesis")}>
              See the evidence
            </button>
          </div>
        </div>
        <ExampleRing />
      </div>
      <div className="lp-scroll-hint" aria-hidden="true"><span /></div>
    </section>
  );
}

/* ------------------------------------------------------------ proof strip */

function ProofStrip({ findings }) {
  if (!findings) return null;
  const f = findings;
  const stats = [
    { value: f.model?.n_records, label: "repair outcomes the model learned from", src: "Open Repair Alliance" },
    { value: f.security?.total_cves, label: "Windows CVEs classified", src: "NVD · CISA KEV" },
    { value: f.nvme?.drives, label: "data-centre drives studied", src: "Alibaba NVMe corpus" },
    { value: f.carbon?.embodied_n, label: "manufacturer carbon declarations", src: "Boavizta" },
  ].filter((s) => Number.isFinite(s.value));
  if (stats.length < 2) return null;
  return (
    <section className="lp-proof" aria-labelledby="lp-proof-h">
      <div className="v2-wrap">
        <Reveal className="lp-proof-head">
          <h2 id="lp-proof-h" className="v2-eyebrow">Verified, not vibes. The data behind every verdict.</h2>
        </Reveal>
        <div className="lp-proof-grid">
          {stats.map((s, i) => (
            <Reveal key={s.src} className="lp-proof-stat" delay={i * 80}>
              <div className="lp-proof-v v2-num"><CountUp value={s.value} /></div>
              <div className="lp-proof-k">{s.label}</div>
              <div className="lp-proof-src">{s.src}</div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ how it works */

function HowSection({ onNavigate }) {
  return (
    <section className="v2-section lp-how" aria-labelledby="lp-how-h">
      <div className="v2-wrap">
        <Reveal className="lp-sec-head">
          <div className="v2-eyebrow">How it works</div>
          <h2 id="lp-how-h" className="v2-h2">Four steps. <span className="v2-grad-text">One signed answer.</span></h2>
        </Reveal>
        <HowSteps />
        <Reveal className="lp-sec-foot">
          <button className="v2-btn ghost" onClick={() => onNavigate("how")}>
            How it works, in full <span aria-hidden="true">→</span>
          </button>
        </Reveal>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ argument */

function Argument({ thesis, onNavigate }) {
  const claims = (thesis?.claims || []).filter((c) => c && c.figure && c.headline);
  if (!claims.length) return null;
  return (
    <section className="v2-section lp-arg" aria-labelledby="lp-arg-h">
      <div className="v2-wrap">
        <Reveal className="lp-sec-head">
          <div className="v2-eyebrow">The argument</div>
          <h2 id="lp-arg-h" className="v2-h2">
            Most devices are retired by a <span className="v2-grad-text">story</span>, not a fault.
          </h2>
          <p className="v2-lede">Each claim below is computed from public data, with its basis and source.</p>
        </Reveal>
        <div className="lp-arg-grid">
          {claims.map((c, i) => (
            <Reveal key={c.key || i} delay={(i % 2) * 100} className="lp-arg-cell">
              <button className="lp-arg-card v2-card is-link" onClick={() => onNavigate("thesis")}>
                <span className="lp-arg-fig v2-num v2-grad-text">{c.figure}</span>
                {c.unit && <span className="lp-arg-unit">{c.unit}</span>}
                <span className="lp-arg-head">{c.headline}</span>
                {(c.basis || c.source) && (
                  <span className="lp-arg-src">
                    {c.basis}{c.basis && c.source ? " · " : ""}{sourceLabel(c.source)}
                  </span>
                )}
                <span className="lp-arg-go" aria-hidden="true">Read the argument →</span>
              </button>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ ESU teaser */

function EsuTeaser({ esu, onNavigate }) {
  const c = esu?.consumer;
  if (!c) return null;
  const days = Number.isFinite(c.ends_in_days) && c.ends_in_days > 0 ? c.ends_in_days : null;
  const end = fmtDate(c.esu_end);
  if (!days && !c.headline) return null;

  // Share of the paid/free ESU window already used, from the API's own dates.
  let elapsed = null;
  const s = Date.parse(c.support_end); const e = Date.parse(c.esu_end); const now = Date.parse(esu.as_of);
  if ([s, e, now].every(Number.isFinite) && e > s) elapsed = Math.min(1, Math.max(0, (now - s) / (e - s)));

  return (
    <section className="v2-section lp-esu" aria-labelledby="lp-esu-h">
      <div className="v2-wrap">
        <Reveal className="lp-esu-card">
          <div className="lp-esu-copy">
            <div className="v2-eyebrow">{c.product || "Windows 10"} countdown</div>
            <h2 id="lp-esu-h" className="v2-h2">
              {days ? <>The cliff is a <span className="v2-grad-text">date</span>.</> : c.headline}
            </h2>
            {days && c.headline && <p className="v2-lede">{c.headline}</p>}
            {c.scope && <p className="v2-note">{c.scope}</p>}
            <button className="v2-btn" onClick={() => onNavigate("esu")}>
              See the full countdown <span aria-hidden="true">→</span>
            </button>
          </div>
          {days && (
            <div className="lp-esu-count">
              <div className="lp-esu-days v2-num"><CountUp value={days} duration={1200} /></div>
              <div className="lp-esu-unit">days of consumer security updates left</div>
              {end && <div className="lp-esu-end">Last update: <b>{end}</b></div>}
              {elapsed !== null && (
                <div className="lp-esu-bar" role="img"
                     aria-label={`Extended Security Updates window, from ${fmtDate(c.support_end)} to ${end}`}>
                  <div className="lp-esu-fill" style={{ "--lp-w": `${(elapsed * 100).toFixed(1)}%` }} />
                  <div className="lp-esu-ends">
                    <span>{fmtDate(c.support_end)}</span><span>{end}</span>
                  </div>
                </div>
              )}
              {esu.as_of && <div className="v2-note">As of {fmtDate(esu.as_of)}.</div>}
            </div>
          )}
        </Reveal>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ tools */

const TOOLS = [
  {
    id: "compare", title: "Compare devices",
    text: "Put two devices side by side and see how they stack up.",
    icon: <><rect x="3" y="7" width="11" height="15" rx="2" /><rect x="18" y="7" width="11" height="15" rx="2" /><path d="M8.5 26h15" /></>,
  },
  {
    id: "carbon", title: "Carbon calculator",
    text: "Keep or replace, by carbon, on the grid your country actually runs on.",
    icon: <><path d="M16 28c-6 0-10-4.5-10-10C6 10 16 4 16 4s10 6 10 14c0 5.5-4 10-10 10z" /><path d="M16 28V14" /></>,
  },
  {
    id: "verify", title: "Verify a passport",
    text: "Paste a passport or scan its QR to check the signature and the issuer key.",
    icon: <><path d="M16 3l10 4v8c0 7-4.5 11.5-10 14-5.5-2.5-10-7-10-14V7z" /><path d="M11 16l3.5 3.5L21 13" /></>,
  },
];

function Tools({ onNavigate }) {
  return (
    <section className="v2-section lp-tools" aria-labelledby="lp-tools-h">
      <div className="v2-wrap">
        <Reveal className="lp-sec-head">
          <div className="v2-eyebrow">Tools</div>
          <h2 id="lp-tools-h" className="v2-h2">Tools for the <span className="v2-grad-text">whole decision.</span></h2>
        </Reveal>
        <div className="lp-tools-grid">
          {TOOLS.map((t, i) => (
            <Reveal key={t.id} delay={i * 70} className="lp-tool-cell">
              <button className="lp-tool v2-card is-link" onClick={() => onNavigate(t.id)}>
                <svg className="lp-tool-ico" viewBox="0 0 32 32" aria-hidden="true">{t.icon}</svg>
                <span className="lp-tool-t">{t.title}</span>
                <span className="lp-tool-d">{t.text}</span>
                <span className="lp-tool-go" aria-hidden="true">Open →</span>
              </button>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ closing */

function Closing({ onNavigate }) {
  return (
    <section className="lp-close" aria-labelledby="lp-close-h">
      <div className="v2-wrap">
        <Reveal className="lp-close-card">
          <div className="lp-close-glow" aria-hidden="true" />
          <h2 id="lp-close-h" className="lp-display lp-close-h">
            Obsolete? <span className="v2-grad-text">Says who?</span>
          </h2>
          <p className="v2-lede">Get an answer you can check, for the device in front of you.</p>
          <div className="lp-cta-row is-center">
            <button className="v2-btn lp-btn-lg" onClick={() => onNavigate("scan")}>
              Scan this device <span aria-hidden="true">→</span>
            </button>
            <button className="v2-btn ghost lp-btn-lg" onClick={() => onNavigate("verify")}>
              Verify a passport
            </button>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ page */

export default function Landing({ onNavigate }) {
  const nav = (id) => onNavigate?.(id);
  const findings = useApi(() => api.findingsOnce());
  const thesis = useApi(() => api.thesis());
  const esu = useApi(() => api.esu());
  return (
    <div className="lp">
      <Hero onNavigate={nav} />
      <ProofStrip findings={findings} />
      <HowSection onNavigate={nav} />
      <Argument thesis={thesis} onNavigate={nav} />
      <EsuTeaser esu={esu} onNavigate={nav} />
      <Tools onNavigate={nav} />
      <Closing onNavigate={nav} />
    </div>
  );
}
