import Disclose from "./Disclose.jsx";

// Does replacing THIS device actually save carbon, on the grid it is plugged into?
//
// The research page answers this once, globally, with the most conservative
// figure available ("~21 years even on the dirtiest grid"). That is honest but
// it is not the reader's number, and it buries the variable that decides the
// answer: the break-even spans an order of magnitude between grids. On a clean
// one, replacing effectively never repays; on a coal-heavy one it repays in
// under two decades.
//
// Two things this card must keep visible, because both change what the number
// means:
//   - whether the grid is the user's own or the world-average fallback
//   - whether the embodied carbon is this model's declared LCA or a default
// Both arrive as `basis` fields and both are shown, not smoothed away.

function Row({ label, value, note }) {
  return (
    <li className="ct-row">
      <span className="ct-row-label">{label}</span>
      <span className="ct-row-value">{value}</span>
      {note && <span className="ct-row-note">{note}</span>}
    </li>
  );
}

export default function CarbonTradeoff({ tradeoff }) {
  if (!tradeoff || !tradeoff.grid) return null;

  const { grid, repays, years, embodied_kg, embodied_basis,
          annual_saving_kg, annual_kwh_saved, headline, assumptions } = tradeoff;

  const worldFallback = grid.basis === "world";
  const declared = embodied_basis === "matched" || embodied_basis === "declared";
  const classMedian = embodied_basis === "class";

  // Under about a decade the replacement argument is at least arguable; beyond
  // it, keeping the device is the clear answer. The boundary is a presentation
  // choice, not a threshold anything is computed from.
  const tone = !repays || years > 25 ? "good" : years > 10 ? "warn" : "bad";

  return (
    <div className={`dash-card ct ${tone}`}>
      <div className="k-label">
        Would replacing it be greener?
        <span className={`pill ${worldFallback ? "muted" : "cyan"}`}>
          {worldFallback ? "world average" : grid.region}
        </span>
      </div>

      <p className="ct-headline">{headline}</p>

      <ul className="ct-rows">
        <Row label="Grid carbon intensity"
             value={`${grid.gco2_kwh.toFixed(0)} gCO₂e/kWh`}
             note={worldFallback
               ? "world average — we could not place you"
               : `${grid.region}, ${grid.year}`} />
        <Row label="Making a replacement"
             value={`${Math.round(embodied_kg)} kg CO₂e`}
             note={declared ? "declared for this model"
               : classMedian ? "median for this device class" : "default estimate"} />
        {repays && (
          <>
            <Row label="Energy a newer machine saves"
                 value={`${annual_kwh_saved.toFixed(0)} kWh/yr`}
                 note="on the duty cycle below" />
            <Row label="Carbon that saves"
                 value={`${annual_saving_kg.toFixed(1)} kg/yr`}
                 note="on this grid" />
          </>
        )}
      </ul>

      {worldFallback && (
        <p className="note ct-warn">
          We could not determine your country, so this uses the world average.
          Your actual grid could make replacement repay anywhere from roughly
          fifteen years to never.
        </p>
      )}

      <Disclose summary="How this is worked out, and what is assumed">
        <p className="note">
          Keeping an older machine costs electricity; replacing it costs the
          carbon of manufacturing, which is roughly an order of magnitude more
          than a year of running it. The break-even is how long the newer
          machine's efficiency takes to pay that back. Which side wins depends
          almost entirely on how dirty the electricity is — so "reuse always
          wins" is not automatically true, and this works it out rather than
          assuming it.
        </p>
        <p className="note">{assumptions?.note}</p>
        <p className="note">
          Comparing a {assumptions?.old_tdp_w}W machine kept in service against a
          {" "}{assumptions?.new_tdp_w}W replacement doing the same work, at{" "}
          {assumptions?.hours_per_year} hours a year.
        </p>
        <p className="note src">
          Grid intensity: {grid.source}
          {declared && <> · Embodied carbon: manufacturer LCA declaration via Boavizta.</>}
          {classMedian && <> · Embodied carbon: median of manufacturer LCA declarations for this device class, via Boavizta.</>}
        </p>
      </Disclose>
    </div>
  );
}
