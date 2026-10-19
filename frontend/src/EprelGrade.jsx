import Disclose from "./Disclose.jsx";

// The EU's official repairability grade (S3-01), for phones and tablets only.
// It is what the maker DECLARED to the EU registry (EPREL) before sale, scored
// by a published formula; AfterLife's own end-of-life figure comes from what
// actually happened at repair events. The two are shown side by side because
// they answer different questions. Laptops are not in the registry, so they get
// no card at all rather than a borrowed grade.

const PARTS = [
  ["disassembly_depth", "How far it comes apart"],
  ["fasteners", "Fasteners (screws vs glue)"],
  ["tools", "Tools needed"],
];
const SPARE = { PRIORITY: "priority parts available", ALL: "all listed parts available", NONE: "none listed" };
const INFO = { NO_COST: "free to all", REGISTERED: "for registered repairers", NONE: "not provided" };

export default function EprelGrade({ eprel, eolRisk }) {
  if (!eprel) return null;
  if (!eprel.matched) {
    return (
      <div className="dash-card">
        <div className="k-label">EU repairability grade</div>
        <p className="note" style={{ marginTop: "0.3rem" }}>
          No entry in the EU registry matched “{eprel.query}”. Try the model code from Settings → About
          phone (for example SM-S931B). AfterLife shows no grade rather than a guessed one.
        </p>
      </div>
    );
  }
  const total = eprel.spread ? Object.values(eprel.spread.classes || {}).reduce((a, b) => a + b, 0) : 0;
  return (
    <div className="dash-card">
      <div className="k-label">EU repairability grade <span className="pill cyan">official</span></div>
      <div className="eprel-head">
        <span className={`eprel-class c-${(eprel.repairability_class || "").toLowerCase()}`}>{eprel.repairability_class}</span>
        <div>
          <b>{eprel.brand} {eprel.model}</b>
          <p className="note" style={{ margin: "0.2rem 0 0" }}>{eprel.grade_note}</p>
          <p className="note" style={{ margin: "0.2rem 0 0" }}>
            Declared by the maker to the EU product registry (registration {eprel.registration}).
          </p>
        </div>
      </div>

      {typeof eolRisk === "number" && (
        <p className="note" style={{ marginTop: "0.7rem" }}>
          Beside it, AfterLife's own figure: <b>{Math.round(eolRisk * 100)}%</b> end-of-life risk for devices like
          this, learned from real repair outcomes. The grade says how repairable it was designed to be; the risk
          says how repairs like it actually went.
        </p>
      )}

      <ul className="eprel-facts">
        {PARTS.map(([k, label]) => eprel[k] != null && <li key={k}><span>{label}</span><b>{eprel[k]} / 5</b></li>)}
        {eprel.spare_parts && <li><span>Spare parts</span><b>{SPARE[eprel.spare_parts] || eprel.spare_parts}</b></li>}
        {eprel.repair_info && <li><span>Repair information</span><b>{INFO[eprel.repair_info] || eprel.repair_info}</b></li>}
        {eprel.min_years_software_updates != null && <li><span>Software updates</span><b>at least {eprel.min_years_software_updates} years</b></li>}
        {eprel.battery_user_replaceable != null && <li><span>Battery replaceable by the owner</span><b>{eprel.battery_user_replaceable ? "yes" : "no"}</b></li>}
      </ul>

      {eprel.spread && total > 0 && (
        <div className="eprel-spread" aria-label="How all registered models are graded">
          {Object.entries(eprel.spread.classes).map(([c, n]) => (
            <div key={c} className={`eprel-bar c-${c.toLowerCase()} ${c === eprel.repairability_class ? "on" : ""}`}
                 style={{ flexGrow: n }} title={`${c}: ${n} models`}>{c}</div>
          ))}
        </div>
      )}
      {eprel.spread && (
        <p className="note" style={{ marginTop: "0.3rem" }}>
          Across all {eprel.spread.n?.toLocaleString()} registered phones and tablets (median score {eprel.spread.median_index} / 5).
        </p>
      )}

      <Disclose label="What this grade is, and what it isn't">
        <p className="note" style={{ marginTop: 0 }}>{eprel.caveat}</p>
        <p className="note">
          Matched on {eprel.match_score === 1 ? "the exact model code" : "the model code with a variant suffix, or the model name"}.
          Regulation: {eprel.regulation}. Data fetched {eprel.fetched}.
        </p>
        {(eprel.repair_instructions_url || eprel.spare_parts_url) && (
          <p className="note">
            From the maker:{" "}
            {eprel.repair_instructions_url && <a href={eprel.repair_instructions_url} target="_blank" rel="noreferrer noopener">repair instructions ↗</a>}
            {eprel.repair_instructions_url && eprel.spare_parts_url && " · "}
            {eprel.spare_parts_url && <a href={eprel.spare_parts_url} target="_blank" rel="noreferrer noopener">spare parts ↗</a>}
          </p>
        )}
      </Disclose>
      <p className="ai-caption">{eprel.attribution}</p>
    </div>
  );
}
