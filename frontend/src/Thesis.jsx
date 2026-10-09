import { useEffect, useState } from "react";
import { api } from "./api.js";

/**
 * The argument, in one place, made of computed figures.
 *
 * AfterLife has always had a thesis — devices are retired years before they
 * fail, pushed out by support cliffs and perception rather than by hardware
 * giving up — and it lived in a README. The research page shows the evidence
 * card by card; the landing page states the conclusion. Nothing connected them.
 *
 * Every number here is READ from the same artifacts the research page reads,
 * not restated. That matters more than it sounds: this project once shipped a
 * screen asserting two different CVE totals a few inches apart, because one was
 * computed and the other was typed. Two pages making the same argument from two
 * copies of a number is that bug waiting to happen again.
 *
 * The claims arrive in argument order, not in order of size. Each one answers
 * the objection the previous one raises: age does not predict failure, so what
 * about security — security flaws are the least exploited ones, so what about
 * efficiency — replacing costs more carbon than it saves, so what is actually
 * retiring these machines? A date.
 */

export default function Thesis({ onNavigate }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let dead = false;
    api.thesis()
      .then((d) => { if (!dead) setData(d); })
      .catch((e) => { if (!dead) setErr(e.message || "could not load"); });
    return () => { dead = true; };
  }, []);

  if (err) {
    return <div className="dash-card"><b>Could not load</b><p className="note">{err}</p></div>;
  }
  if (!data) {
    return <div className="dash-card"><p className="note">Assembling the argument…</p></div>;
  }

  return (
    <div className="view thesis-view">
      <div className="eyebrow">The argument · every figure computed</div>
      <h1 className="title">Obsolete? Says who?</h1>
      <p className="lede">
        Working hardware is scrapped on schedules, not on faults. Four findings,
        each read from a real dataset, and each one answering the objection the
        last one raises.
      </p>

      <ol className="thesis-list">
        {data.claims.map((c, i) => (
          <li className="thesis-claim glass" key={c.key}>
            <span className="thesis-index" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>

            <div className="thesis-body">
              <h2 className="thesis-headline">{c.headline}</h2>

              <div className="thesis-figure">
                <b>{c.figure}</b>
                <span>{c.unit}</span>
              </div>

              <p className="thesis-detail">{c.detail}</p>

              <p className="note thesis-basis">
                <span className="thesis-basis-label">Measured on</span> {c.basis}
                <br />
                <span className="thesis-basis-label">Source</span> {c.source}
              </p>
            </div>
          </li>
        ))}
      </ol>

      <div className="thesis-close glass">
        <h2>So the question is not whether it still works.</h2>
        <p>
          It is whether anything has actually changed about the machine — or only
          about the calendar. That is the question this product exists to answer,
          on your device, with the same data.
        </p>
        <div className="thesis-actions">
          <button className="cta" onClick={() => onNavigate?.("scan", { fresh: true })}>
            Scan your device →
          </button>
          <button className="ghost" onClick={() => onNavigate?.("sources")}>
            Check the sources
          </button>
        </div>
      </div>

      <p className="note thesis-method">{data.note}</p>
    </div>
  );
}
