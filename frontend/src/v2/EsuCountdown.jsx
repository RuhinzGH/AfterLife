// Windows 10 countdown. Every date and day count on this page is read from
// GET /api/esu (afterlife/esu.py); the page only does clock arithmetic on them.
import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import "./esu.css";

const DAY_MS = 86_400_000;

// "2027-10-12" -> a UTC midnight timestamp, so date maths never drifts by a
// time zone. Returns null for anything that is not a plain ISO date.
function isoToUtc(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : null;
}

function fmtDate(iso) {
  const t = isoToUtc(iso);
  if (t == null) return "date not available";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(t));
}

// The instant the esu_end day is over, in the visitor's own time zone:
// local midnight at the start of the following day.
function endOfDayLocal(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  return m ? new Date(+m[1], +m[2] - 1, +m[3] + 1, 0, 0, 0).getTime() : null;
}

function errorText(err) {
  try { return JSON.parse(err.message).detail || err.message; } catch { return err?.message || "request failed"; }
}

const STATE_COPY = {
  supported: { label: "Supported", text: "Ordinary support: security and quality updates for every device, no enrolment needed." },
  esu: { label: "Extended Security Updates", text: "Ordinary support is over. Only devices enrolled in the programme still get security patches, and only security patches." },
  unsupported: { label: "Ended", text: "This programme has ended. Devices it covered no longer receive security updates from it." },
};

function useNow(active) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  return now;
}

function Countdown({ target }) {
  const now = useNow(target != null);
  if (target == null) return <p className="v2-note">The programme end date did not come back from the server, so there is nothing to count to.</p>;
  const left = Math.max(0, target - now);
  const parts = [
    ["days", Math.floor(left / DAY_MS)],
    ["hours", Math.floor((left % DAY_MS) / 3_600_000)],
    ["minutes", Math.floor((left % 3_600_000) / 60_000)],
    ["seconds", Math.floor((left % 60_000) / 1000)],
  ];
  return (
    <div className="esu-clock" role="timer" aria-live="off" aria-label={`${parts[0][1]} days, ${parts[1][1]} hours, ${parts[2][1]} minutes left`}>
      {parts.map(([unit, n], i) => (
        <div className="esu-cell" key={unit}>
          <span className={`esu-digit v2-num ${i === 0 ? "v2-grad-text" : ""}`}>
            {i === 0 ? n : String(n).padStart(2, "0")}
          </span>
          <span className="esu-unit">{unit}</span>
        </div>
      ))}
    </div>
  );
}

function Timeline({ data }) {
  const c = data.consumer, b = data.commercial;
  const start = isoToUtc(c.support_end), end = isoToUtc(b.esu_end), today = isoToUtc(data.as_of);
  if (start == null || end == null || end <= start) return null;
  const pos = (t) => `${Math.min(100, Math.max(0, ((t - start) / (end - start)) * 100)).toFixed(2)}%`;
  const points = [
    { key: "support", t: start, date: c.support_end, title: "Ordinary support ended", sub: "Windows 10, all editions", tone: "muted" },
    today != null && { key: "today", t: today, date: data.as_of, title: "Today", sub: "per the server's date", tone: "today" },
    { key: "consumer", t: isoToUtc(c.esu_end), date: c.esu_end, title: "Home-user ESU ends", sub: "the countdown above", tone: "hot" },
    { key: "commercial", t: end, date: b.esu_end, title: "Organisations' paid ESU ends", sub: "commercial and education", tone: "cool" },
  ].filter(Boolean);
  return (
    <div className="esu-timeline" role="list" aria-label="Windows 10 support timeline">
      <div className="esu-track" aria-hidden="true">
        {today != null && <div className="esu-fill" style={{ "--pos": pos(today) }} />}
      </div>
      {points.map((p, i) => (
        <div key={p.key} role="listitem" className={`esu-point is-${p.tone} ${i % 2 ? "is-below" : "is-above"}`} style={{ "--pos": pos(p.t) }}>
          <span className="esu-dot" aria-hidden="true" />
          <span className="esu-label">
            <span className="esu-label-date">{fmtDate(p.date)}</span>
            <span className="esu-label-title">{p.title}</span>
            <span className="esu-label-sub">{p.sub}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

function Programme({ p, who }) {
  const s = STATE_COPY[p.state] || { label: p.state || "unknown", text: "State not recognised by this page." };
  return (
    <article className="v2-card esu-prog">
      <p className="v2-eyebrow">{who}</p>
      <h3 className="v2-h3">{p.product}</h3>
      <p className={`esu-state is-${p.state}`}>{s.label}</p>
      <p className="esu-prog-text">{s.text}</p>
      <dl className="esu-facts">
        <div><dt>Who can get it</dt><dd>{p.audience || "not stated"}</dd></div>
        <div><dt>What it covers</dt><dd>{p.scope || "not stated"}</dd></div>
        <div>
          <dt>Enrolment</dt>
          <dd>{p.enrolment_open === true ? `Open — join any time until ${fmtDate(p.enrol_by)}.`
            : p.enrolment_open === false ? `Closed (last day was ${fmtDate(p.enrol_by)}).` : "not stated"}</dd>
        </div>
        <div>
          <dt>Programme ends</dt>
          <dd>{fmtDate(p.esu_end)}{typeof p.ends_in_days === "number"
            ? (p.ends_in_days >= 0 ? ` — ${p.ends_in_days} days from the server's date` : ` — ended ${-p.ends_in_days} days ago`) : ""}</dd>
        </div>
      </dl>
      {p.source && (
        <p className="v2-note">Source: <a className="esu-link" href={p.source} target="_blank" rel="noreferrer">Microsoft's programme page</a></p>
      )}
    </article>
  );
}

export default function EsuCountdown({ onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    api.esu().then((d) => live && setData(d)).catch((e) => live && setError(errorText(e)));
    return () => { live = false; };
  }, []);

  const target = useMemo(() => (data ? endOfDayLocal(data.consumer?.esu_end) : null), [data]);

  if (error) {
    return (
      <section className="esu">
        <p className="v2-eyebrow">Windows 10 countdown</p>
        <h1 className="v2-h2">The support dates could not be loaded.</h1>
        <p className="v2-note">{error}. This page shows no dates it cannot read from the server.</p>
      </section>
    );
  }
  if (!data) {
    return <section className="esu" aria-busy="true"><p className="v2-eyebrow">Windows 10 countdown</p><div className="esu-skel" /></section>;
  }

  const c = data.consumer;
  const ended = target != null && Date.now() >= target;
  return (
    <section className="esu">
      <header className="esu-hero">
        <p className="v2-eyebrow">Windows 10 countdown · as of {fmtDate(data.as_of)}</p>
        <h1 className="v2-h1">
          {ended ? <>Home-user security updates <span className="v2-grad-text">have ended.</span></>
            : <>Security updates for home Windows 10 PCs <span className="v2-grad-text">stop in</span></>}
        </h1>
        <Countdown target={target} />
        <p className="v2-note esu-target">
          Counting to the end of {fmtDate(c.esu_end)} — midnight at the close of that day in your own time zone.
          Microsoft publishes a date, not a time of day.
        </p>
        <p className="v2-lede">{c.headline}</p>
        <div className="esu-ctas">
          <button type="button" className="v2-btn" onClick={() => onNavigate?.("scan", { fresh: true })}>Scan a device</button>
          <button type="button" className="v2-btn ghost" onClick={() => onNavigate?.("thesis")}>Read the argument</button>
        </div>
      </header>

      <div className="v2-card esu-tl-card">
        <h2 className="v2-h3">The timeline</h2>
        <Timeline data={data} />
        <p className="v2-note">
          On wide screens the dates are placed to scale. The home-user date has moved once
          already: it was first announced as 13 October 2026 and extended by a year in June 2026
          (history recorded in this project's ESU module, afterlife/esu.py). The date in the countdown is the one
          the server returns today, so if Microsoft moves it again the page follows.
        </p>
      </div>

      <div className="esu-progs">
        <Programme p={c} who="Home users" />
        <Programme p={data.commercial} who="Organisations" />
      </div>

      <div className="v2-card esu-after">
        <h2 className="v2-h2">What happens after the date</h2>
        <div className="esu-after-grid">
          <div>
            <h3 className="v2-h3">The machine keeps working</h3>
            <p>Nothing switches off. The device boots, runs and holds your files the morning after,
              exactly as it did the night before. What stops is the stream of security fixes.</p>
          </div>
          <div>
            <h3 className="v2-h3">The risk rises from then on</h3>
            <p>Every vulnerability found after the cut-off stays open. That is a security cost you can
              mitigate — a supported operating system, Windows 11 if the hardware qualifies, or a narrower
              role for the machine — not a hardware fault.</p>
          </div>
          <div>
            <h3 className="v2-h3">A date, not a fault</h3>
            <p>That is AfterLife's argument: working machines are retired by a calendar. A scan tells you
              whether this one is worth keeping, repairing, selling or recycling.</p>
          </div>
        </div>
        <div className="esu-ctas">
          <button type="button" className="v2-btn" onClick={() => onNavigate?.("scan", { fresh: true })}>Scan this device</button>
          <button type="button" className="v2-btn ghost" onClick={() => onNavigate?.("thesis")}>Why replacing rarely pays back</button>
        </div>
      </div>
    </section>
  );
}
