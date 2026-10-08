// Compare two devices side by side, from their signed passports.
//
// Every figure on this page comes from one of two places: the passport's own
// signed payload, or the /api/assess response computed from it. Nothing is
// filled in. Where one passport simply never measured something (an instant
// browser scan cannot read battery wear or disk health) the cell says so, and
// no side is declared "better" on a row unless both values exist AND mean the
// same thing -- an instant scan's RAM is a browser-capped lower bound, a deep
// scan's is the real figure, and pretending those compare would be a guess.
//
// A passport whose signature does not check out is still shown -- hiding it
// would leave the user wondering where it went -- but it is flagged on its
// card, its column is visibly marked, and it never wins a row.
import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { api } from "../api.js";
import { b64decodeCompressed, b64decodeUtf8 } from "../b64.js";
import { fetchAssessment } from "../assess.js";
import { scanDevice } from "../scan.js";
import { defaultProductCategory } from "../deviceCategory.js";
import { verdictFor } from "../Verifier.jsx";
import "./compare.css";

/* ------------------------------------------------------------ input parsing */
// Same rules as Verifier.extractPassport (not exported there): a ?verify= link
// carries gzip+base64url JSON, with plain base64url as the legacy fallback;
// anything else is tried as raw JSON.
function extractPassport(text) {
  const t = String(text || "").trim();
  const m = t.match(/[?&]verify=([^&\s]+)/);
  if (m) {
    let raw = m[1];
    try { raw = decodeURIComponent(raw); } catch { /* not percent-encoded */ }
    try { return b64decodeCompressed(raw); } catch { /* fall through */ }
    try { return JSON.parse(b64decodeUtf8(raw)); } catch { /* fall through */ }
  }
  try { return JSON.parse(t); } catch { return null; }
}

// What gets sent to /api/verify. A saved-scan row carries the assessment next
// to the signed fields; the client-side `verified` flag is never trusted.
function signedPart(doc) {
  const { assessment: _a, verified: _v, ...rest } = doc;
  return rest;
}

function isPassport(doc) {
  return !!(doc && typeof doc === "object" && doc.payload && typeof doc.payload === "object" && doc.signature);
}

function decodeQrFile(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = img.naturalWidth; c.height = img.naturalHeight;
      const ctx = c.getContext("2d");
      ctx.drawImage(img, 0, 0);
      const d = ctx.getImageData(0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      const code = jsQR(d.data, d.width, d.height);
      if (!code) reject(new Error("No QR code found in that image. Try a sharper screenshot."));
      else resolve(code.data);
    };
    img.onerror = () => reject(new Error("Couldn't read that image file."));
    img.src = URL.createObjectURL(file);
  });
}

/* ----------------------------------------------------------- field readers */
// Each returns { text, value, note } or null when the passport has no reading.
// `value` is the comparable quantity; it is set only when comparing it means
// something.

const isDeep = (p) => p.trust_score != null;

function pct(v) {
  const m = String(v ?? "").match(/^\s*(\d+(?:\.\d+)?)\s*%/);
  return m ? Number(m[1]) : null;
}

function deviceName(p) {
  if (p.device_name) return p.device_name;
  if (p.make_model) return p.make_model;
  const os = p.os ? p.os.replace(/\s*\(build[^)]*\)/i, "") : null;
  return [p.product_category, os].filter(Boolean).join(" · ") || "Device";
}

function bestPathway(a) {
  const ps = a?.pathways;
  if (!Array.isArray(ps) || !ps.length) return null;
  return ps.find((x) => x.status === "best_fit") || ps[0];
}

function eolAdjustment(a) {
  return (a?.blend?.adjustments || []).find((x) => x.source === "ml" || x.source === "support") || null;
}

function eolRiskOf(p, a) {
  const adj = eolAdjustment(a);
  if (!adj) return null;
  // The number assess actually used: the instant scan's signed ML probability,
  // or (deep scan) the support-date risk resolved by the server.
  const r = adj.source === "ml" ? p.lifecycle?.eol_risk : a?.support_horizon?.eol_risk;
  if (typeof r !== "number") return null;
  return { risk: r, source: adj.source, factor: adj.factor, detail: adj.detail };
}

function win11Of(p) {
  if (isDeep(p)) {
    if (p.win11 === "ELIGIBLE") return { text: "Eligible", rank: 2, tone: "good" };
    if (p.win11 === "NOT ELIGIBLE") {
      const why = p.win11_permanently_blocked ? "CPU blocks it (permanent)"
        : p.win11_firmware_fixable ? "fixable in firmware" : null;
      return { text: "Not eligible", note: why, rank: 0, tone: "bad" };
    }
    if (p.win11 === "INDETERMINATE") return { text: "Indeterminate", note: "TPM not read", rank: null };
    return null;
  }
  if (p.windows_major === "11") return { text: "Already running 11", note: "browser-reported", rank: 2, tone: "good" };
  return null;
}

function supportOf(a) {
  const s = a?.support_horizon;
  if (!s) return null;
  const m = typeof s.months_remaining === "number" ? s.months_remaining : null;
  if (s.is_eol) return { text: `Ended ${s.eol_from}`, note: s.release ? `${s.product} ${s.release}` : null, months: 0, eol: true, tone: "bad" };
  return {
    text: s.eol_from ? `Until ${s.eol_from}` : "Supported",
    note: m != null ? `about ${Math.round(m)} months left` : null,
    months: m, eol: false,
  };
}

/* -------------------------------------------------------------- the rows */
// `get(p, a)` -> { text, note, v } | null. `cmp` decides the better side:
// "higher" / "lower" on `v`, a function for custom rules, or absent for rows
// that are context rather than a contest.
const NM = null; // "not measured" marker, for readability below

const ROWS = [
  {
    key: "tier", label: "Scan depth",
    get: (p) => ({ text: isDeep(p) ? "Deep scan" : "Instant scan", note: p.tier || null }),
  },
  {
    key: "os", label: "Operating system",
    get: (p) => (p.os ? { text: p.os.replace(/\s*\(build[^)]*\)/i, ""), note: (p.os.match(/build[^)]*/i) || [null])[0] } : NM),
  },
  {
    key: "support", label: "Security updates",
    get: (_p, a) => supportOf(a),
    cmp: (x, y) => {
      if (x.eol !== y.eol) return x.eol ? 1 : -1;
      if (x.eol || x.months == null || y.months == null || Math.round(x.months) === Math.round(y.months)) return 0;
      return x.months > y.months ? -1 : 1;
    },
  },
  {
    key: "win11", label: "Windows 11",
    get: (p) => win11Of(p),
    cmp: (x, y) => (x.rank == null || y.rank == null || x.rank === y.rank ? 0 : x.rank > y.rank ? -1 : 1),
  },
  {
    key: "cpu", label: "Processor",
    get: (p) => {
      if (!p.cpu && p.cpu_cores == null) return NM;
      const cores = p.cpu_cores != null ? `${p.cpu_cores} ${isDeep(p) ? "cores" : "logical cores"}` : null;
      return p.cpu ? { text: p.cpu, note: cores } : { text: cores, note: "model not readable from a browser" };
    },
  },
  {
    key: "ram", label: "Memory",
    get: (p) => {
      if (p.ram_gb == null) return NM;
      // navigator.deviceMemory is rounded down and capped at 8: a lower bound.
      return isDeep(p) ? { text: `${p.ram_gb} GB`, v: p.ram_gb, exact: true }
        : { text: `${p.ram_gb} GB+`, note: "browser-reported, rounded down", v: p.ram_gb, exact: false };
    },
    cmp: (x, y) => {
      // A browser figure is a rounded-down bucket, a deep scan's is exact:
      // mixed precision is no contest. Like with like compares normally.
      if (x.v === y.v || x.exact !== y.exact) return 0;
      return x.v > y.v ? -1 : 1;
    },
  },
  {
    key: "storage", label: "Storage",
    get: (p) => (p.storage && p.storage !== "UNKNOWN"
      ? { text: p.storage, note: p.storage_health && p.storage_health !== "UNKNOWN" ? p.storage_health : "health not read" }
      : NM),
  },
  {
    key: "battery", label: "Battery health",
    get: (p) => {
      const v = pct(p.battery_health);
      if (v == null) {
        if (/present/i.test(p.battery_health || "")) return { text: "not measured", note: "battery present, health not read", nm: true };
        return NM;
      }
      return { text: `${v}%`, note: "of design capacity", v };
    },
    cmp: "higher",
  },
  {
    key: "gpu", label: "Graphics",
    get: (p) => (p.gpu ? { text: p.gpu } : NM),
  },
  {
    key: "age", label: "Age",
    get: (p) => {
      if (typeof p.lifecycle?.device_age === "number") return { text: `${p.lifecycle.device_age} yr`, note: "as stated at scan", v: p.lifecycle.device_age };
      if (typeof p.age_years === "number") return { text: `${p.age_years} yr`, note: "estimated by the collector", v: p.age_years };
      return NM;
    },
    cmp: "lower",
  },
  {
    key: "eol", label: "End-of-life risk",
    get: (p, a) => {
      const e = eolRiskOf(p, a);
      if (!e) return NM;
      return { text: `${Math.round(e.risk * 100)}%`, note: e.factor, v: e.risk, src: e.source };
    },
    // An ML repair-outcome probability and a support-date risk are different
    // quantities; only like with like.
    // A model probability a point or two apart is noise, not a difference:
    // under 5 percentage points is shown but not ranked.
    cmp: (x, y) => (x.src !== y.src || Math.abs(x.v - y.v) < 0.05 ? 0 : x.v < y.v ? -1 : 1),
  },
  {
    key: "years", label: "Est. years left",
    get: (_p, a) => {
      const y = a?.pipeline?.estimated_remaining_years;
      if (typeof y !== "number") return NM;
      const tot = a.pipeline.projected_total_life;
      return { text: `${y} yr`, note: typeof tot === "number" ? `of ~${tot} yr projected life` : null, v: y };
    },
    cmp: "higher", sameTier: true,
  },
  {
    key: "action", label: "Recommended action",
    get: (_p, a) => {
      const b = bestPathway(a);
      return b ? { text: b.label, note: typeof b.fit_score === "number" ? `fit ${b.fit_score}/100` : null } : NM;
    },
  },
  {
    key: "complete", label: "Evidence coverage",
    get: (p) => (typeof p.completeness_pct === "number" ? { text: `${p.completeness_pct}%`, note: "of passport fields measured" } : NM),
  },
];

function rowWinner(row, A, B, ctx) {
  if (!row.cmp || !A || !B || A.nm || B.nm || !ctx.trusted) return 0;
  if (row.sameTier && !ctx.sameTier) return 0;
  if (typeof row.cmp === "function") return row.cmp(A, B);
  if (typeof A.v !== "number" || typeof B.v !== "number" || A.v === B.v) return 0;
  const aBetter = row.cmp === "higher" ? A.v > B.v : A.v < B.v;
  return aBetter ? -1 : 1;
}

function trustState(v) {
  if (!v) return null;
  if (v.error) return { tone: "warn", label: "Not checked", trusted: false, text: v.error };
  const verdict = verdictFor(v);
  const trusted = !!v.valid && v.issued_by_afterlife !== false;
  return { tone: verdict.tone, label: verdict.label, trusted, text: v.message };
}

/* ---------------------------------------------------------------- summary */
// One plain sentence (two at most), assembled from the same values the rows
// show. No model writes this.
function buildSummary(slots, names) {
  const [a, b] = slots;
  const ta = trustState(a.verify), tb = trustState(b.verify);
  const bad = [ta?.trusted ? null : names[0], tb?.trusted ? null : names[1]].filter(Boolean);
  if (bad.length) {
    return `${bad.join(" and ")} could not be verified as AfterLife-issued, so ${bad.length > 1 ? "neither is" : "it is not"} treated as genuine and no side is declared better.`;
  }
  const sa = a.assessment?.blend?.combined_score, sb = b.assessment?.blend?.combined_score;
  const pa = a.doc.payload, pb = b.doc.payload;
  if (typeof sa !== "number" || typeof sb !== "number") return "Waiting on both assessments before summarising.";
  // Two scans of one machine is a fair thing to compare (before and after a
  // repair, say) -- it is just worth saying out loud. Only for deep scans: the
  // instant-scan ID is derived from the OS string's first characters, so every
  // Windows browser scan currently shares one ID and it proves nothing.
  const lead = isDeep(pa) && isDeep(pb) && pa.device_id && pa.device_id === pb.device_id
    ? `These are two passports for the same device (${pa.device_id}). ` : "";
  const sameTier = isDeep(pa) === isDeep(pb);
  const ya = a.assessment?.pipeline?.estimated_remaining_years, yb = b.assessment?.pipeline?.estimated_remaining_years;
  const parts = [];
  if (!sameTier) {
    const [deepN, instN] = isDeep(pa) ? [names[0], names[1]] : [names[1], names[0]];
    return `${lead}${names[0]} scores ${sa} and ${names[1]} scores ${sb}, but ${deepN} is a deep scan and ${instN} an instant scan, so the scores rest on different evidence and are not ranked against each other.`;
  }
  if (sa === sb) parts.push(`Both score ${sa}`);
  else {
    const [hi, lo, hs, ls] = sa > sb ? [names[0], names[1], sa, sb] : [names[1], names[0], sb, sa];
    parts.push(`${hi} scores ${hs - ls} point${hs - ls === 1 ? "" : "s"} higher than ${lo} (${hs} vs ${ls})`);
  }
  if (typeof ya === "number" && typeof yb === "number") {
    if (ya === yb) parts.push(`both have about ${ya} years left`);
    else {
      const [hi, hy, ly] = ya > yb ? [names[0], ya, yb] : [names[1], yb, ya];
      const d = Math.round((hy - ly) * 10) / 10;
      parts.push(`${hi} has about ${d} more year${d === 1 ? "" : "s"} of projected life (${hy} vs ${ly})`);
    }
  }
  let s = parts.join(", and ") + ".";
  if (!isDeep(pa)) s += " Both are instant scans, so battery and disk health were not measured on either.";
  return lead + s.charAt(0).toUpperCase() + s.slice(1);
}

/* ------------------------------------------------------------------- page */
const EMPTY = { status: "empty" };
const CATEGORIES = ["Laptop", "Desktop computer", "Tablet", "Mobile", "Games console"];

export default function Compare({ onNavigate }) {
  const [slots, setSlots] = useState([EMPTY, EMPTY]);
  const seq = useRef([0, 0]);

  const setSlot = (i, next) => setSlots((s) => s.map((x, j) => (j === i ? (typeof next === "function" ? next(x) : next) : x)));

  // Verify and assess run in parallel; whichever lands first is shown. A
  // sequence number drops results from a passport the slot has since replaced.
  async function load(i, doc, source, extra = null) {
    if (!isPassport(doc)) {
      setSlot(i, { status: "error", error: "That isn't a signed Afterlife passport — it needs both a payload and a signature." });
      return;
    }
    const n = ++seq.current[i];
    const live = () => seq.current[i] === n;
    setSlot(i, { status: "ready", doc, source, verify: null, assessment: null });
    api.verify(signedPart(doc))
      .then((v) => live() && setSlot(i, (s) => ({ ...s, verify: v })))
      .catch((e) => live() && setSlot(i, (s) => ({ ...s, verify: { error: `Couldn't reach the verifier: ${e.message}` } })));
    fetchAssessment(doc.payload, extra, doc)
      .then((r) => live() && setSlot(i, (s) => ({ ...s, assessment: r })))
      .catch((e) => live() && setSlot(i, (s) => ({ ...s, assessErr: e.message })));
  }

  function clear(i) { seq.current[i]++; setSlot(i, EMPTY); }

  const both = slots[0].status === "ready" && slots[1].status === "ready";
  const names = ["A", "B"];

  return (
    <div className="cmp">
      <header className="cmp-head">
        <div className="v2-eyebrow">Tools · Compare</div>
        <h1 className="v2-h2">Two devices, <span className="v2-grad-text">side by side</span></h1>
        <p className="v2-lede">
          Load a signed passport into each slot. Each one is checked against AfterLife's key and
          assessed fresh, then compared row by row — and only where both sides actually measured
          the thing.
        </p>
      </header>

      <div className="cmp-slots">
        {[0, 1].map((i) => (
          <Slot key={i} idx={i} name={names[i]} slot={slots[i]} onLoad={(d, src, extra) => load(i, d, src, extra)}
                onClear={() => clear(i)} onError={(msg) => setSlot(i, { status: "error", error: msg })} />
        ))}
      </div>

      {both ? (
        <Comparison slots={slots} names={names} />
      ) : slots.every((s) => s.status !== "ready") ? (
        <EmptyHelp onNavigate={onNavigate} />
      ) : (
        <p className="v2-note cmp-waiting">Load a second passport to see the comparison.</p>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- a slot */
const METHODS = [
  { key: "upload", label: "Upload" },
  { key: "paste", label: "Paste" },
  { key: "device", label: "This device" },
];

function Slot({ idx, name, slot, onLoad, onClear, onError }) {
  const [method, setMethod] = useState("upload");
  const id = `cmp-slot-${idx}`;

  if (slot.status === "ready") return <SlotCard name={name} slot={slot} onClear={onClear} />;

  return (
    <section className="cmp-slot v2-card" aria-labelledby={`${id}-h`}>
      <div className="cmp-slot-top">
        <span className="cmp-letter" aria-hidden="true">{name}</span>
        <h2 className="v2-h3" id={`${id}-h`}>Device {name}</h2>
      </div>
      <div className="cmp-seg" role="group" aria-label={`How to load device ${name}`}>
        {METHODS.map((m) => (
          <button key={m.key} type="button" aria-pressed={method === m.key}
                  className={method === m.key ? "is-on" : ""} onClick={() => setMethod(m.key)}>
            {m.label}
          </button>
        ))}
      </div>
      {slot.status === "error" && <div className="cmp-err" role="alert">{slot.error}</div>}
      <div className="cmp-method">
        {method === "upload" && <UploadMethod id={id} onLoad={onLoad} onError={onError} />}
        {method === "paste" && <PasteMethod id={id} onLoad={onLoad} onError={onError} />}
        {method === "device" && <DeviceMethod id={id} onLoad={onLoad} onError={onError} />}
      </div>
    </section>
  );
}

function UploadMethod({ id, onLoad, onError }) {
  const [drag, setDrag] = useState(false);
  async function handle(file) {
    if (!file) return;
    try {
      if (file.type.startsWith("image/")) {
        const text = await decodeQrFile(file);
        const doc = extractPassport(text);
        if (!doc) throw new Error("QR found, but it isn't an Afterlife passport.");
        onLoad(doc, "QR image");
      } else {
        const doc = extractPassport(await file.text());
        if (!doc) throw new Error("That file isn't passport JSON.");
        onLoad(doc, file.name);
      }
    } catch (e) { onError(e.message); }
  }
  return (
    <label htmlFor={`${id}-file`} className={`cmp-drop${drag ? " is-drag" : ""}`}
           onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
           onDragLeave={() => setDrag(false)}
           onDrop={(e) => { e.preventDefault(); setDrag(false); handle(e.dataTransfer.files?.[0]); }}>
      <span className="cmp-drop-t">Drop or choose a file</span>
      <span className="v2-note">A saved passport <b>.json</b>, or its <b>QR</b> as a PNG/JPG</span>
      <input id={`${id}-file`} type="file" accept=".json,application/json,image/*" className="cmp-file"
             onChange={(e) => { handle(e.target.files?.[0]); e.target.value = ""; }} />
    </label>
  );
}

function PasteMethod({ id, onLoad, onError }) {
  const [text, setText] = useState("");
  function go() {
    const doc = extractPassport(text);
    if (!doc) { onError("That isn't passport JSON or a ?verify= link."); return; }
    onLoad(doc, text.includes("verify=") ? "verify link" : "pasted JSON");
  }
  return (
    <div className="cmp-paste">
      <label htmlFor={`${id}-paste`} className="v2-note">Passport JSON or a <code>?verify=</code> link</label>
      <textarea id={`${id}-paste`} value={text} onChange={(e) => setText(e.target.value)}
                placeholder='{"payload": …, "signature": …}  or  …/?verify=…' spellCheck={false} />
      <button type="button" className="v2-btn" onClick={go} disabled={!text.trim()}>Load passport</button>
    </div>
  );
}

function DeviceMethod({ id, onLoad, onError }) {
  const [cat, setCat] = useState(defaultProductCategory);
  const [age, setAge] = useState("");
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try {
      const scan = await scanDevice();
      const doc = await api.scanPassport({ ...scan, product_category: cat, device_age: age === "" ? null : Number(age), problem: "" });
      onLoad(doc, "This device (instant scan)", { product_category: cat, device_age: age, problem: "", persona: "general" });
    } catch (e) {
      onError(`Instant scan failed: ${e.message}`);
    } finally { setBusy(false); }
  }
  return (
    <div className="cmp-device">
      <p className="v2-note">Reads what this browser exposes — OS, cores, memory, graphics — and mints an instant passport. No files or history are read.</p>
      <div className="cmp-device-f">
        <label htmlFor={`${id}-cat`}>Type
          <select id={`${id}-cat`} value={cat} onChange={(e) => setCat(e.target.value)}>
            {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <label htmlFor={`${id}-age`}>Age (years)
          <input id={`${id}-age`} type="number" min="0" max="30" value={age} placeholder="e.g. 4"
                 onChange={(e) => setAge(e.target.value)} />
        </label>
      </div>
      <button type="button" className="v2-btn" onClick={go} disabled={busy}>
        {busy ? "Scanning…" : "Scan this device"}
      </button>
    </div>
  );
}

/* ---------------------------------------------------------- loaded card */
function gradeTone(g) {
  if (!g) return "none";
  return g.startsWith("A") ? "a" : g.startsWith("B") ? "b" : g.startsWith("C") ? "c" : "d";
}

function SlotCard({ name, slot, onClear }) {
  const p = slot.doc.payload;
  const t = trustState(slot.verify);
  const blend = slot.assessment?.blend;
  const flagged = t && !t.trusted;
  return (
    <section className={`cmp-slot cmp-loaded v2-card${flagged ? " is-flagged" : ""}`} aria-label={`Device ${name}`}>
      <div className="cmp-slot-top">
        <span className="cmp-letter" aria-hidden="true">{name}</span>
        <div className="cmp-dev">
          <h2 className="v2-h3">{deviceName(p)}</h2>
          <div className="cmp-id">{p.device_id} · {isDeep(p) ? "deep scan" : "instant scan"} · issued {p.issued || "—"}</div>
        </div>
        <button type="button" className="cmp-x" onClick={onClear}>Change<span className="sr-only"> device {name}</span></button>
      </div>

      <div className={`cmp-badge tone-${t?.tone || "wait"}`} role="status">
        {t ? (
          <>
            <span className="cmp-badge-dot" aria-hidden="true">{t.tone === "good" ? "✓" : "!"}</span>
            <span><b>{t.label}</b>{t.text ? ` — ${t.text}` : ""}</span>
          </>
        ) : <span>Checking signature…</span>}
      </div>
      {flagged && (
        <p className="cmp-flag-note">
          {slot.verify?.error ? "Signature could not be checked. " : "This passport does not verify. "}
          Its figures are shown for reference only and never counted as better.
        </p>
      )}

      <div className="cmp-score">
        {blend ? (
          <>
            <span className={`cmp-score-n v2-num grade-${gradeTone(blend.grade)}`}>{blend.combined_score}</span>
            <div className="cmp-score-side">
              <span className={`cmp-grade grade-${gradeTone(blend.grade)}`}>{blend.grade}</span>
              <span className="v2-note">
                {isDeep(p) ? `hardware trust ${p.trust_score}` : "hardware trust not measured — instant scans start from the assessment's 75 baseline"}
              </span>
            </div>
          </>
        ) : slot.assessErr ? (
          <span className="cmp-err">Assessment failed: {slot.assessErr}</span>
        ) : (
          <span className="v2-note"><span className="cmp-spin" aria-hidden="true" /> Assessing…</span>
        )}
      </div>
      <div className="v2-note cmp-src">Loaded from {slot.source}</div>
    </section>
  );
}

/* -------------------------------------------------------- the comparison */
function Comparison({ slots, names }) {
  const [a, b] = slots;
  const ta = trustState(a.verify), tb = trustState(b.verify);
  const ready = a.assessment && b.assessment && ta && tb;
  const ctx = {
    trusted: !!(ta?.trusted && tb?.trusted),
    sameTier: isDeep(a.doc.payload) === isDeep(b.doc.payload),
  };
  const sa = a.assessment?.blend?.combined_score, sb = b.assessment?.blend?.combined_score;
  const flags = [!!(ta && !ta.trusted), !!(tb && !tb.trusted)];
  const scoreWin = ready && ctx.trusted && ctx.sameTier && sa !== sb ? (sa > sb ? -1 : 1) : 0;

  return (
    <section className="cmp-result" aria-labelledby="cmp-res-h">
      <h2 className="v2-eyebrow" id="cmp-res-h">The comparison</h2>
      <p className="cmp-summary" aria-live="polite">
        {ready ? buildSummary(slots, names.map((n) => `Device ${n}`)) : "Checking signatures and running both assessments…"}
      </p>

      <div className="cmp-table" role="table" aria-label="Device comparison">
        <div className="cmp-tr cmp-thead" role="row">
          <span className="cmp-th" role="columnheader"><span className="sr-only">Measure</span></span>
          {[a, b].map((s, i) => (
            <span key={i} role="columnheader" className={`cmp-th${[ta, tb][i] && ![ta, tb][i].trusted ? " is-flagged" : ""}`}>
              <span className="cmp-letter sm" aria-hidden="true">{names[i]}</span>
              <span className="cmp-th-n">{deviceName(s.doc.payload)}</span>
              {[ta, tb][i] && ![ta, tb][i].trusted && <span className="cmp-th-flag">{[ta, tb][i].label}</span>}
            </span>
          ))}
        </div>

        <Row label="Score" A={sa != null ? { text: `${sa}`, note: a.assessment.blend.grade } : null}
             B={sb != null ? { text: `${sb}`, note: b.assessment.blend.grade } : null}
             win={scoreWin} pending={!a.assessment || !b.assessment} names={names} big flags={flags} />
        {ROWS.map((r) => {
          const A = r.get(a.doc.payload, a.assessment);
          const B = r.get(b.doc.payload, b.assessment);
          const needsAssess = ["support", "eol", "years", "action"].includes(r.key);
          const pending = needsAssess && (!a.assessment || !b.assessment);
          const win = ready ? rowWinner(r, A, B, ctx) : 0;
          return <Row key={r.key} label={r.label} A={A} B={B} win={win} pending={pending} names={names} flags={flags} />;
        })}
      </div>

      <p className="v2-note cmp-foot">
        A row is marked <span className="cmp-better-key">better</span> only when both passports
        measured it the same way and both verified; end-of-life risks less than 5 points apart are
        not ranked. Battery and disk health are shown as not measured: a browser scan cannot read them.
        {!ctx.sameTier && ready ? " These two are different depths, so those rows are shown, not ranked." : ""}
      </p>
    </section>
  );
}

function Cell({ c, isWin, pending, name, flagged }) {
  const fl = flagged ? " is-flagged" : "";
  if (pending && !c) return <span className={`cmp-td is-pending${fl}`} role="cell">…</span>;
  if (!c) return <span className={`cmp-td is-nm${fl}`} role="cell">not measured</span>;
  return (
    <span role="cell" className={`cmp-td${isWin ? " is-win" : ""}${c.nm ? " is-nm" : ""}${flagged ? " is-flagged" : ""}${c.tone ? ` tone-${c.tone}` : ""}`}>
      <span className="cmp-td-v">{c.text}</span>
      {c.note && <span className="cmp-td-n">{c.note}</span>}
      {isWin && <span className="cmp-win">better<span className="sr-only"> — device {name}</span></span>}
    </span>
  );
}

function Row({ label, A, B, win, pending, names, big, flags = [] }) {
  return (
    <div className={`cmp-tr${big ? " is-big" : ""}`} role="row">
      <span className="cmp-rh" role="rowheader">{label}</span>
      <Cell c={A} isWin={win === -1} pending={pending} name={names[0]} flagged={flags[0]} />
      <Cell c={B} isWin={win === 1} pending={pending} name={names[1]} flagged={flags[1]} />
    </div>
  );
}

/* ------------------------------------------------------------ empty state */
function EmptyHelp({ onNavigate }) {
  return (
    <section className="cmp-empty v2-card" aria-labelledby="cmp-empty-h">
      <h2 className="v2-h3" id="cmp-empty-h">Where do passports come from?</h2>
      <ol className="cmp-steps">
        <li><b>Scan a device.</b> The instant scan takes seconds in the browser.</li>
        <li><b>Keep the passport.</b> On the result, choose <i>Save passport (JSON)</i> or <i>Save QR</i>, or copy the verify link the QR opens.</li>
        <li><b>Load one into each slot above.</b></li>
      </ol>
      <div className="cmp-ctas">
        <button type="button" className="v2-btn" onClick={() => onNavigate?.("scan")}>Scan a device</button>
      </div>
    </section>
  );
}
