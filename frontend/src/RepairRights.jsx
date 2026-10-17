import Disclose from "./Disclose.jsx";

// Repair rights (S2-06): what the law entitles this owner to, from
// afterlife/repair_rights.py. Laptops, the device assessed most often, are only
// partly covered by the EU right to repair (the screen, not the machine), so
// that case leads with the exclusion. Outside the EU and EEA the card says the
// EU rules do not apply rather than showing them.

const TAG = {
  covered: ["cyan", "covered by EU law"],
  display_only: ["muted", "partly covered"],
  not_covered: ["muted", "not covered yet"],
  outside: ["muted", "outside the EU"],
};

export default function RepairRights({ rights }) {
  if (!rights) return null;
  const [cls, tag] = TAG[rights.status] || TAG.not_covered;
  const eu = rights.status !== "outside";

  return (
    <div className="dash-card">
      <div className="k-label">
        Your repair rights <span className={`pill ${cls}`}>{tag}</span>
      </div>
      <b style={{ display: "block", marginTop: "0.3rem" }}>{rights.headline}</b>
      {eu && (
        <p className="note" style={{ marginTop: "0.3rem" }}>
          The EU right-to-repair directive {rights.in_force ? "has applied since" : "applies from"}{" "}
          {new Date(`${rights.applies_from}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}.
        </p>
      )}

      <ul className="rr-list">
        {rights.rights.map((r) => (
          <li key={r.title}>
            <b>{r.title}.</b> <span className="note">{r.detail}</span>
          </li>
        ))}
      </ul>

      <Disclose label="Where this comes from">
        <p className="note" style={{ marginTop: 0 }}>
          <b>This is not legal advice.</b>{" "}
          {eu
            ? "It is a plain-English reading of published EU law and applies in the EU and EEA only. Your country's own law may add to it."
            : "The app holds repair rules for the EU and EEA only, so it makes no claim about your country's law."}
        </p>
        {rights.sources.map((s) => (
          <p className="note" key={s.url}>
            Source: <a href={s.url} target="_blank" rel="noreferrer noopener">{s.label} ↗</a>
          </p>
        ))}
      </Disclose>
    </div>
  );
}
