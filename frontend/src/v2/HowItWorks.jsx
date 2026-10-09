// "How it works" — the pipeline explainer, plus the reusable four-step strip
// (HowSteps) and the scroll-reveal helpers the landing page shares.
//
// Every count on this page is read from /api/findings. Facts about the pipeline
// are taken from Scanner.jsx, afterlife/passport.py, afterlife/assessment.py and
// VERIFICATION.md; nothing here describes a capability the code does not have.
import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import "./how.css";

/* ------------------------------------------------------------ shared helpers */

export function prefersReducedMotion() {
  return typeof window !== "undefined"
    && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

//: True once the element has scrolled into view (and stays true).
export function useInView(options) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    if (typeof IntersectionObserver === "undefined") { setInView(true); return undefined; }
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setInView(true); io.disconnect(); }
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08, ...options });
    io.observe(el);
    return () => io.disconnect();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return [ref, inView];
}

//: Fades and lifts its children in the first time they scroll into view.
export function Reveal({ as: Tag = "div", className = "", delay = 0, style, children, ...rest }) {
  const [ref, inView] = useInView();
  return (
    <Tag ref={ref} className={`hw-reveal${inView ? " is-in" : ""}${className ? ` ${className}` : ""}`}
         style={{ "--hw-delay": `${delay}ms`, ...style }} {...rest}>
      {children}
    </Tag>
  );
}

const fmt = (n) => (Number.isFinite(n) ? n.toLocaleString("en-US") : null);
const pct = (x) => (Number.isFinite(x) ? `${Math.round(x * 100)}%` : null);

/* ------------------------------------------------------------ HowSteps */

const STEPS = [
  {
    key: "scan", title: "Scan",
    text: "An instant read in the browser with no download, plus the age and any faults you add.",
    icon: (
      <>
        <rect x="4" y="6" width="24" height="16" rx="2.5" />
        <path d="M11 27h10M16 22v5" />
        <path d="M8 14h16" className="hw-ico-scan" />
      </>
    ),
  },
  {
    key: "score", title: "Score",
    text: "Rule-based hardware trust and an end-of-life signal, blended in code into a grade and pathways.",
    icon: (
      <>
        <circle cx="16" cy="16" r="11" />
        <path d="M16 5a11 11 0 0 1 10.4 14.6" className="hw-ico-arc" />
        <path d="M12 17l3 3 6-7" />
      </>
    ),
  },
  {
    key: "sign", title: "Sign",
    text: "A passport signed with Ed25519, shaped as a W3C Verifiable Credential, with a QR code.",
    icon: (
      <>
        <path d="M8 4h12l5 5v19H8z" />
        <path d="M20 4v5h5" />
        <path d="M12 16h9M12 20h6" />
        <circle cx="21" cy="23" r="3" />
      </>
    ),
  },
  {
    key: "verify", title: "Verify",
    text: "Anyone checks the signature: on the Verify page, or offline with a short script.",
    icon: (
      <>
        <path d="M16 3l10 4v8c0 7-4.5 11.5-10 14-5.5-2.5-10-7-10-14V7z" />
        <path d="M11 16l3.5 3.5L21 13" />
      </>
    ),
  },
];

//: The four-step strip: scan -> score -> sign -> verify. Used on the landing
//: page and at the top of the full explainer.
export function HowSteps({ className = "" }) {
  return (
    <ol className={`hw-steps${className ? ` ${className}` : ""}`}>
      {STEPS.map((s, i) => (
        <Reveal as="li" key={s.key} className="hw-step" delay={i * 90}>
          <div className="hw-step-top">
            <span className="hw-step-n" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
            <svg className="hw-step-ico" viewBox="0 0 32 32" aria-hidden="true">{s.icon}</svg>
          </div>
          <h3 className="v2-h3">{s.title}</h3>
          <p>{s.text}</p>
        </Reveal>
      ))}
    </ol>
  );
}

/* ------------------------------------------------------------ flow diagram */

const NODES = {
  instant: { title: "Instant scan", lines: ["In the browser,", "no download"] },
  deep: { title: "Your answers", lines: ["Device type, age and", "any faults you enter"] },
  hw: { title: "Hardware trust", lines: ["A documented baseline", "for a browser scan"], tone: "cool" },
  eol: { title: "End-of-life risk", lines: ["Repair model, or a", "published support date"], tone: "amber" },
  blend: { title: "Blended score", lines: ["Grade and pathways:", "keep · harden · repurpose", "sell · recycle"] },
  pass: { title: "Signed passport", lines: ["Ed25519 · W3C VC", "with a QR code"], tone: "hot" },
  verify: { title: "Anyone verifies", lines: ["Verify page, or scan", "the QR code"], tone: "green" },
};

const WIDE = {
  viewBox: "0 0 1120 300",
  boxes: {
    instant: [0, 30, 180, 100], deep: [0, 170, 180, 100],
    hw: [235, 30, 180, 100], eol: [235, 170, 180, 100],
    blend: [470, 85, 200, 130],
    pass: [725, 100, 175, 100], verify: [945, 100, 175, 100],
  },
  edges: [
    "M180 80H207", "M180 220H207", "M207 80V220", "M207 80H229", "M207 220H229",
    "M415 80H442V150H464", "M415 220H442V150",
    "M670 150H719", "M900 150H939",
  ],
};

const TALL = {
  viewBox: "0 0 360 760",
  boxes: {
    instant: [0, 0, 170, 96], deep: [190, 0, 170, 96],
    hw: [0, 150, 170, 104], eol: [190, 150, 170, 104],
    blend: [30, 310, 300, 120],
    pass: [55, 480, 250, 96], verify: [55, 630, 250, 96],
  },
  edges: [
    "M85 96V123", "M275 96V123", "M85 123H275", "M85 123V144", "M275 123V144",
    "M85 254V282H180V304", "M275 254V282H180",
    "M180 430V474", "M180 576V624",
  ],
};

function FlowSvg({ layout, className, id }) {
  return (
    <svg className={`hw-flow ${className}`} viewBox={layout.viewBox} role="img"
         aria-labelledby={`${id}-t`}>
      <title id={`${id}-t`}>
        An instant scan plus your answers, then hardware trust and end-of-life risk, blended into a score and
        pathways, signed into a passport that anyone can verify.
      </title>
      <defs>
        <linearGradient id={`${id}-g`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7c3aed" />
          <stop offset="0.5" stopColor="#2563eb" />
          <stop offset="1" stopColor="#059669" />
        </linearGradient>
        <marker id={`${id}-a`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7"
                orient="auto-start-reverse">
          <path d="M0 0L10 5L0 10z" fill="#2563eb" />
        </marker>
      </defs>
      {layout.edges.map((d, i) => {
        const arrow = /H(229|464|719|939)$|V(144|304|474|624)$/.test(d);
        return (
          <g key={i}>
            <path d={d} className="hw-edge-base" />
            <path d={d} className="hw-edge" markerEnd={arrow ? `url(#${id}-a)` : undefined} />
          </g>
        );
      })}
      {Object.entries(layout.boxes).map(([k, [x, y, w, h]]) => {
        const n = NODES[k];
        const lineH = 17;
        const top = y + h / 2 - ((n.lines.length) * lineH) / 2 - 2;
        return (
          <g key={k} className={`hw-node${n.tone ? ` tone-${n.tone}` : ""}`}>
            <rect x={x} y={y} width={w} height={h} rx="14" />
            <text x={x + w / 2} y={top} className="hw-node-t" textAnchor="middle">{n.title}</text>
            {n.lines.map((l, i) => (
              <text key={i} x={x + w / 2} y={top + lineH * (i + 1) + 2} className="hw-node-s"
                    textAnchor="middle">{l}</text>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

/* ------------------------------------------------------------ page */

export default function HowItWorks({ onNavigate }) {
  const [f, setF] = useState(null);
  useEffect(() => {
    let live = true;
    api.findingsOnce().then((d) => { if (live) setF(d); }).catch(() => {});
    return () => { live = false; };
  }, []);
  const m = f?.model;
  const g = m?.winner_grouped;

  return (
    <div className="hw-page">
      <header className="hw-head">
        <div className="v2-eyebrow">How it works</div>
        <h1 className="v2-h1">From a scan to a <span className="v2-grad-text">signed answer</span>.</h1>
        <p className="v2-lede">
          AfterLife reads a device, scores it, weighs how close it is to the end of its life, and
          recommends what to do with it. The result is signed, so a buyer, a repairer or an IT team
          can check that nobody edited it afterwards.
        </p>
      </header>

      <HowSteps />

      <section className="hw-block" aria-labelledby="hw-pipe">
        <Reveal>
          <div className="v2-eyebrow">The pipeline</div>
          <h2 id="hw-pipe" className="v2-h2">One path, five stages.</h2>
        </Reveal>
        <Reveal className="hw-flow-card v2-card">
          <FlowSvg layout={WIDE} className="is-wide" id="hwf-w" />
          <FlowSvg layout={TALL} className="is-tall" id="hwf-t" />
        </Reveal>
      </section>

      <section className="hw-block hw-stages" aria-label="Each stage in detail">
        <Reveal className="hw-stage">
          <div className="hw-stage-n">01</div>
          <div>
            <h3 className="v2-h3">Scan: what a browser can see, plus your answers</h3>
            <p>
              The <b>instant scan</b> needs no download. It reads what a browser exposes: graphics,
              processor cores, memory and architecture, and turns it into a signed profile in
              seconds. A browser cannot see battery wear, disk health or the machine's age, so an
              instant result is built on less evidence and tends to read lower.
            </p>
            <p>
              You then <b>complete the picture</b> with what a browser cannot see: the device type,
              its age, and any faults in your own words. The device type, age and fault description
              are what the end-of-life model reads.
            </p>
          </div>
        </Reveal>

        <Reveal className="hw-stage">
          <div className="hw-stage-n">02</div>
          <div>
            <h3 className="v2-h3">Score: trust, then end-of-life risk</h3>
            <p>
              <b>Hardware trust</b> is deliberately rule-based. A browser cannot measure hardware
              condition, so an instant scan starts from a documented baseline of 75, and every
              adjustment after that is shown on the score, because a black box would defeat the
              point of a trust document.
            </p>
            <p>
              <b>End-of-life risk</b> comes from one of two places, and the result says which: the
              trained repair model, or a published security-support end date when that is the
              stronger evidence. A date is something an owner can go and check.
            </p>
            {m && Number.isFinite(m.n_records) && (
              <div className="hw-model">
                <div className="hw-model-stats">
                  <Stat v={fmt(m.n_records)} k="repair records the model learned from" />
                  {Number.isFinite(m.n_groups) && <Stat v={fmt(m.n_groups)} k="repair organisations" />}
                  {Number.isFinite(g?.eol_recall) && <Stat v={pct(g.eol_recall)} k="end-of-life recall on unseen venues" />}
                  {Number.isFinite(g?.eol_precision) && <Stat v={pct(g.eol_precision)} k="end-of-life precision on unseen venues" />}
                </div>
                <p className="v2-note">
                  Open Repair Alliance records.{m.winner ? ` Model: ${m.winner}.` : ""}
                  {Number.isFinite(m.folds) ? ` Grouped ${m.folds}-fold validation by data provider:` : ""}
                  {Number.isFinite(m.folds) ? " every test record comes from a repair venue absent from training." : ""}
                  {" "}Recall and precision are shown together because either one alone flatters the model.
                </p>
              </div>
            )}
          </div>
        </Reveal>

        <Reveal className="hw-stage">
          <div className="hw-stage-n">03</div>
          <div>
            <h3 className="v2-h3">Blend: one grade, five pathways</h3>
            <p>
              The blended score starts from hardware trust and applies bounded, explicit adjustments
              for end-of-life risk, age, any fault you report and, where a scan measured it, battery wear. It is reproducible:
              the same inputs always give the same score and grade.
            </p>
            <p>
              From the grade, each pathway gets a fit score from a fixed table: keep as the primary
              device, keep with hardening, repurpose, sell, or recycle. The highest fit is marked
              as the best fit; the other four stay visible as real options.
            </p>
          </div>
        </Reveal>

        <Reveal className="hw-stage">
          <div className="hw-stage-n">04</div>
          <div>
            <h3 className="v2-h3">Sign: a passport that cannot be quietly edited</h3>
            <p>
              The result becomes a JSON passport in a <b>W3C Verifiable Credential</b> envelope
              (context, type, issuer, valid-from, subject and proof). It is signed with
              <b> Ed25519</b> over the canonical bytes of the whole envelope, so the issuer and the
              issue date are covered as well as the device facts.
            </p>
            <p>
              Each passport stands on its own: nothing about it is stored on our server. The QR code
              carries the signed passport itself, so scanning it opens a verification of exactly what
              was signed.
            </p>
            <p className="v2-note">
              Honest limit: the envelope is shape-compatible with Digital Product Passport work, but
              the signature covers this project's canonical JSON, not JSON-LD RDF canonicalisation.
            </p>
          </div>
        </Reveal>

        <Reveal className="hw-stage">
          <div className="hw-stage-n">05</div>
          <div>
            <h3 className="v2-h3">Verify: without trusting us</h3>
            <div className="hw-verify">
              <div className="hw-verify-card">
                <div className="v2-eyebrow">Online</div>
                <p>
                  Open the Verify page, or scan the QR. It checks the signature and whether the
                  signing key is the one AfterLife publishes.
                </p>
                <button className="v2-btn ghost" onClick={() => onNavigate?.("verify")}>
                  Verify a passport <span aria-hidden="true">→</span>
                </button>
              </div>
              <div className="hw-verify-card">
                <div className="v2-eyebrow">Check it yourself</div>
                <p>
                  The signing key is public, and the signature is standard Ed25519 over the
                  passport's canonical JSON, so any Ed25519 library can re-check it against the key
                  without trusting this website.
                </p>
                <pre className="hw-code"><code>GET /api/pubkey</code></pre>
              </div>
            </div>
            <table className="hw-table">
              <caption className="v2-note">What each check proves</caption>
              <thead><tr><th scope="col">Check</th><th scope="col">What it proves</th></tr></thead>
              <tbody>
                <tr><td>Signature valid</td><td>The document has not been altered since it was signed.</td></tr>
                <tr><td>Valid, and the key matches AfterLife's published key</td><td>A genuine, unmodified AfterLife passport.</td></tr>
                <tr><td>Valid, but the key does not match</td><td>Someone self-signed a forgery. Treat it as unverified.</td></tr>
              </tbody>
            </table>
          </div>
        </Reveal>
      </section>

      <section className="hw-block" aria-labelledby="hw-cvn">
        <Reveal>
          <div className="v2-eyebrow">The rule</div>
          <h2 id="hw-cvn" className="v2-h2">What is computed, and what is <span className="v2-grad-text">written</span>.</h2>
          <p className="v2-lede">
            Words that could change a number would bring the guesswork back. So the text only
            ever describes numbers that were already computed.
          </p>
        </Reveal>
        <div className="hw-cvn">
          <Reveal className="hw-cvn-card is-computed" delay={0}>
            <div className="hw-cvn-tag">Computed</div>
            <h3 className="v2-h3">In code, or by the trained model</h3>
            <ul>
              <li>Hardware trust score (a fixed baseline of 75 for a browser scan)</li>
              <li>End-of-life risk: model probability or support-date horizon</li>
              <li>Blended score and grade</li>
              <li>Pathway fit scores and the recommendation</li>
              <li>Support end dates and countdowns</li>
              <li>The Ed25519 signature</li>
              <li>The one-line verdict quip, picked from a fixed table</li>
            </ul>
          </Reveal>
          <Reveal className="hw-cvn-card is-written" delay={120}>
            <div className="hw-cvn-tag">Written</div>
            <h3 className="v2-h3">By fixed rules, from the computed numbers</h3>
            <ul>
              <li>A plain-language summary filled in from the score and years</li>
              <li>A lifecycle note and practical suggestions</li>
              <li>It never sets, changes or rounds a value</li>
            </ul>
            <div className="hw-fallback">
              <b>The same inputs always give the same words</b>, so every sentence can be traced
              back to a number on the page.
            </div>
          </Reveal>
        </div>
      </section>

      <Reveal as="section" className="hw-cta" aria-label="Try it">
        <h2 className="v2-h2">See it on your own device.</h2>
        <div className="hw-cta-row">
          <button className="v2-btn" onClick={() => onNavigate?.("scan")}>
            Scan this device <span aria-hidden="true">→</span>
          </button>
          <button className="v2-btn ghost" onClick={() => onNavigate?.("thesis")}>See the evidence</button>
        </div>
      </Reveal>
    </div>
  );
}

function Stat({ v, k }) {
  if (v == null) return null;
  return (
    <div className="hw-stat">
      <div className="v2-num hw-stat-v">{v}</div>
      <div className="hw-stat-k">{k}</div>
    </div>
  );
}
