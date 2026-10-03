import Disclose from "./Disclose.jsx";
import SourceNote from "./SourceNote.jsx";

// Two research results rendered on the Our Research page.

/* ------------------------------------------------ SSDs are not simply better */
export function FailSlow({ data }) {
  if (!data?.ssd) return null;
  const windows = ["5min", "15min", "30min", "60min"];
  const pct = (d, w) => d[`slow_drive_pct_${w}`];

  return (
    <div className="card pad-lg">
      <h2>SSDs stutter less, but stall for longer</h2>
      <div className="sub">
        {(data.ssd.drives + data.hdd.drives).toLocaleString()} drives · share running
        abnormally slow, by how long the slowdown lasted
      </div>

      <div className="fs-grid">
        <div className="fs-head"><span /><span>5 min</span><span>15 min</span><span>30 min</span><span>60 min</span></div>
        {[data.ssd, data.hdd].map((d) => (
          <div className="fs-row" key={d.label}>
            <span className="fs-label">{d.label}</span>
            {windows.map((w) => (
              <span className="fs-cell" key={w}>{pct(d, w).toFixed(1)}%</span>
            ))}
          </div>
        ))}
        <div className="fs-row ratio">
          <span className="fs-label">SSD ÷ HDD</span>
          {windows.map((w) => (
            <span className={`fs-cell ${data.ssd_hdd_ratio[w] > 1 ? "worse" : "better"}`} key={w}>
              {data.ssd_hdd_ratio[w].toFixed(2)}
            </span>
          ))}
        </div>
      </div>

      <p className="card-takeaway">
        At five minutes an SSD is less than half as likely as a hard disk to be running slow. At
        sixty minutes it is <b>more</b> likely. Solid-state drives fail differently rather than
        simply less — which matters if you are deciding whether a slow machine needs replacing or
        just a new drive.
      </p>

      <div className="card-foot">
        <Disclose label="Limits of this measurement">
          <ul className="tried-also">
            {(data.caveats || []).map((c, i) => <li key={i} className="note">{c}</li>)}
            <li className="note">
              Datacentre drives under datacentre workloads. A laptop SSD is not this population,
              and the direction of the finding is more transferable than the rates.
            </li>
          </ul>
        </Disclose>
        <SourceNote
          title="Fail-slow analysis, Alibaba fleet"
          dataset="Per-drive latency records for NVMe SSDs and SATA HDDs"
          sample={`${data.ssd.drives.toLocaleString()} SSD, ${data.hdd.drives.toLocaleString()} HDD`}
          method="Share of drives exhibiting abnormally high latency sustained over each window"
          published={data.source}
          caveat="Workload stands in for cluster identity, and no throughput filter is available, so rates are an upper bound."
        />
      </div>
    </div>
  );
}

/* ------------------------------------- the comparison, cross-validated */
export function CostSweep({ data }) {
  if (!data?.cv_5fold || Object.keys(data.cv_5fold).length === 0) return null;
  const ratios = Object.keys(data.cost_ratio_sweep || {});
  const winners = new Set(Object.values(data.cost_ratio_sweep || {}));
  const robust = winners.size === 1;

  return (
    <div className="card pad-lg">
      <h2>Does the answer survive changing the question?</h2>
      <div className="sub">
        five-fold cross-validation, and the cost of a missed end-of-life device swept
        from {ratios[0]}× to {ratios[ratios.length - 1]}×
      </div>

      <div className="modeltable" style={{ marginTop: "0.9rem" }}>
        <div className="mt-head cv">
          <span>model</span><span>macro F1</span><span>EOL recall</span><span>cost score</span>
        </div>
        {Object.entries(data.cv_5fold).map(([name, m]) => (
          <div className="mt-row cv" key={name}>
            <span>{name}</span>
            <span>{m.macro_f1_mean.toFixed(3)} <span className="mt-dim">±{m.macro_f1_std.toFixed(3)}</span></span>
            <span>{m.eol_recall_mean.toFixed(3)} <span className="mt-dim">±{m.eol_recall_std.toFixed(3)}</span></span>
            <span>{m.cost5_mean?.toFixed(3)} <span className="mt-dim">±{m.cost5_std?.toFixed(3)}</span></span>
          </div>
        ))}
      </div>

      <p className="card-takeaway">
        {robust ? (
          <>
            <b>{[...winners][0]}</b> is selected at every cost ratio from {ratios[0]} to{" "}
            {ratios[ratios.length - 1]}, while <b>{data.accuracy_best_model}</b> wins on raw
            accuracy. The cost-sensitive choice is not a knife-edge that depends on picking exactly
            the right weighting — it holds across the whole range anyone would argue for.
          </>
        ) : (
          <>The selected model changes with the cost ratio, so the choice depends on the weighting
          and the weighting has to be defended.</>
        )}
      </p>

      <div className="card-foot">
        <Disclose label="What the cost score means">
          <p className="note" style={{ marginTop: 0 }}>
            A weighted error count where missing a genuinely end-of-life device costs N times more
            than wrongly flagging a healthy one. Lower is better. Sweeping N rather than fixing it
            is the point: a result that only holds at one arbitrary weighting is not a result.
          </p>
          <p className="note">
            Standard deviations are across the five folds. They are small relative to the gaps
            between models, which is what makes the ranking meaningful rather than noise.
          </p>
        </Disclose>
        <SourceNote
          title="Cross-validated model comparison"
          dataset="Open Repair Alliance IT devices"
          sample={`${data.n_train?.toLocaleString()} train / ${data.n_test?.toLocaleString()} test, 5-fold CV`}
          method="Four candidates compared on macro F1, end-of-life recall, and a cost score swept across ratios 1–10"
          published="scripts/research_experiment.py"
        />
      </div>
    </div>
  );
}
