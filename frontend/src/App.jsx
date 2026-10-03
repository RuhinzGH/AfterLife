import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { api } from "./api.js";
import Scanner from "./Scanner.jsx";
import FindingsSkeleton from "./FindingsSkeleton.jsx";
import ErrorBoundary from "./ErrorBoundary.jsx";

// A lazy chunk references a specific hashed filename from the build that was
// live when the page loaded. If a new version gets deployed while someone's
// tab is still open (this app redeploys often), that exact file no longer
// exists once they click a tab that hasn't loaded yet -- "Failed to fetch
// dynamically imported module," a dead end with no obvious fix for a visitor
// who doesn't know to hard-refresh. A stale build is only ever fixed by
// actually reloading, so this does that automatically, once -- the
// sessionStorage flag stops it from reload-looping if the failure is a real
// network problem a refresh won't solve.
function lazyWithReload(loader) {
  return lazy(async () => {
    try {
      const mod = await loader();
      sessionStorage.removeItem("chunk-reload-attempted"); // a later deploy can trigger this again
      return mod;
    } catch (err) {
      const key = "chunk-reload-attempted";
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, "1");
        window.location.reload();
        return new Promise(() => {}); // reloading now; never resolve into a crash
      }
      throw err;
    }
  });
}


// Scanner is the default, most-common view -- loaded eagerly. Everything else
// only loads once someone actually clicks its nav tab, which keeps the initial
// bundle to the part almost every visitor uses.
// Findings is the heaviest view -- every research card, the provenance panel
// and the chart helpers -- and it is not the default tab. Splitting it means
// a visitor who only ever scans their device never downloads any of it.
const Findings = lazyWithReload(() => import("./Findings.jsx"));
const Verifier = lazyWithReload(() => import("./Verifier.jsx"));
const Sources = lazyWithReload(() => import("./Sources.jsx"));
const Thesis = lazyWithReload(() => import("./Thesis.jsx"));

function TabLoading() {
  return <div className="center"><span className="spinner" /> loading…</div>;
}

// Grouped, not flat. Five destinations was the point at which a single column
// stopped communicating anything about the product's shape -- "Passport
// Verifier" and "Data Sources" sat side by side as peers while doing entirely
// different jobs for different people.
//
// The grouping says what the product actually is: you bring a device to it,
// you keep a record of what it found, or you check the evidence underneath.
// The number keys still run 1..n straight down the list regardless of group,
// because someone reaching for a shortcut is counting rows, not sections.
const NAV_GROUPS = [
  {
    heading: "Your device",
    items: [
      { id: "scan", label: "Scan & Assess", glyph: "◉" },
    ],
  },
  {
    heading: "Verify",
    items: [
      { id: "verify", label: "Passport Verifier", glyph: "✓" },
    ],
  },
  {
    heading: "The evidence",
    items: [
      { id: "thesis", label: "The Argument", glyph: "✦" },
      { id: "findings", label: "Our Research", glyph: "◆" },
      { id: "sources", label: "Data Sources", glyph: "❖" },
    ],
  },
];

//: Flattened once, here, so the keyboard shortcuts and the group rendering can
//: never disagree about which tab is number 3.
const NAV = NAV_GROUPS.flatMap((g) => g.items);

export default function App() {
  const isVerifyLink = new URLSearchParams(window.location.search).has("verify");
  const [view, setView] = useState(isVerifyLink ? "verify" : "scan");

  // Tabs used to swap instantly, which made a whole page of content appear with
  // no sense of where it came from. The View Transitions API cross-fades the two
  // states on the compositor for roughly nothing.
  //
  // flushSync is load-bearing: startViewTransition snapshots the DOM when its
  // callback returns, and React would otherwise batch the state update to after
  // that point, so the transition would capture no change at all.
  //
  // Everything degrades to a plain setView -- browsers without the API, and
  // anyone who has asked for reduced motion, for whom a full-page cross-fade is
  // precisely the motion they turned off.
  const navigate = useCallback((next) => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || typeof document.startViewTransition !== "function") {
      setView(next);
      return;
    }
    document.startViewTransition(() => flushSync(() => setView(next)));
  }, []);
  // Wake the sleeping backend now, not when the visitor first needs an answer.
  useEffect(() => { api.warm(); }, []);

  // Number keys switch tabs. Guarded three ways: no modifier held (Ctrl+1
  // belongs to the browser's own tab switching), not while typing in a field,
  // and not while a dialog is up.
  //
  // The range is DERIVED from NAV rather than written out. It used to be the
  // literal "1234", and adding a fifth destination rendered a "5" hint on the
  // new tab with nothing behind it -- a shortcut the interface advertised and
  // did not have. Deriving it means that can never drift again.
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target;
      if (t.closest?.("input, textarea, select, [contenteditable], [role='dialog']")) return;
      const i = Number(e.key) - 1;
      if (Number.isInteger(i) && i >= 0 && i < NAV.length) navigate(NAV[i].id);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navigate]);
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">
          <img src="/afterlife-logo.png" alt="Afterlife" className="logo-mark" />
          <span className="mark">fterlife</span>
        </div>
        <div className="tag">Obsolete? Says who?</div>
        <nav className="nav" aria-label="Sections">
          {NAV_GROUPS.map((g) => (
            <div className="nav-group" key={g.heading}>
              {/* A real heading element rather than a styled div: a screen
                  reader user navigating by landmark gets the same grouping a
                  sighted user gets from the spacing. */}
              <h2 className="nav-heading">{g.heading}</h2>
              {g.items.map((n) => {
                const i = NAV.findIndex((x) => x.id === n.id);
                return (
                  <button key={n.id} className={view === n.id ? "active" : ""}
                          aria-current={view === n.id ? "page" : undefined}
                          onClick={() => navigate(n.id)}
                          title={`${n.label} — press ${i + 1}`}>
                    <span className="glyph">{n.glyph}</span>
                    {n.label}
                    {i < 9 && <span className="key" aria-hidden="true">{i + 1}</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="foot">
          Should this device<br />continue existing?<br /><br />
          Real data · signed passports<br />no vibes.
        </div>
      </aside>
      <main className="main">
        <ErrorBoundary key={view}>
          {/* Scanner stays mounted and is only hidden (not unmounted) when you
              switch tabs, so a scan result survives navigating away and back --
              it only resets on a real page reload or an explicit new scan. */}
          <div style={{ display: view === "scan" ? "contents" : "none" }}>
            <Scanner onNavigate={navigate} />
          </div>
          <Suspense fallback={<FindingsSkeleton />}>
            {view === "findings" && <Findings />}
            {view === "verify" && <Verifier onNavigate={navigate} />}
            {view === "sources" && <Sources />}
            {view === "thesis" && <Thesis onNavigate={navigate} />}
          </Suspense>
        </ErrorBoundary>
      </main>
    </div>
  );
}

/* FindingsSkeleton now lives in its own module -- Findings.jsx needs it too, and
   it cannot be imported across the lazy boundary in either direction without
   either undoing the code split or making the modules circular.

   Loading and ErrState used to be defined here as well. They were only ever
   rendered by the findings view, which carries its own copies since the split,
   so the ones here were unreachable duplicates and are gone. */
