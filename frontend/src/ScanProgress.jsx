// The deep scan, shown as a checklist rather than a spinner.
//
// A deep scan is a high-stakes, multi-step, minutes-long flow that the user
// kicks off in a terminal and then watches a pulsing dot for. When nothing
// arrives they cannot tell whether the collector failed, the upload was blocked,
// or it is simply slow -- so the failure mode of the old UI was not "no
// feedback", it was "no way to locate the problem".
//
// Every step below is driven by state the browser genuinely knows. Nothing here
// is a fake progress animation: "collector ran" only ticks when a payload
// actually arrives, and the steps after it tick as their real work completes.
// A checklist that guesses is worse than a spinner, because it lies with
// specifics.

const PENDING = "pending", ACTIVE = "active", DONE = "done", FAILED = "failed";

function Step({ state, label, detail }) {
  const icon = { done: "✓", failed: "✕", active: "●", pending: "○" }[state];
  return (
    <li className={`sp-step is-${state}`}>
      <span className="sp-icon" aria-hidden="true">{icon}</span>
      <span className="sp-body">
        <span className="sp-label">{label}</span>
        {detail && <span className="sp-detail">{detail}</span>}
      </span>
    </li>
  );
}

export default function ScanProgress({ waiting, stalled, received, signed, assessed, elapsed }) {
  const mins = Math.floor(elapsed / 60);
  const secs = String(elapsed % 60).padStart(2, "0");

  const steps = [
    {
      label: "Collector runs on your machine",
      state: received ? DONE : stalled ? FAILED : ACTIVE,
      detail: received
        ? "Scan received"
        : stalled
          ? "Nothing has arrived yet"
          : "Waiting — the scan itself takes about twenty seconds once it starts",
    },
    {
      label: "Results uploaded to Afterlife",
      state: received ? DONE : PENDING,
      detail: received ? "Hardware, security and health readings in hand" : null,
    },
    {
      label: "Passport signed",
      state: signed ? DONE : received ? ACTIVE : PENDING,
      detail: signed ? "Ed25519 signature over the whole record" : null,
    },
    {
      label: "Assessment computed",
      state: assessed ? DONE : signed ? ACTIVE : PENDING,
      detail: assessed ? "Score, grade and remaining life" : null,
    },
  ];

  return (
    <div className="scan-progress">
      <div className="sp-head">
        <span className="sp-title">
          {received ? "Scan complete" : stalled ? "Still listening" : "Listening for your scan"}
        </span>
        {waiting && (
          <span className="sp-clock" aria-live="off">{mins}:{secs}</span>
        )}
      </div>

      {/* aria-live so a screen-reader user is told when a step completes rather
          than having to poll the list by hand. */}
      <ol className="sp-steps" aria-live="polite">
        {steps.map((s) => <Step key={s.label} {...s} />)}
      </ol>
    </div>
  );
}

// What the collector actually managed to read.
//
// Partial success, itemised. A scan that reached everything except SMART is not
// a failure and should not read as one -- but it is also not the complete scan
// the passport used to claim it was, and the user is owed the difference,
// especially when one of the gaps is fixable by re-running elevated.
export function ScanCoverage({ coverage }) {
  if (!coverage || !coverage.probes) return null;
  const { probes, completeness_pct, rerun_elevated_would_help, summary } = coverage;
  const complete = completeness_pct >= 100;

  return (
    <div className={`scan-coverage ${complete ? "is-complete" : "is-partial"}`}>
      <div className="sc-head">
        <span className="sc-title">What this scan could read</span>
        <span className={`pill ${complete ? "cyan" : "muted"}`}>{completeness_pct}% complete</span>
      </div>

      <p className="note sc-summary">{summary}</p>

      <ul className="sc-list">
        {probes.map((p) => (
          <li key={p.key} className={`sc-item ${p.ok === true ? "ok" : p.ok === null ? "na" : "miss"}`}>
            <span className="sc-mark" aria-hidden="true">
              {p.ok === true ? "✓" : p.ok === null ? "–" : "✕"}
            </span>
            <span>
              {p.label}
              {p.why && <span className="sc-why">{p.why}</span>}
            </span>
          </li>
        ))}
      </ul>

      {rerun_elevated_would_help && (
        <p className="note sc-fix">
          Re-run the collector as administrator to fill in the missing checks —
          they need elevated access and nothing else went wrong.
        </p>
      )}
    </div>
  );
}
