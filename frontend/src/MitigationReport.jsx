// The keep-or-replace argument, made specific to this machine -- and written for
// the person who owns it, not for a security engineer.
//
// The product's own house rule (see assessment.py) is "write for a complete
// non-technical reader, avoid jargon entirely". This card breaks that easily,
// because the underlying material is genuinely technical: attack vectors,
// privilege levels, service names. The fix isn't to dumb the numbers down -- it's
// to say what each thing actually IS before saying what to do about it.
//
// Only renders for Windows 10, since that's the OS the classified corpus covers.

import { useEffect, useState } from "react";
import Disclose, { Conclusion } from "./Disclose.jsx";

const STATE = {
  true: { cls: "done", glyph: "✓", label: "already done on this PC" },
  false: { cls: "todo", glyph: "→", label: "you could do this" },
  null: { cls: "unk", glyph: "?", label: "we could not check this" },
};

function Bar({ segments, total }) {
  return (
    <div className="mit-bar" role="img" aria-label="how the security flaws break down">
      {segments.filter((s) => s.n > 0).map((s) => (
        <span
          key={s.key}
          className={`mit-seg ${s.key}`}
          style={{ width: `${(s.n / total) * 100}%` }}
          title={`${s.label}: ${s.n.toLocaleString()}`}
        />
      ))}
    </div>
  );
}

export default function MitigationReport({ mitigation, token }) {
  const [showAll, setShowAll] = useState(false);
  const [plain, setPlain] = useState(null);
  const apiBase = import.meta.env.VITE_API_BASE || "http://localhost:8000";
  const available = mitigation && mitigation.available !== false && mitigation.serious_cves;

  // Fetched separately so the numbers render instantly and the explanation
  // arrives underneath them. If it never arrives, the card is still complete --
  // it's an aid to understanding, not a dependency.
  useEffect(() => {
    if (!available || !token) return;
    let cancelled = false;
    fetch(`${apiBase}/api/mitigation-explain/${token}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!cancelled && d?.text) setPlain(d.text); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [available, token, apiBase]);

  if (!available) return null;

  const m = mitigation;
  const segments = [
    { key: "fix", n: m.fixable_cves, label: "Can be closed for free, keeping this PC" },
    { key: "iso", n: m.isolation_cves, label: "Made much harder by a network setting" },
    { key: "loc", n: m.local_access_cves, label: "Only a risk if someone already uses this PC" },
    { key: "res", n: m.remote_no_lever_cves, label: "No published fix" },
  ];

  const actionable = m.actions.filter((a) => a.applied !== true);
  const done = m.actions.filter((a) => a.applied === true);
  const shown = showAll ? m.actions : actionable.slice(0, 6);

  return (
    <div className="card pad mit" id="tour-security">
      {/* On an end-of-support OS people are actively being told to replace the
          machine, so the card answers that. On a supported one nobody is saying
          it, and asking the question anyway would manufacture the exact anxiety
          this product exists to push back on. Same numbers, different headline. */}
      <div className="mit-head">
        <div>
          <h3 className="sh-title">
            {m.os_supported ? "What's actually exposed on this PC" : "Does this actually need replacing?"}
          </h3>
          <span className="note">
            {m.os_label} has {m.serious_cves.toLocaleString()} known security flaws rated
            serious. We checked every one against Microsoft's own published advice
            {m.os_supported
              ? " to work out how much of it you can close yourself."
              : ", asking a single question: can it be closed without buying a new machine?"}
          </span>
        </div>
        <span className="life-tag fix">
          {Math.round(m.addressable_share * 100)}% have an answer
        </span>
      </div>

      {/* Conclusion first. The bar, the legend and the breakdown are all evidence
          FOR this sentence, so leading with them makes a reader assemble the
          verdict themselves -- and most will not. They fold underneath instead. */}
      <Conclusion
        tone={m.remote_no_creds_cves === 0 ? "good" : "warn"}
        icon={m.remote_no_creds_cves === 0 ? "✓" : "!"}
        verdict={m.remote_no_creds_cves === 0
          ? "Safe from attacks over the internet"
          : `${m.remote_no_creds_cves} need attention`}
        plain={m.remote_no_creds_cves === 0
          ? "Every one of these flaws needs either a login on this PC or someone sitting in front of it. "
            + (m.os_supported
              ? "This version of Windows also still gets security updates, so the list shrinks on its own."
              : "That is a very different thing from \"this machine is unsafe to keep\".")
          : "These could be reached by someone over the internet with no login, and have no published fix. That is the part worth taking seriously."}
        label="Why?"
      >
        <p className="note" style={{ marginTop: 0 }}>
          {m.os_label} has {m.serious_cves.toLocaleString()} known flaws rated serious. Every one
          was checked against Microsoft's own published advice. Here is how they break down:
        </p>

        <Bar segments={segments} total={m.serious_cves} />

        <div className="mit-legend">
          {segments.map((s) => (
            <div key={s.key} className="mit-leg">
              <span className={`mit-swatch ${s.key}`} />
              <b>{s.n.toLocaleString()}</b>
              <span>{s.label}</span>
            </div>
          ))}
        </div>

        {/* Written by the model from the same computed numbers -- it explains
            them, it cannot move them. Absent entirely if the model is unreachable. */}
        {plain && (
          <div className="mit-plainspeak">
            <span className="mit-plainspeak-tag">In plain English</span>
            <p>{plain}</p>
          </div>
        )}

        <Disclose label="Technical detail">
          <p className="note" style={{ marginTop: 0 }}>
            Each flaw is classified by its CVSS attack vector and the privileges an attacker
            would already need. "Only a risk if someone already uses this PC" means the vector is
            LOCAL or PHYSICAL, or the flaw requires privileges the attacker must obtain first.
            "Can be closed for free" means Microsoft has published a configuration change,
            service disable, or update that removes the exposure without new hardware. The
            classification runs per-device on every deep scan, from{" "}
            <code>afterlife/mitigation.py</code>.
          </p>
          <p className="note">
            <b>Limitation:</b> this counts vendor-documented mitigations only. A flaw with no
            published advice is counted as having no lever even if one exists in practice, which
            makes the residual bucket a deliberate over-estimate rather than an optimistic one.
          </p>
        </Disclose>
      </Conclusion>

      {m.actions.length > 0 && (
        <>
          <div className="mit-actions-head">
            <h4>What you can switch off</h4>
            <span className="note">
              {m.already_applied} already done · {m.outstanding} you could do ·{" "}
              {m.unknown_state} we could not check
            </span>
          </div>

          {/* A persistent key, not just a hover tooltip: the summary line above
              counts the three states, but nothing on screen told you which glyph
              was which. Tooltips need a hover, which a phone doesn't have. */}
          <div className="mit-legend" aria-hidden="true">
            <span className="mit-legend-item"><span className="mit-state done">✓</span> already done</span>
            <span className="mit-legend-item"><span className="mit-state todo">→</span> you could do</span>
            <span className="mit-legend-item"><span className="mit-state unk">?</span> couldn’t check</span>
          </div>

          <ul className="mit-actions">
            {shown.map((a) => {
              const st = STATE[String(a.applied)];
              return (
                <li key={a.key} className={`mit-action ${st.cls}`}>
                  <span className={`mit-state ${st.cls}`} title={st.label}>{st.glyph}</span>
                  <div className="mit-action-body">
                    <div className="mit-action-top">
                      <b>{a.label}</b>
                      <span className="mit-count">fixes {a.cves_closed.toLocaleString()}</span>
                    </div>
                    {/* What the thing IS comes before what to do about it -- nobody
                        can judge "disable the Print Spooler" without knowing that
                        the Print Spooler is printing. */}
                    {a.plain && <div className="mit-plain">{a.plain}</div>}
                    {a.cost && a.applied === false && (
                      <div className="mit-cost">If you switch it off: {a.cost}</div>
                    )}
                    <details className="mit-more">
                      <summary>Exact step</summary>
                      <div className="mit-action-detail">{a.action}</div>
                      {a.source && <div className="mit-src">Microsoft's advice: {a.source}</div>}
                    </details>
                  </div>
                </li>
              );
            })}
          </ul>

          {m.actions.length > shown.length && (
            <button className="ghost sm" onClick={() => setShowAll(true)}>
              Show all {m.actions.length}{done.length ? ` (including ${done.length} already done)` : ""}
            </button>
          )}

          {m.outstanding > 0 && token && (
            <div className="mit-script">
              <div>
                <b>Want these done for you?</b>
                <p className="note">
                  We can write a small script for the ones still open on this PC. Running it
                  the first time only <i>shows</i> you what it would change — nothing happens
                  until you choose to run it again with <code>-Apply</code>. Each step also
                  prints the command that puts it back.
                </p>
              </div>
              <a className="cta" href={`${apiBase}/api/hardening-script/${token}`} download>
                Get the script
              </a>
            </div>
          )}
        </>
      )}

      <Disclose label="How to read this">
        <p className="note" style={{ marginTop: 0 }}>
          Every fix counted here is one Microsoft has already published — we are not inventing
          them. "Only a risk if someone already uses this PC" means an attacker would need to be
          logged in or physically present first, which is a problem you solve with a password, not
          a new laptop.
          {m.os_supported && (
            <> {m.os_label} is still supported, so this is a picture of your current exposure
            rather than an argument about replacing anything.</>
          )}
        </p>
      </Disclose>
    </div>
  );
}
