// Hardware findings Windows already knows about but never shows anyone: logged
// hardware errors, disk/filesystem errors, graphics-driver resets, crash dumps,
// unexpected shutdowns, faulty devices, and Windows' own stability score.

const SEV = { serious: "eol", warning: "rep", info: "muted" };

export default function ReliabilitySignals({ hardware }) {
  if (!hardware) return null;
  const { findings = [], reliability, battery, memory_sticks: mem = [] } = hardware;
  // Nothing worth a card: no findings, no stability score, no battery cycle data.
  if (!findings.length && !reliability && !battery && !mem.length) return null;

  return (
    <div className="card pad reliability">
      <div className="sh-head">
        <div>
          <h3 className="sh-title">Reliability record</h3>
          <span className="note">What this machine has logged about itself</span>
        </div>
        {reliability && (
          <span className={`life-tag ${reliability.band === "good" ? "fix"
            : reliability.band === "poor" ? "eol" : "rep"}`}>
            {reliability.index}/10 stability
          </span>
        )}
      </div>

      {findings.length === 0 ? (
        <p className="sh-summary">{hardware.summary || "No hardware faults found in the logs that could be read."}</p>
      ) : (
        <ul className="sh-findings">
          {findings.map((f, i) => (
            <li key={i} className={`sh-finding ${f.severity}`}>
              <span className="sh-dot" />
              <span>
                <b className={`life-tag ${SEV[f.severity] || "muted"} inline`}>{f.label}</b>
                {" "}{f.detail}
              </span>
            </li>
          ))}
        </ul>
      )}

      {(battery || mem.length > 0) && (
        <div className="rel-extra">
          {battery && <div className="note">{battery.note}</div>}
          {mem.length > 0 && (
            <div className="note">
              Memory: {mem.length} stick{mem.length > 1 ? "s" : ""} ·{" "}
              {mem.map((m, i) => (
                <span key={i}>
                  {i > 0 && ", "}
                  {m.capacity_gb}GB{m.speed_mhz ? ` @ ${m.speed_mhz}MHz` : ""}
                  {m.manufacturer ? ` (${m.manufacturer})` : ""}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
