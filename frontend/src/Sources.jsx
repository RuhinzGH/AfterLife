import { useEffect, useState } from "react";
import { api } from "./api.js";

/**
 * Where every number on this site comes from, and how old it is.
 *
 * The product's entire pitch is "verified, not vibes", and the one thing that
 * claim needs is somewhere a sceptic can check the provenance without taking
 * anybody's word for it. That page did not exist.
 *
 * Nothing here is written. Every date, row count and status is read off the
 * artifact on disk when the request is made — including the awkward ones. A
 * source that has gone stale says so, in days, on its own page, without anyone
 * remembering to update a sentence. Building it any other way would repeat the
 * exact failure the project already documents: a page quoting a confident CVE
 * count from a corpus that had stopped moving two years earlier.
 */

const STATUS = {
  current:    { cls: "ok",   label: "current" },
  ageing:     { cls: "warn", label: "ageing" },
  stale:      { cls: "bad",  label: "stale" },
  unverified: { cls: "mut",  label: "unverified" },
  unknown:    { cls: "mut",  label: "unknown" },
};

function Row({ s }) {
  const st = STATUS[s.status] || STATUS.unknown;
  return (
    <li className={`src-row is-${st.cls}`}>
      <div className="src-head">
        <a href={s.url} target="_blank" rel="noopener noreferrer" className="src-name">
          {s.label}
        </a>
        <span className={`pill ${st.cls === "ok" ? "cyan" : "muted"}`}>{st.label}</span>
      </div>

      <p className="note src-use">{s.used_for}</p>

      <dl className="src-facts">
        <div>
          <dt>Last pulled</dt>
          <dd>
            {s.fetched || "—"}
            {s.age_days != null && <span className="src-age"> · {s.age_days}d ago</span>}
          </dd>
        </div>
        <div>
          <dt>Records</dt>
          <dd>{s.rows != null ? s.rows.toLocaleString() : "—"}</dd>
        </div>
        <div>
          <dt>Refreshed every</dt>
          <dd>{s.expected_days ? `${s.expected_days} days` : "one-off release"}</dd>
        </div>
        <div>
          <dt>Licence</dt>
          <dd className="src-licence">{s.licence}</dd>
        </div>
      </dl>

      {/* The distinction that keeps this page honest. A date read from a file's
          modification time cannot tell a fresh pull from a fresh checkout, so it
          is never allowed to vouch for a source — only to rule one out. Saying
          so on the row is the difference between provenance and decoration. */}
      {s.fetched_basis === "mtime" && (
        <p className="note src-caveat">
          This date is the file's modification time, not a recorded pull — the
          builder for this source does not stamp itself yet, so the date cannot
          be trusted to mean the data is fresh.
        </p>
      )}
      {!s.present && (
        <p className="note src-caveat">
          Not present in this build. Anything depending on it is unavailable
          rather than estimated.
        </p>
      )}
    </li>
  );
}

export default function Sources() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let dead = false;
    api.sources()
      .then((d) => { if (!dead) setData(d); })
      .catch((e) => { if (!dead) setErr(e.message || "could not load sources"); });
    return () => { dead = true; };
  }, []);

  if (err) return <div className="dash-card"><b>Could not load sources</b><p className="note">{err}</p></div>;
  if (!data) return <div className="dash-card"><p className="note">Reading the manifest…</p></div>;

  const fresh = data.by_status.current || 0;

  return (
    <div className="view sources-view">
      <div className="eyebrow">Provenance · nothing here is typed in</div>
      <h1 className="title">Every number has a receipt</h1>
      <p className="lede">
        {data.total} datasets stand behind this product. The dates, counts and
        licences below are read from the files themselves each time this page
        loads — so a source that has gone stale says so here before anyone has to
        notice.
      </p>

      <div className="src-summary glass">
        <div><b>{fresh}</b><span>verified current</span></div>
        <div><b>{data.total - fresh}</b><span>unverified or ageing</span></div>
        <div><b>{data.as_of}</b><span>checked</span></div>
      </div>

      <ul className="src-list">
        {data.sources.map((s) => <Row key={s.key} s={s} />)}
      </ul>

      <p className="note src-method">{data.note}</p>
    </div>
  );
}
