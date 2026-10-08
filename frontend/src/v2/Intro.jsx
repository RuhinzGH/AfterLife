// Opening animation for the redesigned full edition, about 3.7 seconds.
//
//   0.0s  dark; the question fades in above an empty ring
//   0.2s  a gradient arc draws itself round the ring behind a scanning sweep,
//         ticks light in order, hex glyphs flicker either side
//   1.5s  the ring seals: a flash, a guilloche stamp lands, the mark appears
//   1.9s  "Obsolete?"   2.3s  "Says who?"
//   2.9s  the stage zooms through the viewer, then the dark lifts (gone 3.7s)
//
// The flickering glyphs are decoration. They carry no label and are not read
// from anything -- nothing on screen claims to be a measurement.
//
// Plays once per browser session and never under prefers-reduced-motion (the
// rule is introGate.js, shared with the core edition's RiftIntro). Skip button,
// click anywhere, Escape or Enter end it early. The visual layer is aria-hidden;
// only the Skip button is exposed, and focus is never moved or trapped.
import { useCallback, useEffect, useState } from "react";
import { markIntroPlayed, shouldPlayIntro } from "../introGate.js";
import "./intro.css";

const FALLBACK_MS = 4300;   // animationend should arrive at ~3.7s; this is the net
const LEAVE_MS = 320;       // fade length when skipped
const FINAL_ANIMATION = "v2i-out";

const TICKS = 72;
const R = 100;              // arc radius in the 240x240 viewBox

// Guilloche rosette for the seal: rotated ellipses, like the fine line-work
// printed on passports and banknotes. Built once at module load.
const ROSETTE = Array.from({ length: 18 }, (_, i) => i * 10);

const HEX = "0123456789ABCDEF";
const randHex = (n) => {
  let s = "";
  for (let i = 0; i < n; i += 1) s += HEX[(Math.random() * 16) | 0];
  return s;
};
const glyphLine = () => `${randHex(2)} ${randHex(2)} ${randHex(4)}`;

// Decorative glyph columns. Re-renders only itself while it flickers, then stops.
function Glyphs({ side }) {
  const [lines, setLines] = useState(() => Array.from({ length: 5 }, glyphLine));
  useEffect(() => {
    const iv = setInterval(() => setLines(Array.from({ length: 5 }, glyphLine)), 75);
    const stop = setTimeout(() => clearInterval(iv), 1600);
    return () => { clearInterval(iv); clearTimeout(stop); };
  }, []);
  return (
    <div className={`v2i-glyphs is-${side}`}>
      {lines.map((l, i) => <span key={i} style={{ "--i": i }}>{l}</span>)}
    </div>
  );
}

function readGate() {
  if (typeof window === "undefined") return false;
  const reduced = !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  let store = null;
  try { store = window.sessionStorage; } catch { /* blocked: play, never crash */ }
  return shouldPlayIntro(store, reduced);
}

export default function Intro() {
  const [play] = useState(readGate);
  const [phase, setPhase] = useState(play ? "on" : "done"); // on | leaving | done

  const finish = useCallback(() => setPhase("done"), []);
  // Skipping fades out quickly rather than cutting to the page.
  const skip = useCallback(() => setPhase((p) => (p === "on" ? "leaving" : p)), []);
  useEffect(() => {
    if (phase !== "leaving") return undefined;
    const t = setTimeout(finish, LEAVE_MS);
    return () => clearTimeout(t);
  }, [phase, finish]);

  // Mark played the moment it starts; listen for keys; lock scroll while shown.
  useEffect(() => {
    if (!play) return undefined;
    try { markIntroPlayed(window.sessionStorage); } catch { /* blocked */ }
    const onKey = (e) => { if (e.key === "Escape" || e.key === "Enter") skip(); };
    window.addEventListener("keydown", onKey);
    const t = setTimeout(finish, FALLBACK_MS);
    return () => {
      window.removeEventListener("keydown", onKey);
      clearTimeout(t);
    };
  }, [play, skip, finish]);

  const visible = phase !== "done";
  useEffect(() => {
    if (!visible) return undefined;
    const root = document.documentElement;
    const prev = root.style.overflow;
    root.style.overflow = "hidden";
    return () => { root.style.overflow = prev; };
  }, [visible]);

  if (!visible) return null;

  const onEnd = (e) => {
    if (e.animationName === FINAL_ANIMATION && e.target === e.currentTarget) finish();
  };

  return (
    <div
      className={`v2-intro${phase === "leaving" ? " is-leaving" : ""}`}
      onClick={skip}
      onAnimationEnd={onEnd}
    >
      <div className="v2i-visual" aria-hidden="true">
        <div className="v2i-grid" />
        <div className="v2i-stage">
          <p className="v2i-question">Should this device continue existing?</p>

          <div className="v2i-ring">
            <div className="v2i-halo" />
            <div className="v2i-sweep" />
            <svg viewBox="0 0 240 240" className="v2i-svg">
              <defs>
                <linearGradient id="v2i-g" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stopColor="#7c3aed" />
                  <stop offset="0.55" stopColor="#2563eb" />
                  <stop offset="1" stopColor="#059669" />
                </linearGradient>
              </defs>
              <g className="v2i-ticks">
                {Array.from({ length: TICKS }, (_, i) => {
                  const long = i % 6 === 0;
                  return (
                    <line
                      key={i}
                      x1="120" y1={long ? 4 : 7} x2="120" y2="13"
                      transform={`rotate(${(i * 360) / TICKS} 120 120)`}
                      style={{ "--d": `${200 + (i / TICKS) * 1250}ms` }}
                      className={long ? "is-long" : undefined}
                    />
                  );
                })}
              </g>
              <circle cx="120" cy="120" r={R} className="v2i-track" />
              <circle
                cx="120" cy="120" r={R} pathLength="1"
                className="v2i-arc" stroke="url(#v2i-g)"
                transform="rotate(-90 120 120)"
              />
              <g className="v2i-rosette" stroke="url(#v2i-g)">
                {ROSETTE.map((a) => (
                  <ellipse key={a} cx="120" cy="120" rx="80" ry="34" transform={`rotate(${a} 120 120)`} />
                ))}
                <circle cx="120" cy="120" r="86" />
                <circle cx="120" cy="120" r="89" strokeDasharray="1.2 2.4" />
              </g>
            </svg>
            <div className="v2i-core" />
            <img className="v2i-logo" src="/afterlife-logo.png" alt="" width="96" height="96" />
            <div className="v2i-flash" />
            <Glyphs side="l" />
            <Glyphs side="r" />
          </div>

          <h2 className="v2i-tag">
            <span className="v2i-line is-a">Obsolete?</span>
            <span className="v2i-line is-b"><span className="v2i-grad">Says who?</span></span>
          </h2>

          <div className="v2i-word">
            <img src="/afterlife-logo.png" alt="" width="28" height="28" />
            <span>fterlife</span>
          </div>
        </div>
      </div>

      <button
        type="button"
        className="v2i-skip"
        onClick={(e) => { e.stopPropagation(); skip(); }}
      >
        Skip intro
      </button>
    </div>
  );
}
