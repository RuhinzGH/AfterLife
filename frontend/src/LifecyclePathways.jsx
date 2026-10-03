import AiCaption from "./AiCaption.jsx";

const STATUS_LABEL = { best_fit: "Best fit today", also_viable: "Also viable", not_ideal: "Not ideal right now" };

// Five parallel futures for one device instead of a single verdict --
// "obsolete" is a decision informed by security, performance, economics, and
// sustainability, not a binary the app hands down. Every pathway's fit score
// and action list is computed server-side (afterlife/pathways.py); this just
// renders it. Cards stay in the order the backend already ranked them in
// (best fit first), so nothing gets re-sorted client-side.
export default function LifecyclePathways({ pathways, narrative }) {
  if (!pathways || pathways.length === 0) return null;

  return (
    <div className="dash-card">
      <div className="k-label">Lifecycle pathways</div>
      {narrative?.summary && <p className="punchline" style={{ marginTop: "0.5rem" }}>{narrative.summary}</p>}
      {narrative && <AiCaption source={narrative.source} />}

      <div className="pathways-grid" style={{ marginTop: "0.9rem" }}>
        {pathways.map((p) => (
          <div className={`pathway-card ${p.color} ${p.status}`} key={p.key}>
            <div className="pathway-head">
              <span className="pathway-icon">{p.icon}</span>
              <span className="pathway-label">{p.label}</span>
              <span className={`pathway-status ${p.status}`}>{STATUS_LABEL[p.status]}</span>
            </div>
            <div className="pathway-fit-track">
              <i className="pathway-fit-fill" style={{ width: `${p.fit_score}%` }} />
            </div>
            <ul className="pathway-actions">
              {p.actions.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
