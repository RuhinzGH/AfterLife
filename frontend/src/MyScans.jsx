import { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { useAuth } from "./AuthContext.jsx";
import { ChevronUp, ChevronDown } from "./icons.jsx";
import { currentDeviceCategory } from "./deviceCategory.js";
import { b64encodeCompressed } from "./b64.js";
import { getNickname, isThisDevice, relativeTime, setNickname, getPrimary, setPrimary } from "./deviceStore.js";
import ScoreHistory from "./ScoreHistory.jsx";

const CATEGORY_META = {
  mobile: { label: "Phone", icon: "📱" },
  tablet: { label: "Tablet", icon: "📱" },
  desktop: { label: "Laptop / desktop", icon: "💻" },
  other: { label: "Other devices", icon: "🖥" },
};

// A deep scan only ever runs via the PowerShell collector, which only exists for
// Windows -- so its category is unambiguous regardless of what the passport
// payload does or doesn't record. An instant scan carries whatever the user
// picked in "Complete the picture" (defaulted to match the scanning device
// itself -- see deviceCategory.js -- so this is trustworthy, not just whatever
// the dropdown happened to default to).
function scanCategory(s) {
  if (s.scan_type === "deep") return "desktop";
  const pc = s.passport?.payload?.product_category;
  if (pc === "Mobile") return "mobile";
  if (pc === "Tablet") return "tablet";
  if (pc === "Laptop" || pc === "Desktop computer") return "desktop";
  return "other";
}

function deviceTitle(p) {
  return p.device_name || p.make_model || p.product_category || "Device";
}

// Grade -> the same colour language the rest of the app already uses for grades.
// Inventing a second set of thresholds for this one view would mean a card could
// read amber next to a report reading green for the same machine.
function gradeTone(grade) {
  if (!grade) return "none";
  if (grade.startsWith("A")) return "excellent";
  if (grade.startsWith("B")) return "good";
  if (grade.startsWith("C")) return "fair";
  return "poor";
}

// Flatten a grouped device into the scalar fields the table sorts and compares
// on. One place, so the fleet table and the comparison panel can never disagree
// about what "years left" or "battery" means for the same machine.
function deviceRow(d) {
  const p = d.primary.passport?.payload || {};
  const a = d.primary.passport?.assessment || {};
  const bh = p.battery_health ? parseFloat(String(p.battery_health)) : null;
  return {
    id: d.deviceId,
    device: d,
    name: getNickname(d.deviceId) || deviceTitle(p),
    detected: deviceTitle(p),
    score: a.blend?.combined_score ?? null,
    grade: a.blend?.grade || null,
    tone: gradeTone(a.blend?.grade),
    years: a.pipeline?.estimated_remaining_years ?? null,
    os: p.os || null,
    cpu: p.cpu || null,
    ramGb: p.ram_gb ?? null,
    storage: p.storage_health ? `${p.storage} · ${p.storage_health}` : p.storage || null,
    battery: p.battery_health || null,
    batteryPct: Number.isFinite(bh) ? bh : null,
    age: p.age_years ?? null,
    type: d.primary.scan_type,
    checked: d.lastChecked,
  };
}

// When a device is worth a fresh look. CHARON already says "I'd reassess then"
// about the support horizon; this is that, made actionable -- surfaced on the
// card and summarised at the top, so a decaying machine doesn't just sit in the
// list looking the same as the day it was scanned. In-app only; an emailed
// version needs a sender + scheduler and is a separate step.
const STALE_MONTHS = 6;
function reassessReason(d) {
  const p = d.primary.passport?.payload || {};
  const a = d.primary.passport?.assessment || {};
  const sh = a.support_horizon;
  const bh = p.battery_health ? parseFloat(String(p.battery_health)) : null;
  const months = (Date.now() - new Date(d.lastChecked)) / (1000 * 60 * 60 * 24 * 30.44);
  if (sh?.is_eol) return "security support has ended";
  if (sh && sh.months_remaining != null && sh.months_remaining <= 3) return "security support ends within 3 months";
  if (Number.isFinite(bh) && bh < 60) return `battery health is down to ${Math.round(bh)}%`;
  if (months >= STALE_MONTHS) return `last checked ${Math.round(months)} months ago`;
  return null;
}

/* ------------------------------------------------------------------ grouping */
// One card per physical machine, not one per scan. A laptop scanned six times is
// one thing that changed six times -- six cards for it is a list of events
// pretending to be a list of devices, which is what made this page unreadable at
// 17 rows for a single PC.
//
// Within a device, a DEEP scan always wins the card even if an instant scan is
// newer: the instant one cannot see battery wear or disk health, so letting it
// take over would make the card quietly lose detail over time and look like a
// bug. Both timestamps are kept and shown when they differ.
//
// An instant scan and a deep scan of one machine carry different IDs (browser
// facts vs maker/model/CPU). A saved scan lists the other IDs scanned from the
// same browser (`links`), and a browser only ever scans the machine it runs on,
// so linked IDs are joined into one card here.
export function groupDevices(scans) {
  const idOf = (s) => s.passport?.payload?.device_id || `row-${s.id}`;
  const parent = new Map();
  const find = (x) => { while (parent.get(x) !== x) { parent.set(x, parent.get(parent.get(x))); x = parent.get(x); } return x; };
  for (const s of scans) parent.set(idOf(s), idOf(s));
  for (const s of scans) {
    for (const other of s.passport?.links || []) {
      if (parent.has(other)) parent.set(find(other), find(idOf(s)));
    }
  }
  const byDevice = new Map();
  for (const s of scans) {
    const root = find(idOf(s));
    if (!byDevice.has(root)) byDevice.set(root, []);
    byDevice.get(root).push(s);
  }

  const devices = [];
  for (const history of byDevice.values()) {
    const sorted = [...history].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    const lastDeep = sorted.find((s) => s.scan_type === "deep");
    const primary = lastDeep || sorted[0];
    devices.push({
      deviceId: idOf(primary),
      ids: [...new Set(sorted.map(idOf))],
      primary,
      history: sorted,
      lastChecked: sorted[0].created_at,
      lastDeep: lastDeep?.created_at || null,
      category: scanCategory(primary),
    });
  }
  devices.sort((a, b) => new Date(b.lastChecked) - new Date(a.lastChecked));
  return devices;
}

/* --------------------------------------------------------------------- page */
export default function MyScans({ onNavigate }) {
  const { user, session, loading, openAuthModal } = useAuth();
  const [scans, setScans] = useState(null);
  const [err, setErr] = useState(null);
  const [query, setQuery] = useState("");
  // Which card is expanded. Held here, not inside each card, so opening one
  // collapses the rest -- an accordion, so the page never becomes a long scroll
  // of stacked expanded specs (which is what made 3+ devices unreadable).
  const [openId, setOpenId] = useState(null);
  // Remove a device card (every ID joined into it) from the account. Asked
  // once, because it can't be undone: the signed passports are deleted.
  async function removeDevice(d) {
    if (!window.confirm("Remove this device and all its saved scans from My Scans? This can't be undone.")) return;
    try {
      for (const id of d.ids || [d.deviceId]) {
        if (/^AFL-/.test(id)) await api.removeDevice(id, session.access_token);
      }
      setScans((list) => (list || []).filter((s) => !(d.ids || [d.deviceId]).includes(s.passport?.payload?.device_id)));
      setOpenId(null);
    } catch (e) {
      // Shown where the person is looking, not only at the top of the page.
      window.alert(`Couldn't remove it: ${e.message}`);
      setErr(`Couldn't remove it: ${e.message}`);
    }
  }
  // Quick filters that sit beside the text search. `tone` buckets by grade
  // (the same excellent/good/fair/poor language the cards colour by), `type`
  // is instant-vs-deep, `attention` surfaces only the machines a person would
  // actually want to act on -- faster than typing for anyone with a few devices.
  const [filters, setFilters] = useState({ tone: null, type: null, attention: false });
  // Cards are the browsing view; the table is the fleet view -- sortable columns
  // for anyone past ~6 devices, where a card grid stops scaling. Comparison is a
  // table activity (pick a few machines, see them side by side to decide which to
  // keep as primary vs sell), so selection lives with the table.
  const [view, setView] = useState("cards");
  const [sort, setSort] = useState({ key: "checked", dir: "desc" });
  const [selected, setSelected] = useState([]);
  const [comparing, setComparing] = useState(false);
  const [nudgeDismissed, setNudgeDismissed] = useState(false);
  // User-designated primary (daily driver), kept in localStorage. Mirrored into
  // state so toggling a card's star re-renders the badges immediately.
  const [primaryId, setPrimaryId] = useState(() => getPrimary());
  const togglePrimary = (id) => {
    const next = primaryId === id ? null : id;
    setPrimary(next);
    setPrimaryId(next);
  };

  useEffect(() => {
    if (!session) return;
    api.myScans(session.access_token).then((r) => setScans(r.scans)).catch((e) => setErr(e.message));
  }, [session]);

  const devices = useMemo(() => (scans ? groupDevices(scans) : null), [scans]);

  const filtered = useMemo(() => {
    if (!devices) return null;
    const q = query.trim().toLowerCase();
    return devices.filter((d) => {
      const p = d.primary.passport?.payload || {};
      const blend = d.primary.passport?.assessment?.blend;
      const tone = gradeTone(blend?.grade);
      if (filters.tone && tone !== filters.tone) return false;
      if (filters.type && d.primary.scan_type !== filters.type) return false;
      if (filters.attention && !(tone === "fair" || tone === "poor")) return false;
      if (!q) return true;
      return [
        getNickname(d.deviceId), deviceTitle(p), p.make_model, p.os, p.cpu,
        blend?.grade, blend?.combined_score,
      ].filter(Boolean).join(" ").toLowerCase().includes(q);
    });
  }, [devices, query, filters]);

  const anyFilter = query.trim() || filters.tone || filters.type || filters.attention;
  const toggleFilter = (key, value) =>
    setFilters((f) => ({ ...f, [key]: f[key] === value ? (typeof value === "boolean" ? false : null) : value }));

  if (loading) return <div className="center"><span className="spinner" /> loading…</div>;

  if (!user) {
    return (
      <div className="view">
        <div>
          <div className="eyebrow">Your account</div>
          <h1 className="title">Scan history</h1>
          <p className="lede">
            Sign in to keep every device you've scanned, so a future one has something to be
            compared against.
          </p>
        </div>
        <div className="empty-state">
          <div className="empty-icon">🔒</div>
          <div className="empty-title">You're not signed in</div>
          <p className="empty-sub">Sign in to see your scan history here.</p>
          {/* Only claims the product actually keeps: saveScan() runs per signed-in
              scan, ScoreHistory charts the same device over time, and the account
              is what makes history portable across machines. */}
          <ul className="empty-perks">
            <li>Every scan saved to your account</li>
            <li>Score history for the same device over time</li>
            <li>Your history on any device you sign in on</li>
          </ul>
          <button className="cta" onClick={openAuthModal}>Sign in</button>
        </div>
      </div>
    );
  }

  const here = currentDeviceCategory();
  const grouped = filtered && groupByCategory(filtered, here);

  return (
    <div className="view">
      <div>
        <div className="eyebrow">Your account</div>
        <h1 className="title">Your devices</h1>
        <p className="lede">
          One card per machine, updated in place — not one per scan. Open a card to see how its
          score has moved over time.
        </p>
      </div>

      {err && <div className="badge bad">⚠ {err}</div>}
      {!scans && !err && <div className="center"><span className="spinner" /> loading scans…</div>}

      {(() => {
        const due = (devices || []).filter(reassessReason);
        if (!due.length || nudgeDismissed) return null;
        return (
          <div className="reassess-banner">
            <span className="reassess-icon" aria-hidden="true">⏰</span>
            <span className="reassess-text">
              <b>{due.length === 1 ? "1 device is" : `${due.length} devices are`} worth a fresh scan.</b>{" "}
              {due.length === 1
                ? <>{getNickname(due[0].deviceId) || deviceTitle(due[0].primary.passport?.payload || {})} — {reassessReason(due[0])}.</>
                : "Their support window, battery, or last check has moved on."}
            </span>
            <button className="ghost sm" onClick={() => onNavigate("scan", { fresh: true })}>Rescan</button>
            <button className="reassess-x" onClick={() => setNudgeDismissed(true)} aria-label="Dismiss">✕</button>
          </div>
        );
      })()}

      {scans && scans.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">🗂</div>
          <div className="empty-title">No scans yet</div>
          <p className="empty-sub">Run a scan while signed in and it'll show up here.</p>
          <button className="cta" onClick={() => onNavigate("scan", { fresh: true })}>Go scan a device</button>
        </div>
      )}

      {devices && devices.length > 1 && (
        <div className="scan-filters">
          <input
            className="scan-search"
            placeholder="Search by name, model, OS or grade…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="chip-row">
            {[["excellent", "A"], ["good", "B"], ["fair", "C"], ["poor", "D–F"]].map(([t, label]) => (
              <button
                key={t}
                className={`chip chip-${t} ${filters.tone === t ? "on" : ""}`}
                onClick={() => toggleFilter("tone", t)}
              >{label}</button>
            ))}
            <span className="chip-sep" />
            <button className={`chip ${filters.type === "deep" ? "on" : ""}`} onClick={() => toggleFilter("type", "deep")}>Deep</button>
            <button className={`chip ${filters.type === "instant" ? "on" : ""}`} onClick={() => toggleFilter("type", "instant")}>Instant</button>
            <span className="chip-sep" />
            <button className={`chip chip-attention ${filters.attention ? "on" : ""}`} onClick={() => toggleFilter("attention", true)}>⚠ Needs attention</button>
            {anyFilter && (
              <button className="chip chip-clear" onClick={() => { setQuery(""); setFilters({ tone: null, type: null, attention: false }); }}>Clear</button>
            )}
            <span className="chip-sep" />
            <div className="view-toggle">
              <button className={view === "cards" ? "on" : ""} onClick={() => setView("cards")} title="Card view">▦ Cards</button>
              <button className={view === "table" ? "on" : ""} onClick={() => setView("table")} title="Table view">☰ Table</button>
            </div>
          </div>
        </div>
      )}

      {filtered && filtered.length === 0 && devices.length > 0 && (
        <div className="empty-state empty-inline">
          <div className="empty-icon">🔍</div>
          <div className="empty-title">No matches</div>
          <p className="empty-sub">
            Nothing here fits {query.trim() ? <>“{query}”</> : "those filters"}.
          </p>
          <button className="ghost" onClick={() => { setQuery(""); setFilters({ tone: null, type: null, attention: false }); }}>Clear filters</button>
        </div>
      )}

      {view === "table" && filtered && filtered.length > 0 && (
        <FleetTable
          rows={filtered.map(deviceRow)}
          sort={sort}
          onSort={(key) => setSort((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" }))}
          selected={selected}
          onToggleSelect={(id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))}
          onOpen={(id) => { setView("cards"); setOpenId(id); }}
        />
      )}

      {view === "cards" && grouped && grouped.map(([cat, list]) => (
        <div key={cat}>
          <div className="scan-group-head">
            <span className="scan-group-icon">{CATEGORY_META[cat].icon}</span>
            <span className="scan-group-title">{CATEGORY_META[cat].label}</span>
            <span className="scan-group-count">{list.length}</span>
          </div>
          <div className="device-grid">
            {list.map((d) => (
              <DeviceCard
                key={d.deviceId}
                device={d}
                open={openId === d.deviceId}
                onToggle={() => setOpenId((cur) => (cur === d.deviceId ? null : d.deviceId))}
                onScanAgain={() => onNavigate("scan", { fresh: true })}
                primary={primaryId === d.deviceId}
                onPrimary={() => togglePrimary(d.deviceId)}
                onRemove={() => removeDevice(d)}
              />
            ))}
          </div>
        </div>
      ))}

      {/* Compare bar: appears once 2+ machines are picked, from either view. */}
      {selected.length >= 2 && !comparing && (
        <div className="compare-bar">
          <span>{selected.length} selected</span>
          <button className="cta" onClick={() => setComparing(true)}>Compare side by side</button>
          <button className="ghost" onClick={() => setSelected([])}>Clear</button>
        </div>
      )}
      {comparing && (
        <CompareModal
          rows={(devices || []).filter((d) => selected.includes(d.deviceId)).map(deviceRow)}
          onClose={() => setComparing(false)}
        />
      )}
    </div>
  );
}

function groupByCategory(devices, here) {
  const buckets = new Map();
  for (const d of devices) {
    if (!buckets.has(d.category)) buckets.set(d.category, []);
    buckets.get(d.category).push(d);
  }
  return [...buckets.entries()].sort(([a], [b]) => {
    if (a === here) return -1;
    if (b === here) return 1;
    return 0;
  });
}

/* --------------------------------------------------------------------- card */
function DeviceCard({ device, open, onToggle, onScanAgain, primary, onPrimary, onRemove }) {
  const [editing, setEditing] = useState(false);
  const [nick, setNick] = useState(() => getNickname(device.deviceId) || "");

  const scan = device.primary;
  const p = scan.passport?.payload || {};
  const blend = scan.passport?.assessment?.blend;
  const bestPathway = scan.passport?.assessment?.pathways?.[0];
  const detected = deviceTitle(p);
  const tone = gradeTone(blend?.grade);
  const isDeep = scan.scan_type === "deep";
  const mine = (device.ids || [device.deviceId]).some(isThisDevice);

  function saveNick(value) {
    setNickname(device.deviceId, value);
    setNick(value.trim());
    setEditing(false);
  }

  if (!open) {
    return (
      <div className={`device-card tone-${tone}`}>
        {/* The header is the toggle: clicking anywhere on it expands the card,
            and the caret makes that affordance visible instead of relying on
            people discovering the ring or the "View report" button. Rename and
            the caret stop propagation so they don't double-fire the toggle. */}
        <div className="dc-head dc-head-toggle" onClick={onToggle} role="button" tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle(); } }}>
          <div className="dc-names">
            {editing ? (
              <input
                className="dc-nick-input"
                autoFocus
                defaultValue={nick}
                placeholder={detected}
                onClick={(e) => e.stopPropagation()}
                onBlur={(e) => saveNick(e.target.value)}
                onKeyDown={(e) => {
                  e.stopPropagation();
                  if (e.key === "Enter") saveNick(e.target.value);
                  if (e.key === "Escape") setEditing(false);
                }}
              />
            ) : (
              <button className="dc-nick" onClick={(e) => { e.stopPropagation(); setEditing(true); }} title="Rename">
                {nick || detected}
                <span className="dc-pencil">✎</span>
              </button>
            )}
            {nick && <div className="dc-detected">{detected}</div>}
            {/* Two DELIBERATELY different concepts, kept visually distinct so they
                never read as the same thing:
                  · "This device" — cyan, auto-detected, not interactive: the
                    machine you're browsing from right now. Absent (correctly) on
                    every card when you're on a machine that's never been scanned.
                  · "Primary" — the amber star up in the corner, user-chosen and
                    clickable: the device you've named your daily driver. */}
            <div className="dc-idtags">
              {mine && (
                <span className="dc-here" title="The machine you're browsing from right now (auto-detected)">◉ This device</span>
              )}
              {primary && (
                <span className="dc-primary" title="The device you've marked as your daily driver">★ Primary</span>
              )}
            </div>
          </div>
          <div className="dc-head-right">
            <button
              className={`dc-star ${primary ? "on" : ""}`}
              aria-pressed={primary}
              title={primary ? "Your primary device — click to unset" : "Mark as your primary (daily-driver) device"}
              onClick={(e) => { e.stopPropagation(); onPrimary?.(); }}
            >{primary ? "★" : "☆"}</button>
            {/* Persistent text, not an icon with a tooltip -- tooltips need a
                hover, which does not exist on a phone. */}
            <span className={`dc-badge ${isDeep ? "deep" : "instant"}`}>{isDeep ? "Deep" : "Instant"}</span>
            <span className="dc-caret" aria-hidden="true"><ChevronDown /></span>
          </div>
        </div>

        <button className="dc-ring-wrap" onClick={onToggle}>
          {blend ? <Ring value={blend.combined_score} tone={tone} /> : <div className="dc-noscore">no score</div>}
          {blend && <div className="dc-grade">{blend.grade}</div>}
        </button>

        {bestPathway && <div className="dc-verdict">{bestPathway.icon} {bestPathway.label}</div>}

        {reassessReason(device) && (
          <div className="dc-reassess" title={reassessReason(device)}>⏰ Worth a rescan</div>
        )}

        <div className="dc-foot">
          <span className="dc-when">Scanned {relativeTime(device.lastChecked)}</span>
          {device.history.length > 1 && <span className="dc-count">{device.history.length} scans</span>}
        </div>

        <div className="dc-actions">
          <button className="ghost dc-btn" onClick={onToggle}>View report</button>
          {mine ? (
            <button className="ghost dc-btn" onClick={onScanAgain}>↻ Scan again</button>
          ) : (
            // Legibly disabled-with-reason, not a dead button shape: it reads as
            // status, and the tooltip explains that "scan again" only works from
            // the machine being scanned -- switch to it to re-scan.
            <span className="note dc-elsewhere" title="“Scan again” only runs on the device being scanned. Open Afterlife on this machine to re-scan it.">
              Not this device
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <ExpandedDevice
      device={device}
      nick={nick}
      detected={detected}
      onClose={onToggle}
      onScanAgain={onScanAgain}
      onRemove={onRemove}
      mine={mine}
    />
  );
}

function Ring({ value, tone }) {
  const r = 34, c = 2 * Math.PI * r;
  const off = c * (1 - value / 100);
  return (
    <svg className={`dc-ring tone-${tone}`} width="88" height="88" viewBox="0 0 88 88">
      <circle cx="44" cy="44" r={r} fill="none" stroke="var(--line)" strokeWidth="7" />
      <circle cx="44" cy="44" r={r} fill="none" stroke="currentColor" strokeWidth="7"
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
        transform="rotate(-90 44 44)" style={{ transition: "stroke-dashoffset 0.7s ease" }} />
      <text x="44" y="44" textAnchor="middle" dominantBaseline="central"
        fontFamily="var(--font-display)" fontSize="24" fontWeight="700" fill="var(--ink)">{value}</text>
    </svg>
  );
}

/* ----------------------------------------------------------------- expanded */
function ExpandedDevice({ device, nick, detected, onClose, onScanAgain, onRemove, mine }) {
  const [qr, setQr] = useState(null);
  const [verifyUrl, setVerifyUrl] = useState(null);
  const [copied, setCopied] = useState("");
  const scan = device.primary;
  const p = scan.passport?.payload || {};
  const assessment = scan.passport?.assessment;
  const blend = assessment?.blend;
  const pipeline = assessment?.pipeline;
  const keyPoints = assessment?.key_points;
  const bestPathway = assessment?.pathways?.[0];

  useEffect(() => {
    const doc = scan.passport;
    if (!doc?.signature || qr) return;
    // issuer/validFrom are load-bearing -- the passport is signed over the whole
    // W3C VC envelope, so dropping them makes verify_payload() check the
    // signature against the wrong bytes and always fail.
    const signed = {
      payload: doc.payload, signature: doc.signature, issuer_pubkey: doc.issuer_pubkey,
      issuer: doc.issuer, validFrom: doc.validFrom,
    };
    // Effect callbacks cannot be async, so the dynamic import is chained rather
    // than awaited.
    const data = b64encodeCompressed(signed);
    const url = `${window.location.origin}/?verify=${data}`;
    setVerifyUrl(url);
    import("qrcode")
      .then(({ default: QRCode }) => QRCode.toDataURL(url, {
          margin: 4, scale: 5, errorCorrectionLevel: "M",
          color: { dark: "#0e1518", light: "#ffffff" },
        }))
      .then(setQr)
      .catch(() => {});
  }, [scan.passport, qr]);

  function copy(kind, text) {
    if (!text) return;
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(kind);
      setTimeout(() => setCopied(""), 1600);
    }).catch(() => {});
  }

  const rows = [
    ["Manufacturer", p.manufacturer],
    ["Operating system", p.os],
    ["OS support", p.os_supported],
    ["Windows 11", p.win11],
    ["Windows 11 note", p.win11_note],
    ["Processor", p.cpu],
    ["CPU cores", p.cpu_cores],
    ["Memory", p.ram_gb ? `${p.ram_gb} GB` : null],
    ["Graphics", p.gpu],
    ["Storage", p.storage],
    ["Storage health", p.storage_health],
    ["Battery health", p.battery_health],
    ["Device age", p.age_years != null ? `${p.age_years} yr` : null],
    ["Wipe verified", p.wipe_verified],
    ["Recommended use", p.recommended_use],
    ["Est. safe years", p.est_safe_years],
    ["Brand repairability", p.repairability ? `${p.repairability.grade} · ${p.repairability.source}` : null],
    ["Scan depth", p.tier],
    ["Device ID", p.device_id],
  ].filter(([, v]) => v != null && v !== "" && v !== "UNKNOWN");

  const scoreRows = blend ? [
    ["Hardware trust", blend.hardware_trust],
    ["Combined score", `${blend.combined_score} / 100`],
    ["Years remaining", pipeline?.estimated_remaining_years != null ? `${pipeline.estimated_remaining_years} yr` : null],
  ].filter(([, v]) => v != null) : [];

  return (
    <div className="dash-card device-expanded">
      <div className="card-head-row">
        <div className="k-label" style={{ marginBottom: 0 }}>
          {nick || detected}
          {nick && <span className="note" style={{ marginLeft: "0.5rem" }}>{detected}</span>}
        </div>
        <button className="collapse-x" onClick={onClose} aria-label="Collapse"><ChevronUp /></button>
      </div>

      {/* Both timestamps, and only when they actually differ -- a device deep-scanned
          and then instant-scanned later has genuinely different "last measured
          properly" and "last looked at" dates, and collapsing them would overstate
          how fresh the detailed fields are. */}
      <p className="note" style={{ marginBottom: "0.8rem" }}>
        {scan.scan_type === "deep" ? "Deep scan" : "Instant scan"} · last checked{" "}
        {relativeTime(device.lastChecked)}
        {device.lastDeep && device.lastDeep !== device.lastChecked &&
          ` · last full scan ${relativeTime(device.lastDeep)}`}
      </p>

      {blend ? (
        <div className="scan-score-band">
          <div className="scan-score-big">{blend.combined_score}<span>/100</span></div>
          <div className="scan-score-grade">{blend.grade}</div>
        </div>
      ) : (
        <p className="note" style={{ marginBottom: "0.8rem" }}>
          No score saved for this scan.
        </p>
      )}

      {bestPathway && (
        <p className="punchline" style={{ marginBottom: "0.6rem" }}>
          {bestPathway.icon} Best fit at the time: {bestPathway.label}
        </p>
      )}

      <ScoreHistory history={device.history} />

      {keyPoints && (keyPoints.strengths.length > 0 || keyPoints.weaknesses.length > 0) && (
        <div className="checklist" style={{ marginBottom: "0.9rem" }}>
          <div className="check-col">
            {keyPoints.strengths.map((s, i) => <div className="check-item good" key={i}><span>✓</span>{s}</div>)}
          </div>
          <div className="check-col">
            {keyPoints.weaknesses.map((w, i) => <div className="check-item bad" key={i}><span>•</span>{w}</div>)}
          </div>
        </div>
      )}

      <div className="scan-detail-grid">
        {scoreRows.concat(rows).map(([k, v]) => (
          <div key={k} className="scan-detail-row">
            <span className="scan-detail-k">{k}</span>
            <span className="scan-detail-v">{v}</span>
          </div>
        ))}
      </div>

      {qr && (
        <div className="scan-share">
          <img src={qr} alt="Scan to verify this passport" width={112} height={112} />
          <div className="scan-share-body">
            <p className="note">Scan to open the verifier with this exact signed passport — anyone can confirm it hasn't been edited.</p>
            <div className="scan-share-actions">
              {verifyUrl && (
                <button className="ghost dc-btn" onClick={() => copy("link", verifyUrl)}>
                  {copied === "link" ? "✓ Copied" : "Copy verify link"}
                </button>
              )}
              {p.device_id && (
                <button className="ghost dc-btn" onClick={() => copy("id", p.device_id)}>
                  {copied === "id" ? "✓ Copied" : "Copy device ID"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginTop: "1rem" }}>
        {mine && (
          <button className="ghost" onClick={onScanAgain}>
            ↻ Scan again
          </button>
        )}
        {onRemove && (
          <button className="ghost danger" onClick={onRemove}
                  title="Delete this device and all its saved scans from your account">
            Remove from My Scans
          </button>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- fleet table */
// The card grid stops scaling past ~6-9 devices (the reviewer's point). The
// table is the fleet view: sortable columns for someone actually managing a
// stack of machines, and the place comparison selection lives.
function FleetTable({ rows, sort, onSort, selected, onToggleSelect, onOpen }) {
  const sorted = useMemo(() => {
    const dir = sort.dir === "asc" ? 1 : -1;
    const val = (r) => {
      switch (sort.key) {
        case "name": return (r.name || "").toLowerCase();
        case "score": return r.score ?? -1;
        case "years": return r.years ?? -1;
        case "os": return (r.os || "").toLowerCase();
        case "battery": return r.batteryPct ?? -1;
        case "type": return r.type || "";
        default: return new Date(r.checked).getTime();
      }
    };
    return [...rows].sort((a, b) => {
      const av = val(a), bv = val(b);
      return av < bv ? -dir : av > bv ? dir : 0;
    });
  }, [rows, sort]);

  const COLS = [
    ["name", "Device"], ["score", "Grade"], ["years", "Yrs left"],
    ["os", "OS"], ["battery", "Battery"], ["type", "Scan"], ["checked", "Checked"],
  ];
  const arrow = (k) => (sort.key === k ? (sort.dir === "asc" ? " ▲" : " ▼") : "");

  return (
    <div className="fleet-wrap">
      <table className="fleet">
        <thead>
          <tr>
            <th className="fleet-check" aria-label="select" />
            {COLS.map(([k, label]) => (
              <th key={k} className="fleet-th" onClick={() => onSort(k)} title="Sort">{label}{arrow(k)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.id} className={selected.includes(r.id) ? "sel" : ""}>
              <td className="fleet-check">
                <input type="checkbox" checked={selected.includes(r.id)}
                  onChange={() => onToggleSelect(r.id)} aria-label={`Compare ${r.name}`} />
              </td>
              <td>
                <button className="fleet-name" onClick={() => onOpen(r.id)}>{r.name}</button>
                {r.name !== r.detected && <div className="fleet-sub">{r.detected}</div>}
              </td>
              <td>{r.grade
                ? <span className={`grade-pill tone-${r.tone}`}>{r.score} · {r.grade.trim().charAt(0)}</span>
                : "—"}</td>
              <td>{r.years != null ? `${r.years} yr` : "—"}</td>
              <td className="fleet-os">{r.os || "—"}</td>
              <td>{r.battery || "—"}</td>
              <td><span className={`dc-badge ${r.type === "deep" ? "deep" : "instant"}`}>{r.type === "deep" ? "Deep" : "Instant"}</span></td>
              <td className="fleet-when">{relativeTime(r.checked)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------------------------------------------------- comparison view */
// Side by side, the question "which of these do I keep as primary vs sell?"
// answers itself. Best score and most years-left carry a tick, since that is
// the decision the comparison exists to serve.
function CompareModal({ rows, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ATTR = [
    ["Score", (r) => (r.score != null ? `${r.score} / 100` : "—")],
    ["Grade", (r) => r.grade || "—"],
    ["Years left", (r) => (r.years != null ? `${r.years} yr` : "—")],
    ["Operating system", (r) => r.os || "—"],
    ["Processor", (r) => r.cpu || "—"],
    ["Memory", (r) => (r.ramGb ? `${r.ramGb} GB` : "—")],
    ["Storage", (r) => r.storage || "—"],
    ["Battery", (r) => r.battery || "—"],
    ["Age", (r) => (r.age != null ? `${r.age} yr` : "—")],
    ["Scan", (r) => (r.type === "deep" ? "Deep" : "Instant")],
    ["Last checked", (r) => relativeTime(r.checked)],
  ];
  const bestScore = Math.max(...rows.map((r) => r.score ?? -1));
  const bestYears = Math.max(...rows.map((r) => r.years ?? -1));

  return (
    <div className="compare-scrim" onClick={onClose} role="dialog" aria-modal="true" aria-label="Compare devices">
      <div className="compare-modal" onClick={(e) => e.stopPropagation()}>
        <div className="compare-head">
          <h2>Compare devices</h2>
          <button className="collapse-x" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="compare-scroll">
          <table className="compare-table">
            <thead>
              <tr>
                <th />
                {rows.map((r) => <th key={r.id}>{r.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {ATTR.map(([label, get]) => (
                <tr key={label}>
                  <th>{label}</th>
                  {rows.map((r) => {
                    const best = (label === "Score" && r.score === bestScore && bestScore >= 0)
                      || (label === "Years left" && r.years === bestYears && bestYears >= 0);
                    return <td key={r.id} className={best ? "best" : ""}>{get(r)}{best ? " ✓" : ""}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
