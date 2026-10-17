import Disclose from "./Disclose.jsx";

// Repair outlook (S2-05): "if I fix it, what do I get?" and "how often does a
// repair like this work?". The first half is re-scored by the real scorer
// (afterlife/uplift.py); the second is other people's recorded outcomes from
// the Open Repair Alliance data, stated as a rate over a named dataset and
// never as a prediction about this device.

const BARRIER_PLAIN = {
  "spare parts not available": "the part was no longer available",
  "spare parts too expensive": "the part cost too much",
  "item too worn out": "the device was too worn out overall",
  "no way to open product": "it could not be opened without breaking it",
  "repair information not available": "no repair instructions could be found",
  "lack of equipment": "the repairer did not have the right tools",
};

const plain = (b) => (b ? BARRIER_PLAIN[b.toLowerCase()] || b.toLowerCase() : null);

export default function RepairOutlook({ uplift, evidence }) {
  if (!uplift && !evidence) return null;
  const cond = uplift?.condition;
  const cap = uplift?.capability;
  const hasActions = cond && cond.actions.length > 0;

  return (
    <div className="dash-card">
      <div className="k-label">Repair outlook</div>

      {hasActions && (
        <div className="uplift-row">
          <div className="uplift-scores">
            <span className="uplift-now">{cond.current_score}</span>
            <span className="uplift-arrow">→</span>
            <span className="uplift-next">{cond.projected_score}</span>
          </div>
          <div className="uplift-body">
            {cond.grade_changes ? (
              <p style={{ marginTop: 0 }}>
                Fixing this moves it from {cond.current_grade} to <b>{cond.projected_grade}</b>.
              </p>
            ) : (
              <p className="note" style={{ marginTop: 0 }}>
                Not enough to change the {cond.current_grade} grade on its own, but each point is
                a measured problem undone.
              </p>
            )}
            <ul className="uplift-actions">
              {cond.actions.map((a) => (
                <li key={a.action}>
                  <b>{a.action}</b> <span className="uplift-pts">+{a.points}</span>
                  <span className="note"> · {a.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {cond?.ssd_swap_available && (
        <p className="note" style={{ marginTop: hasActions ? "0.6rem" : 0 }}>
          <b>Swap the hard disk for an SSD.</b> This does not change the score, which measures
          wear rather than speed, but it is the biggest single change to how fast the machine feels.
        </p>
      )}

      {cap && (
        <div className="uplift-cap">
          <span className="uplift-cap-icon" aria-hidden="true">⬆</span>
          <span>
            It handles <b>{cap.current_tier || "the basics"}</b> today. Adding{" "}
            <b>{cap.ram_needed_gb} GB of memory</b> ({cap.target_ram_gb} GB in total) is the only thing
            between it and <b>{cap.next_tier}</b>; the processor and graphics already meet that tier.
            Check first that this model's memory can be upgraded.
          </span>
        </div>
      )}

      {evidence && (
        <div className="evidence">
          <div className="k-label" style={{ marginTop: hasActions || cap ? "1.2rem" : "0.2rem" }}>
            How often repairs like this work
          </div>
          <p className="note" style={{ marginTop: "0.3rem", marginBottom: "0.7rem" }}>
            Recorded outcomes for the same kind of fault, from {evidence.n_records?.toLocaleString()} computer
            repairs at community repair events. Not a prediction about this device.
          </p>
          <div className="evidence-list">
            {evidence.themes.map((t) => (
              <div className="evidence-row" key={t.key}>
                <div className="evidence-head">
                  <span className="evidence-label">{t.label}</span>
                  <span className="evidence-rate">{Math.round(t.fixed_pct)}% repaired</span>
                </div>
                <div className="evidence-track"><i className="evidence-fill" style={{ width: `${t.fixed_pct}%` }} /></div>
                <div className="note evidence-note">
                  {t.n.toLocaleString()} brought in with: {t.plain}.
                  {t.top_barrier && ` When it couldn't be fixed, usually ${plain(t.top_barrier)}.`}
                </div>
              </div>
            ))}
          </div>
          <Disclose label="What this measures, and what it doesn't">
            <p className="note" style={{ marginTop: 0 }}>
              The records say what was wrong and how it ended, not which repair was done, so these
              rates say how often a fault was beaten, never what the fix was.
            </p>
            <p className="note">
              These are devices someone thought worth taking to a repair event. Ones written off at
              home never appear, so this is the success rate among attempted repairs.
            </p>
          </Disclose>
          <p className="ai-caption">Source: {evidence.source}.</p>
        </div>
      )}
    </div>
  );
}
