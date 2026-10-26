import LifecyclePathways from "./LifecyclePathways.jsx";
import { useCountUp } from "./useCountUp.js";
import AiCaption from "./AiCaption.jsx";
import Reveal from "./Reveal.jsx";
import CarbonTradeoff from "./CarbonTradeoff.jsx";
import Disclose from "./Disclose.jsx";
import UsageFit from "./UsageFit.jsx";
import RepairOutlook from "./RepairOutlook.jsx";
import RepairRights from "./RepairRights.jsx";
import PriceEstimate from "./PriceEstimate.jsx";
import SellChecklist from "./SellChecklist.jsx";
import { Fragment } from "react";
import { INTENTS, orderCards, setIntent, useIntent } from "./intent.js";
import { setTechnical, useTechnical } from "./prefs.js";
import PlainExplanation from "./PlainExplanation.jsx";
import EprelGrade from "./EprelGrade.jsx";

// Lifecycle result dashboard. A vertical stack of equal-width full-width cards —
// nothing sits beside anything of a different height, so the layout stays
// symmetric by construction. Each card uses its horizontal space internally.

// Purple is the ring's resting state -- it only shifts to emerald when the grade
// is genuinely exceptional (A - excellent), so the shift reads as earned rather
// than just another color band.
function scoreColor(s) {
  return s >= 85 ? "var(--green)" : "var(--brand)";
}


export default function AssessmentDashboard({ data, payload, wipe }) {
  const intent = useIntent();
  const technical = useTechnical();
  if (!data) return null;
  const { blend, pipeline, narrative, key_points, pathways, pathways_narrative, win11,
          carbon_tradeoff, usage_fit, uplift, repair_evidence, repair_rights, geo } = data;
  const ageYears = payload?.age_years ?? payload?.lifecycle?.device_age ?? null;

  const col = scoreColor(blend.combined_score);
  const total = pipeline.projected_total_life || 1;
  const used = Math.max(0, total - pipeline.estimated_remaining_years);

  // The result cards, by name, so the visitor's reason for coming (intent.js)
  // can bring its cards to the top. Nothing is hidden by the order.
  const blocks = {
    life: (
      <>
        {/* Card 2 — remaining life + lifespan position */}
        <Reveal delay={120}>
          <div className="dash-card" id="tour-life">
            <div className="k-label">Estimated safe service life</div>
            <div className="split">
              <div className="split-fixed life-metric">
                <div className="metric-big" style={{ color: col }}>
                  {pipeline.estimated_remaining_years}<span>yr left</span>
                </div>
                <div className="life-bar"><i style={{ width: `${(used / total) * 100}%`, background: col }} /></div>
                <div className="note">{used.toFixed(1)} of ~{total} estimated years used</div>
              </div>
              <MiniGauge value={used} max={total} color={col} />
              <div className="split-main">
                <LifespanBar pipeline={pipeline} color={col} />
              </div>
            </div>
          </div>
        </Reveal>
      </>
    ),
    pipeline: (
      <>
        {/* Card 3 — lifecycle pipeline */}
        <Reveal delay={60}>
          <div className="dash-card tech-only">
            <div className="k-label">Lifecycle pipeline</div>
            <div className="timeline">
              {pipeline.stages.map((s, i) => (
                <div className="tl-wrap" key={i}>
                  <div className={`tl-stage ${s.state}`}>
                    <div className="tl-dot" />
                    <div className="tl-name">{s.stage}</div>
                    <div className="tl-year">yr {s.year}</div>
                  </div>
                  {i < pipeline.stages.length - 1 && <div className="tl-arrow">→</div>}
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </>
    ),
    plain: (
      <>
        {/* Card 3b — the result in plain words, worded by a language model and
            checked against the numbers above (S2-08) */}
        <Reveal>
          <PlainExplanation data={data} tier={payload?.tier} />
        </Reveal>
      </>
    ),
    summary: (
      <>
        {/* Card 4 — narrated detail, secondary to the checklist above */}
        <Reveal>
          <div className="dash-card">
            <div className="k-label">Assessment summary <span className="pill muted">rule-based</span></div>
            <p className="ai-summary">{narrative.summary}</p>
            {narrative.lifecycle_note && <p className="note" style={{ marginTop: "0.6rem" }}>{narrative.lifecycle_note}</p>}
            {narrative.confidence_note && (
              <p className="note" style={{ marginTop: "0.6rem", opacity: 0.8 }}>{narrative.confidence_note}</p>
            )}
            <div className="k-label" style={{ marginTop: "1.2rem" }}>Get more from this device</div>
            <div className="sugg-list">
              {narrative.suggestions.filter((s) => s && s.trim()).map((s, i) => (
                <div className="sugg" key={i}>
                  <span className="sugg-n">{i + 1}</span><span>{s}</span>
                </div>
              ))}
            </div>
            <AiCaption source={narrative.source} />
          </div>
        </Reveal>
      </>
    ),
    usage: (
      <>
        {/* Card 4d -- is it up to the work its owner does on it (S2-07) */}
        <Reveal delay={60}>
          <UsageFit fit={usage_fit} lifecycleYears={pipeline.estimated_remaining_years} />
        </Reveal>
      </>
    ),
    carbon: (
      <>
        {/* Card 4e -- the carbon half of the keep-or-replace decision, on the grid
            this device is actually plugged into rather than the single global
            figure the research page quotes. */}
        <Reveal delay={60}>
          <CarbonTradeoff tradeoff={carbon_tradeoff} />
        </Reveal>
      </>
    ),
    pathways: (
      <>
        {/* Card 5 — Lifecycle Pathways: the decision itself, not just the score behind it */}
        <Reveal delay={80}>
          <div id="tour-reco" className="tour-reco-wrap">
            <LifecyclePathways pathways={pathways} narrative={pathways_narrative} />
          </div>
        </Reveal>
      </>
    ),
    outlook: (
      <>
        <Reveal delay={60}>
          <RepairOutlook uplift={uplift} evidence={repair_evidence} />
        </Reveal>
      </>
    ),
    rights: (
      <>
        <Reveal delay={60}>
          <RepairRights rights={repair_rights} />
        </Reveal>
      </>
    ),
    price: (
      <>
        <PriceEstimate defaultOpen={intent === "sell"} grade={blend.grade} ageYears={ageYears}
          productCategory={payload?.product_category} currency={geo?.currency} />
      </>
    ),
    sell: (
      <>
        <SellChecklist wipe={wipe} defaultOpen={intent === "sell"} />
      </>
    ),
    eugrade: data.eprel ? (
      <Reveal delay={60}>
        <EprelGrade eprel={data.eprel} eolRisk={payload?.lifecycle?.eol_risk} />
      </Reveal>
    ) : null,
    security: intent === "safe" ? <SecuritySummary data={data} /> : null,
  };
  const order = orderCards(["life", "pipeline", "plain", "summary", "usage", "carbon", "pathways",
                            "outlook", "eugrade", "rights", "price", "sell", "security"], intent);


  return (
    <div className={`dash ${technical ? "is-technical" : "is-plain"}`}>
      <div className="dash-head">
        <div className="eyebrow">Lifecycle assessment · blended score + explanation</div>
        <h2 className="dash-title">Should this device continue existing?</h2>
        <ViewToggle technical={technical} />
      </div>

      {/* The recommendation first, on every screen. It used to show on phones
          only; in user testing (26 Oct) desktop users asked for the
          recommendation to be clearer, and three of five needed help finding
          the carbon answer and the working. Every row is read from the same
          fields as the cards below, and the links jump to those cards. */}
      <Recommendation data={data} technical={technical} />

      {/* The thesis, stated plainly -- only shows when there's an actual gap
          between what Windows says and what the real numbers say. */}
      <ThesisContrast win11={win11} grade={blend.grade} remainingYears={pipeline.estimated_remaining_years} />

      {/* Card 1 — score dial + waterfall */}
      <Reveal>
        <div className="dash-card" id="tour-score">
          <div className="k-label">Combined score</div>
          <div className="split">
            <div className="split-fixed">
              <Dial value={blend.combined_score} color={col} />
              <div className="metric-grade" style={{ color: col }}>{blend.grade}</div>
              {narrative.punchline && <div className="punchline">{narrative.punchline}</div>}
            </div>
            <div className="split-main">
              <div className="note" style={{ marginBottom: "0.8rem" }}>
                {payload?.tier === "browser profile"
                  ? <>A rule-based score, not a measurement. A browser can't measure hardware condition, so it starts from a fixed {blend.hardware_trust}; every adjustment is shown below.</>
                  : <>A rule-based score. It starts from the measured hardware trust of {blend.hardware_trust}; every adjustment is shown below.</>}
              </div>
              <ScoreWaterfall blend={blend} />
            </div>
          </div>
        </div>
      </Reveal>


      {/* Card 1b — scannable strengths/weaknesses, the thing people actually read */}
      {key_points && (
        <Reveal delay={60}>
          <div className="dash-card">
            <div className="k-label">Key points</div>
            <div className="checklist">
              <div className="check-col">
                {key_points.strengths.map((s, i) => (
                  <div className="check-item good" key={i}><span>✓</span>{s}</div>
                ))}
              </div>
              <div className="check-col">
                {key_points.weaknesses.length === 0 ? (
                  <div className="check-item good"><span>✓</span>Nothing significant flagged</div>
                ) : key_points.weaknesses.map((w, i) => (
                  <div className="check-item bad" key={i}><span>•</span>{w}</div>
                ))}
              </div>
            </div>
          </div>
        </Reveal>
      )}

      <IntentBar intent={intent} />
      {order.map((k) => <Fragment key={k}>{blocks[k] && <span id={`card-${k}`} className="card-anchor" />}{blocks[k]}</Fragment>)}

      {technical && <TheWorking data={data} />}

      <div className="dash-foot">
        <Disclose label="How this score was calculated">
          <p className="note" style={{ marginTop: 0 }}>
            Every number here is computed in code from your device's measured condition — the
            waterfall above shows each adjustment and where it came from. The written summary only
            explains those numbers in plain words; it cannot change them, and it never invents a
            figure that isn't in the breakdown.
          </p>
          <p className="note">
            The baseline hardware-trust score, the grade thresholds and the remaining-life estimate
            are all explicit, reproducible rules rather than model output — so the same device
            always scores the same, and any figure here can be traced back to a measurement.
          </p>
        </Disclose>
      </div>
    </div>
  );
}

/* The recommendation, in a few lines, with links to the cards that explain it.
   Derives every row from the same assessment fields as the full cards, so the
   two can never tell different stories. Rows with no data simply do not render. */
function jumpTo(selector) {
  const el = document.querySelector(selector);
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function Recommendation({ data, technical }) {
  const { blend, pipeline, support_horizon: sh, pathways, carbon_tradeoff: ct } = data;
  const when = (iso) => {
    const dt = new Date(`${iso}T00:00:00`);
    return Number.isNaN(dt.getTime())
      ? iso : dt.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
  };
  const top = Array.isArray(pathways)
    ? (pathways.find((p) => p?.recommended) || pathways.find((p) => p?.status === "best_fit") || pathways[0])
    : null;
  const grade = String(blend.grade || "").replace(/\s*-\s*/, " — ");

  const rows = [];
  if (pipeline?.estimated_remaining_years != null) {
    const y = pipeline.estimated_remaining_years;
    rows.push(["Useful life left", y < 1 ? `~${Math.round(y * 12)} months` : `~${Number(y).toFixed(1)} years`]);
  }
  if (sh) rows.push(["Security updates", sh.is_eol ? `ended ${when(sh.eol_from)}` : `until ${when(sh.eol_from)}`]);
  if (ct) {
    const sc = (ct.scenarios || []).find((s) => s.name === ct.picked);
    const repays = sc ? sc.repays : ct.repays;
    const years = sc ? sc.years : ct.years;
    rows.push(["Would a new one be greener?", repays === false || years == null
      ? "No: it would never repay the carbon spent making it"
      : `Only after ~${years} years of use`]);
  }

  const openWorking = () => {
    if (!technical) setTechnical(true);
    setTimeout(() => jumpTo(".working-table"), 120);
  };

  return (
    <div className="tldr card" id="tour-recommendation">
      <div className="tldr-head">
        <span className="tldr-score">{blend.combined_score}</span>
        <div>
          <div className="tldr-grade">{grade}</div>
          {top?.label && <div className="tldr-rec">AfterLife recommends: <b>{top.label}</b></div>}
          <div className="note">the short version · full detail below</div>
        </div>
      </div>
      {rows.map(([k, v]) => (
        <div key={k} className="tldr-row">
          <span className="tldr-k">{k}</span>
          <span className="tldr-v">{v}</span>
        </div>
      ))}
      <div className="tldr-jumps">
        {ct && <button type="button" className="tldr-jump" onClick={() => jumpTo("#card-carbon")}>Greener? See why ↓</button>}
        <button type="button" className="tldr-jump" onClick={() => jumpTo("#card-pathways")}>All options ↓</button>
        <button type="button" className="tldr-jump" onClick={() => jumpTo("#card-outlook")}>Is repair worth it? ↓</button>
        <button type="button" className="tldr-jump" onClick={openWorking}>How it's worked out ↓</button>
      </div>
    </div>
  );
}

// "Windows says X, AfterLife says Y" -- the tagline made literal. Only appears
// when there's a real gap to show (Win11 ineligible); if Windows already agrees
// the device is fine, there's no contrast to dramatize, so it renders nothing.
function ThesisContrast({ win11, grade, remainingYears }) {
  if (win11 !== "NOT ELIGIBLE") return null;

  let verdict, note;
  if (grade === "A - excellent" || grade === "B - good") {
    verdict = "Still worth keeping"; note = `~${remainingYears} years left`;
  } else if (grade === "C - serviceable") {
    verdict = "Worth hardening, not scrapping"; note = `~${remainingYears} years left`;
  } else {
    verdict = "Hardware's genuinely done"; note = "but resale or repurposing still beat landfill";
  }

  return (
    <div className="thesis-contrast">
      <div className="contrast-side">
        <div className="contrast-label">Windows says</div>
        <div className="contrast-verdict bad">Replace</div>
      </div>
      <div className="contrast-vs">vs</div>
      <div className="contrast-side">
        <div className="contrast-label">AfterLife says</div>
        <div className="contrast-verdict good">{verdict}</div>
        <div className="contrast-note">{note}</div>
      </div>
    </div>
  );
}

// Baseline -> each adjustment -> final, top to bottom, so the score visually
// explains itself instead of landing as an unexplained single number.
function ScoreWaterfall({ blend }) {
  return (
    <div className="waterfall">
      <div className="wf-row base">
        <span className="wf-value">{blend.hardware_trust}</span>
        <span className="wf-label">Hardware</span>
      </div>
      {blend.adjustments.map((a, i) => (
        <div key={i}>
          <div className="wf-arrow">↓</div>
          <div className={`wf-row ${a.delta >= 0 ? "up" : "down"}`}>
            <span className="wf-value">{a.delta > 0 ? `+${a.delta}` : a.delta}</span>
            <span className="wf-label">{a.factor}{a.detail && <span className="wf-detail"> · {a.detail}</span>}</span>
          </div>
        </div>
      ))}
      <div className="wf-arrow">↓</div>
      <div className="wf-row final">
        <span className="wf-value">{blend.combined_score}</span>
        <span className="wf-label">Final</span>
      </div>
    </div>
  );
}

function MiniGauge({ value, max, color }) {
  const r = 40, c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value / max));
  const off = c * (1 - pct);
  return (
    <svg className="mini-gauge" width="104" height="104" viewBox="0 0 104 104">
      <circle cx="52" cy="52" r={r} fill="none" stroke="var(--line)" strokeWidth="8" />
      <circle cx="52" cy="52" r={r} fill="none" stroke={color} strokeWidth="8"
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
        transform="rotate(-90 52 52)" style={{ transition: "stroke 0.6s ease" }} />
      <text x="52" y="50" textAnchor="middle" fontSize="20" fontWeight="500" fill="var(--ink)">
        {Math.round(pct * 100)}%
      </text>
      <text x="52" y="66" textAnchor="middle" fontSize="8.5" fill="var(--muted)">used</text>
    </svg>
  );
}

// A horizontal "life consumed" bar with the stage milestones marked along it —
// the linear complement to the number ("6 yr left") and the radial gauge ("40%").
function LifespanBar({ pipeline, color }) {
  const total = pipeline.projected_total_life || 1;
  const stages = pipeline.stages;
  const nowYear = stages.find((s) => s.state === "current")?.year ?? 0;
  const usedPct = Math.min(100, Math.max(0, (nowYear / total) * 100));
  return (
    <div className="lifespan">
      <div className="lifespan-track">
        <div className="lifespan-fill" style={{ width: `${usedPct}%`, background: color }} />
        {stages.map((s, i) => (
          <div key={i} className={`lifespan-tick ${s.state}`} style={{ left: `${Math.min(100, (s.year / total) * 100)}%` }} />
        ))}
        <div className="lifespan-now" style={{ left: `${usedPct}%`, background: color }} />
      </div>
      <div className="lifespan-scale">
        <span>new</span>
        <span className="lifespan-now-lbl" style={{ left: `${usedPct}%`, color }}>now · {nowYear}yr</span>
        <span>{total}yr</span>
      </div>
    </div>
  );
}

function Dial({ value, color }) {
  const r = 46, c = 2 * Math.PI * r;
  const shown = useCountUp(value);
  const off = c * (1 - shown / 100);
  return (
    <svg className="dial" viewBox="0 0 120 120" width="120" height="120">
      <circle cx="60" cy="60" r={r} fill="none" stroke="var(--line)" strokeWidth="9" />
      <circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="9"
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
        transform="rotate(-90 60 60)" style={{ transition: "stroke-dashoffset 0.8s ease, stroke 0.6s ease" }} />
      <text x="60" y="60" textAnchor="middle" dominantBaseline="central"
        fontFamily="var(--font-display)" fontSize="30" fontWeight="700" letterSpacing="-0.03em" fill="var(--ink)">{Math.round(shown)}</text>
      <text x="60" y="80" textAnchor="middle" fontSize="10" fill="var(--muted)">/ 100</text>
    </svg>
  );
}

/* Plain / technical (S3-03). One preference over the same cards: technical
   opens every "how this is worked out" fold, shows the lifecycle pipeline, the
   detail on each score adjustment and the raw working below; plain keeps the
   verdicts. Stored per browser (prefs.js). */
function ViewToggle({ technical }) {
  return (
    <div className="view-toggle-wrap">
      <div className="view-toggle" role="group" aria-label="How much detail to show">
        <button type="button" aria-pressed={!technical} className={!technical ? "on" : ""}
                onClick={() => setTechnical(false)}>Plain</button>
        <button type="button" aria-pressed={technical} className={technical ? "on" : ""}
                onClick={() => setTechnical(true)}>Technical</button>
      </div>
      <span className="view-toggle-hint">{technical ? "Showing every calculation" : "Switch to Technical to see every calculation"}</span>
    </div>
  );
}

/* Why the visitor came (S3-04): which cards lead, and a way to change it. */
function IntentBar({ intent }) {
  return (
    <div className="intent-bar">
      <span className="note">{intent ? <>Showing first: <b>{INTENTS[intent].lead}</b>.</> : "What do you want to know first?"}</span>
      <div className="intent-chips">
        {Object.entries(INTENTS).map(([k, v]) => (
          <button key={k} type="button" className={`intent-chip ${intent === k ? "on" : ""}`}
                  aria-pressed={intent === k} onClick={() => setIntent(intent === k ? null : k)}>{v.label}</button>
        ))}
      </div>
    </div>
  );
}

/* "Is it safe to use?" in one card: the support dates already on the page,
   and the hardening steps from the pathways. Nothing new is computed. */
function SecuritySummary({ data }) {
  const sh = data.support_horizon, cliff = data.support_cliff;
  const hardening = (data.pathways || []).find((p) => p.key === "hardening");
  const when = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
  return (
    <Reveal>
      <div className="dash-card">
        <div className="k-label">Is it safe to use?</div>
        {sh ? (
          <p style={{ marginTop: "0.3rem" }}>
            {sh.is_eol ? <>Ordinary security updates for {sh.product} {sh.release} ended on <b>{when(sh.eol_from)}</b>.</>
                       : <>{sh.product} {sh.release} gets security updates until <b>{when(sh.eol_from)}</b>.</>}
            {cliff && <> Paid extended updates (ESU) run until <b>{when(cliff.date)}</b>, {cliff.days_away} days from now.</>}
          </p>
        ) : (
          <p className="note" style={{ marginTop: "0.3rem" }}>No published support end date matched this device or operating system.</p>
        )}
        {sh?.note && <p className="note">{sh.note}</p>}
        {hardening?.actions?.length > 0 && (
          <>
            <div className="k-label" style={{ marginTop: "1rem" }}>To stay safer on it</div>
            <div className="sugg-list">
              {hardening.actions.map((a, i) => <div className="sugg" key={i}><span className="sugg-n">{i + 1}</span><span>{a}</span></div>)}
            </div>
          </>
        )}
      </div>
    </Reveal>
  );
}

/* Technical view: the raw working behind the cards, as the server returned it. */
function TheWorking({ data }) {
  const { blend, pipeline, carbon_tradeoff: ct } = data;
  return (
    <div className="dash-card">
      <div className="k-label">The working</div>
      <table className="working-table">
        <tbody>
          <tr><th>Start</th><td>{blend.hardware_trust}</td><td className="note">hardware trust</td></tr>
          {blend.adjustments.map((a, i) => (
            <tr key={i}><th>{a.delta > 0 ? `+${a.delta}` : a.delta}</th><td>{a.factor}</td><td className="note">{a.detail}</td></tr>
          ))}
          <tr><th>= {blend.combined_score}</th><td>{blend.grade}</td><td className="note">grade cut-offs 85 / 70 / 55</td></tr>
          <tr><th>{pipeline.estimated_remaining_years} yr</th><td>estimated years left</td><td className="note">score ÷ 100 × 8</td></tr>
          {ct?.assumptions && (
            <tr><th>{ct.repays ? `${ct.years} yr` : "never"}</th><td>carbon payback ({ct.picked})</td>
              <td className="note">{ct.embodied_kg} kg ÷ ({ct.assumptions.old_tdp_w} W − {ct.assumptions.new_tdp_w} W) × {ct.assumptions.load_factor} × {ct.assumptions.system_overhead} × {ct.assumptions.hours_per_year} h × {ct.grid.gco2_kwh} g/kWh</td></tr>
          )}
        </tbody>
      </table>
      <Disclose label="The full result as the server returned it (JSON)">
        <pre className="working-json">{JSON.stringify(data, null, 2)}</pre>
      </Disclose>
      <p className="note" style={{ marginTop: "0.6rem" }}>Every number and its reason: How it works → Every number we assume.</p>
    </div>
  );
}

