// The site shell: a story landing page plus a top-nav app, loaded by main.jsx.
// Pages from the original app are reused as-is inside the new shell.
import { lazy, Suspense, useCallback, useEffect, useId, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { api } from "../api.js";
import Scanner from "../Scanner.jsx";
import FindingsSkeleton from "../FindingsSkeleton.jsx";
import ErrorBoundary from "../ErrorBoundary.jsx";
import "./tokens.css";
import "./shell.css";
import "./skin.css";

function lazyWithReload(loader) {
  // Same stale-deploy guard as App.jsx: a chunk from a replaced build reloads once.
  return lazy(async () => {
    try {
      const mod = await loader();
      sessionStorage.removeItem("chunk-reload-attempted");
      return mod;
    } catch (err) {
      if (!sessionStorage.getItem("chunk-reload-attempted")) {
        sessionStorage.setItem("chunk-reload-attempted", "1");
        window.location.reload();
        return new Promise(() => {});
      }
      throw err;
    }
  });
}

const Landing = lazyWithReload(() => import("./Landing.jsx"));
const HowItWorks = lazyWithReload(() => import("./HowItWorks.jsx"));
const EsuCountdown = lazyWithReload(() => import("./EsuCountdown.jsx"));
const CarbonCalc = lazyWithReload(() => import("./CarbonCalc.jsx"));
const Findings = lazyWithReload(() => import("../Findings.jsx"));
const Verifier = lazyWithReload(() => import("../Verifier.jsx"));
const Sources = lazyWithReload(() => import("../Sources.jsx"));
const Thesis = lazyWithReload(() => import("../Thesis.jsx"));

//: Every route. `app: true` pages render inside the app frame (padded, with a
//: page width); the landing page owns the full bleed.
export const ROUTES = {
  home: { label: "Home" },
  how: { label: "How it works", app: true },
  scan: { label: "Scan", app: true },
  carbon: { label: "Carbon calculator", app: true },
  esu: { label: "Windows 10 countdown", app: true },
  verify: { label: "Verify a passport", app: true },
  thesis: { label: "The Argument", app: true },
  findings: { label: "Our Research", app: true },
  sources: { label: "Data Sources", app: true },
};

//: The top bar. Groups open as menus; single items are plain links.
export const NAV = [
  { id: "scan" },
  { label: "Tools", items: ["carbon", "esu"] },
  { id: "verify" },
  { label: "Evidence", items: ["how", "thesis", "findings", "sources"] },
];

function routeFromLocation() {
  if (new URLSearchParams(window.location.search).has("verify")) return "verify";
  const h = window.location.hash.replace(/^#\/?/, "");
  return h in ROUTES ? h : "home";
}

export default function AppV2() {
  return (
    <Shell />
  );
}

function Shell() {
  const [view, setView] = useState(routeFromLocation);
  // Counts requests for a new scan; each one tells the Scanner to start over.
  // The rule: tabs never discard a result, and every button labelled "scan"
  // starts a scan. So the plain "Scan" tab leaves the current result alone,
  // while "Scan a device" and the scan buttons on other pages bump this.
  const [freshScan, setFreshScan] = useState(0);

  const navigate = useCallback((next) => {
    if (!(next in ROUTES)) return;
    // Keep the ?verify= query out of every other page's URL.
    const url = `${window.location.pathname}#/${next}`;
    if (window.location.hash !== `#/${next}` || window.location.search) {
      window.history.pushState(null, "", url);
    }
    const apply = () => { setView(next); window.scrollTo({ top: 0 }); };
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || typeof document.startViewTransition !== "function") apply();
    else document.startViewTransition(() => flushSync(apply));
  }, []);

  // What pages get as onNavigate: navigate(next), or navigate("scan", { fresh: true })
  // from a button that promises a scan.
  const openPage = useCallback((next, opts) => {
    if (next === "scan" && opts?.fresh) setFreshScan((n) => n + 1);
    navigate(next);
  }, [navigate]);

  useEffect(() => {
    const onPop = () => setView(routeFromLocation());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => { api.warm(); }, []);
  useEffect(() => {
    document.title = view === "home" ? "Afterlife — should this device continue existing?"
      : `${ROUTES[view].label} · Afterlife`;
  }, [view]);

  const page = ROUTES[view];
  return (
    <div className="v2">
      <a className="v2-skip" href="#v2-main" onClick={(e) => {
        e.preventDefault();
        document.getElementById("v2-main")?.focus();
      }}>Skip to content</a>
      <TopNav view={view} navigate={navigate} newScan={() => setFreshScan((n) => n + 1)} />
      <main id="v2-main" tabIndex={-1} className={page.app ? "v2-app v2-wrap" : "v2-bleed"}>
        {/* Scanner stays mounted so a result survives navigating away. It sits
            outside the per-page boundary below: that one is keyed by view, so
            anything inside it is rebuilt (and its state lost) on every page change. */}
        <div style={{ display: view === "scan" ? "contents" : "none" }}>
          <ErrorBoundary>
            <Scanner onNavigate={navigate} freshScan={freshScan} />
          </ErrorBoundary>
        </div>
        <ErrorBoundary key={view}>
          <Suspense fallback={<FindingsSkeleton />}>
            {view === "home" && <Landing onNavigate={openPage} />}
            {view === "how" && <HowItWorks onNavigate={openPage} />}
            {view === "esu" && <EsuCountdown onNavigate={openPage} />}
            {view === "carbon" && <CarbonCalc onNavigate={openPage} />}
            {view === "findings" && <Findings />}
            {view === "verify" && <Verifier onNavigate={openPage} />}
            {view === "sources" && <Sources />}
            {view === "thesis" && <Thesis onNavigate={openPage} />}
          </Suspense>
        </ErrorBoundary>
      </main>
      <Footer view={view} navigate={navigate} />
    </div>
  );
}

// The logo image IS the "A" of the wordmark (the original sidebar renders it
// followed by "fterlife"), so the text here starts at "f". Screen readers get
// the button's label instead of the split word.
function Brand({ onClick, className = "v2-brand", label = "Afterlife home" }) {
  return (
    <button type="button" className={className} onClick={onClick} aria-label={label}>
      <img src="/afterlife-logo.png" alt="" width="28" height="28" />
      <span aria-hidden="true">fterlife</span>
    </button>
  );
}

function useScrolled(threshold = 8) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    let raf = 0;
    const read = () => { raf = 0; setScrolled(window.scrollY > threshold); };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(read); };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); if (raf) cancelAnimationFrame(raf); };
  }, [threshold]);
  return scrolled;
}

function TopNav({ view, navigate, newScan }) {
  const [open, setOpen] = useState(null);       // label of the open desktop group
  const [mobile, setMobile] = useState(false);  // mobile panel
  const scrolled = useScrolled();
  const navRef = useRef(null);
  const burgerRef = useRef(null);
  const panelRef = useRef(null);

  const go = (id) => { setOpen(null); setMobile(false); navigate(id); };
  const scanFresh = () => { newScan(); go("scan"); };

  // Outside click closes whichever menu is open.
  useEffect(() => {
    if (!open && !mobile) return;
    const onDown = (e) => {
      if (navRef.current && !navRef.current.contains(e.target)) { setOpen(null); setMobile(false); }
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open, mobile]);

  // Mobile panel: Escape closes and hands focus back to the burger; the page
  // under it does not scroll; widening past the breakpoint closes it.
  useEffect(() => {
    if (!mobile) return;
    const onKey = (e) => {
      if (e.key === "Escape") { setMobile(false); burgerRef.current?.focus(); }
    };
    const mq = window.matchMedia("(min-width: 901px)");
    const onMq = () => { if (mq.matches) setMobile(false); };
    document.addEventListener("keydown", onKey);
    mq.addEventListener?.("change", onMq);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.querySelector("button")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      mq.removeEventListener?.("change", onMq);
      document.body.style.overflow = prev;
    };
  }, [mobile]);

  return (
    <header ref={navRef} className={`v2-nav${scrolled ? " is-scrolled" : ""}${mobile ? " is-menu" : ""}`}>
      <div className="v2-nav-inner v2-wrap">
        <Brand onClick={() => go("home")} />
        <nav className="v2-links" aria-label="Main">
          {NAV.map((n) => n.id ? (
            <button key={n.id} type="button" className={`v2-link${view === n.id ? " is-active" : ""}`}
                    aria-current={view === n.id ? "page" : undefined} onClick={() => go(n.id)}>
              {ROUTES[n.id].label}
            </button>
          ) : (
            <NavGroup key={n.label} group={n} view={view} go={go}
                      open={open === n.label}
                      setOpen={(v) => setOpen(v ? n.label : (cur) => (cur === n.label ? null : cur))} />
          ))}
        </nav>
        <div className="v2-nav-end">
          <button type="button" className="v2-btn v2-nav-cta" onClick={scanFresh}>Scan a device</button>
          <button ref={burgerRef} type="button" className={`v2-burger${mobile ? " is-open" : ""}`}
                  aria-label={mobile ? "Close menu" : "Open menu"} aria-expanded={mobile}
                  aria-controls="v2-mpanel" onClick={() => { setOpen(null); setMobile(!mobile); }}>
            <span aria-hidden="true" /><span aria-hidden="true" /><span aria-hidden="true" />
          </button>
        </div>
      </div>
      {mobile && (
        <div id="v2-mpanel" ref={panelRef} className="v2-mpanel">
          <nav className="v2-mpanel-inner v2-wrap" aria-label="All pages">
            <div className="v2-mgroup">
              {["home", ...NAV.filter((n) => n.id).map((n) => n.id)].map((id) => (
                <MobileLink key={id} id={id} view={view} go={go} />
              ))}
            </div>
            {NAV.filter((n) => n.items).map((g) => (
              <div key={g.label} className="v2-mgroup">
                <div className="v2-eyebrow">{g.label}</div>
                {g.items.map((id) => <MobileLink key={id} id={id} view={view} go={go} />)}
              </div>
            ))}
            <button type="button" className="v2-btn v2-mpanel-cta" onClick={scanFresh}>Scan a device</button>
          </nav>
        </div>
      )}
    </header>
  );
}

function MobileLink({ id, view, go }) {
  return (
    <button type="button" className={`v2-mlink${view === id ? " is-active" : ""}`}
            aria-current={view === id ? "page" : undefined} onClick={() => go(id)}>
      {ROUTES[id].label}
    </button>
  );
}

// A disclosure menu: click or hover opens it; ArrowDown/Up/Home/End move
// between items; Escape closes and returns focus to the trigger; tabbing out
// closes it.
function NavGroup({ group, view, go, open, setOpen }) {
  const menuId = useId();
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const hoverTimer = useRef(0);
  const hoverOpenedAt = useRef(0);
  const active = group.items.includes(view);

  const items = () => [...(menuRef.current?.querySelectorAll("button") ?? [])];
  const focusItem = (i) => {
    const list = items();
    if (!list.length) return;
    list[(i + list.length) % list.length].focus();
  };
  const openAndFocus = (i) => {
    setOpen(true);
    // The menu is always in the DOM; it only becomes visible, so focus after paint.
    requestAnimationFrame(() => focusItem(i));
  };

  const onTriggerKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); openAndFocus(0); }
    else if (e.key === "ArrowUp") { e.preventDefault(); openAndFocus(-1); }
    else if (e.key === "Escape" && open) { e.preventDefault(); setOpen(false); }
  };
  const onMenuKey = (e) => {
    const list = items();
    const i = list.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); focusItem(i + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); focusItem(i - 1); }
    else if (e.key === "Home") { e.preventDefault(); focusItem(0); }
    else if (e.key === "End") { e.preventDefault(); focusItem(-1); }
    else if (e.key === "Escape") { e.preventDefault(); setOpen(false); triggerRef.current?.focus(); }
  };
  const onBlur = (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false);
  };
  // Hover only for a real mouse; touch taps go through onClick.
  const onEnter = (e) => {
    if (e.pointerType !== "mouse") return;
    clearTimeout(hoverTimer.current);
    if (!open) hoverOpenedAt.current = Date.now();
    setOpen(true);
  };
  const onLeave = (e) => {
    if (e.pointerType !== "mouse") return;
    clearTimeout(hoverTimer.current);
    hoverTimer.current = setTimeout(() => setOpen(false), 140);
  };
  useEffect(() => () => clearTimeout(hoverTimer.current), []);

  return (
    <div className={`v2-group${open ? " is-open" : ""}`} onBlur={onBlur}
         onPointerEnter={onEnter} onPointerLeave={onLeave}>
      <button ref={triggerRef} type="button"
              className={`v2-link v2-group-trigger${active ? " is-active" : ""}`}
              aria-expanded={open} aria-controls={menuId}
              onClick={() => {
                // A click right after hover opened the menu should not shut it again.
                if (open && Date.now() - hoverOpenedAt.current < 600) return;
                setOpen(!open);
              }} onKeyDown={onTriggerKey}>
        {group.label}
        <svg className="v2-caret" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <div id={menuId} ref={menuRef} className="v2-menu" onKeyDown={onMenuKey} hidden={!open}>
        {group.items.map((id) => (
          <button key={id} type="button" className={view === id ? "is-active" : ""}
                  aria-current={view === id ? "page" : undefined} onClick={() => go(id)}>
            {ROUTES[id].label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Footer({ view, navigate }) {
  const cols = [
    { label: "Product", items: ["home", ...NAV.filter((n) => n.id).map((n) => n.id)] },
    ...NAV.filter((n) => n.items).map((g) => ({ label: g.label, items: g.items })),
  ];
  return (
    <footer className="v2-footer">
      <div className="v2-wrap v2-footer-inner">
        <div className="v2-footer-brand">
          <Brand className="v2-brand v2-brand-foot" onClick={() => navigate("home")} />
          <p className="v2-footer-tag">Obsolete? Says who.</p>
          <p className="v2-note">Real data, signed passports, no vibes. Every verdict is
            computed; the written summary only explains it.</p>
        </div>
        {cols.map((c) => (
          <nav key={c.label} className="v2-footer-col" aria-label={c.label}>
            <div className="v2-eyebrow">{c.label}</div>
            {c.items.map((id) => (
              <button key={id} type="button" className={`v2-foot-link${view === id ? " is-active" : ""}`}
                      aria-current={view === id ? "page" : undefined}
                      onClick={() => navigate(id)}>{ROUTES[id].label}</button>
            ))}
          </nav>
        ))}
      </div>
      <div className="v2-wrap v2-footer-base">
        <span>Keep, repair, sell or recycle — decided on evidence.</span>
      </div>
    </footer>
  );
}
