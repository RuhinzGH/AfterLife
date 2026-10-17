import Disclose from "./Disclose.jsx";

// Usage fit (S2-07): is this machine up to the work its owner does on it, and
// for how long? Everything comes from /api/assess (afterlife/persona.py); the
// card only lays it out.
//
// The two year figures on the page answer different questions, so the card says
// which is which: this one is how long the machine keeps up with a kind of work
// as software asks for more; the lifecycle card is safe service life from its
// measured condition.

const ICON = { general: "🗂", gamer: "🎮", coder: "💻", editor: "🎬" };

export default function UsageFit({ fit, lifecycleYears }) {
  if (!fit) return null;
  const auto = fit.source === "auto-detected";
  const differ = typeof fit.years_of_headroom === "number" && typeof lifecycleYears === "number"
    && Math.abs(fit.years_of_headroom - lifecycleYears) >= 1.5;

  return (
    <div className="dash-card">
      <div className="k-label">
        Usage fit
        <span className={`pill ${auto ? "cyan" : "muted"}`}>{auto ? "auto-detected" : "self-reported"}</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginTop: "0.4rem" }}>
        <span style={{ fontSize: "1.4rem" }} aria-hidden="true">{ICON[fit.persona]}</span>
        <span style={{ fontSize: "1.05rem", fontWeight: 500 }}>{fit.label}</span>
      </div>
      {auto && (
        <p className="note" style={{ marginTop: "0.3rem" }}>
          {fit.reasons.length
            ? <>Detected from: {fit.reasons.join(", ")}.</>
            : <>No gaming, coding or editing tools from the list were found, so this is treated as general use.</>}
        </p>
      )}

      <p style={{ marginTop: "0.6rem" }}>{fit.verdict}</p>

      <div className="fit-ladder">
        {fit.tiers.map((t) => (
          <div key={t.name} className={`fit-tier ${t.met ? "met" : ""}`}>
            <span className="fit-mark">{t.met ? "✓" : "○"}</span>
            <span className="fit-name">{t.name}</span>
            <span className="fit-need">
              {t.cores}+ cores · {t.ram_gb}+ GB{t.gpu_tier ? " · dedicated graphics" : ""}
            </span>
          </div>
        ))}
      </div>

      {fit.timeline && <p className="note" style={{ marginTop: "0.7rem" }}>{fit.timeline}</p>}
      {differ && (
        <p className="note" style={{ marginTop: "0.4rem" }}>
          This differs from the <b>{lifecycleYears} years</b> of safe service life above because it
          measures something else: how long the machine keeps up with this kind of work, not how
          long its hardware lasts.
        </p>
      )}
      {fit.caveats.map((c) => <p className="note" key={c} style={{ marginTop: "0.4rem" }}>{c}</p>)}

      <Disclose label="How this is worked out">
        <p className="note" style={{ marginTop: 0 }}>
          The machine's cores, memory and graphics are compared with a ladder of workload tiers
          for its use. The tier thresholds are reference points chosen from published software
          requirements, not learned from data.
        </p>
        <p className="note">
          Graphics are ranked against about 280 GPUs benchmarked in Blender Open Data (cut at the
          25th, 60th and 85th percentile); a dedicated card always counts as at least entry level.
          The years figure uses how fast recommended game requirements have grown in Steam's own
          store data: {fit.growth.ram_gb_per_year} GB of memory a year
          {fit.growth.gpu_tier_years ? <>, and one graphics tier about every {fit.growth.gpu_tier_years} years</> : null}.
          That sample is popular titles only, so treat the years as a direction, not a date.
        </p>
        <p className="note">
          {auto
            ? "The use was inferred from which tools from a short list are installed. The list of programs itself is never sent or stored."
            : "The use is what you selected. Nothing here verified it."}
        </p>
      </Disclose>
    </div>
  );
}
