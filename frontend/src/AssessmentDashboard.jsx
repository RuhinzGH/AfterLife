import LifecyclePathways from "./LifecyclePathways.jsx";
import { useCountUp } from "./useCountUp.js";
import AiCaption from "./AiCaption.jsx";
import Reveal from "./Reveal.jsx";
import CarbonTradeoff from "./CarbonTradeoff.jsx";
import Disclose from "./Disclose.jsx";

// Lifecycle result dashboard. A vertical stack of equal-width full-width cards —
// nothing sits beside anything of a different height, so the layout stays
// symmetric by construction. Each card uses its horizontal space internally.

// Purple is the ring's resting state -- it only shifts to emerald when the grade
// is genuinely exceptional (A - excellent), so the shift reads as earned rather
// than just another color band.
function scoreColor(s) {
  return s >= 85 ? "var(--green)" : "var(--brand)";
}


export default function AssessmentDashboard({ data }) {
  if (!data) return null;
  const { blend, pipeline, narrative, key_points, pathways, pathways_narrative, win11,
          carbon_tradeoff } = data;

  const col = scoreColor(blend.combined_score);
  const total = pipeline.projected_total_life || 1;
  const used = Math.max(0, total - pipeline.estimated_remaining_years);

  return (
    <div className="dash">
      <div className="dash-head">
        <div className="eyebrow">Lifecycle assessment · blended score + explanation</div>
        <h2 className="dash-title">Should this device continue existing?</h2>
      </div>

      {/* Phone-only TL;DR. The full dashboard is a long scroll of cards that a
          phone reader mostly will not finish, so the verdict comes first in a
          few lines, read from the same fields as the cards below it. Hidden on
          desktop, where the cards fit on screen. */}
      <MobileTldr data={data} />

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
                Baseline hardware trust {blend.hardware_trust}, adjusted by the ML model and measured condition.
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

      {/* Card 2 — remaining life + lifespan position */}
      <Reveal delay={120}>
        <div className="dash-card" id="tour-life">
          <div className="k-label">Safe service life</div>
          <div className="split">
            <div className="split-fixed life-metric">
              <div className="metric-big" style={{ color: col }}>
                {pipeline.estimated_remaining_years}<span>yr left</span>
              </div>
              <div className="life-bar"><i style={{ width: `${(used / total) * 100}%`, background: col }} /></div>
              <div className="note">{used.toFixed(1)} of ~{total} projected years used</div>
            </div>
            <MiniGauge value={used} max={total} color={col} />
            <div className="split-main">
              <LifespanBar pipeline={pipeline} color={col} />
            </div>
          </div>
        </div>
      </Reveal>

      {/* Card 3 — lifecycle pipeline */}
      <Reveal delay={60}>
        <div className="dash-card">
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

      {/* Card 4 — narrated detail, secondary to the checklist above */}
      <Reveal>
        <div className="dash-card">
          <div className="k-label">Assessment summary</div>
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


      {/* Card 4e -- the carbon half of the keep-or-replace decision, on the grid
          this device is actually plugged into rather than the single global
          figure the research page quotes. */}
      <Reveal delay={60}>
        <CarbonTradeoff tradeoff={carbon_tradeoff} />
      </Reveal>

      {/* Card 5 — Lifecycle Pathways: the decision itself, not just the score behind it */}
      <Reveal delay={80}>
        <div id="tour-reco" className="tour-reco-wrap">
          <LifecyclePathways pathways={pathways} narrative={pathways_narrative} />
        </div>
      </Reveal>


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

// "Windows says X, AfterLife says Y" -- the tagline made literal. Only appears
// when there's a real gap to show (Win11 ineligible); if Windows already agrees
/* The short phone verdict. Derives every row from the same assessment fields
   as the full cards, so the two can never tell different stories. Rows with no
   data simply do not render -- no dashes, no placeholders. */
function MobileTldr({ data }) {
  const { blend, pipeline, support_horizon: sh, pathways } = data;
  const when = (iso) => {
    const dt = new Date(`${iso}T00:00:00`);
    return Number.isNaN(dt.getTime())
      ? iso : dt.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
  };
  const top = Array.isArray(pathways) ? (pathways.find((p) => p?.recommended) || pathways[0]) : null;

  const rows = [];
  if (pipeline?.estimated_remaining_years != null) {
    const y = pipeline.estimated_remaining_years;
    rows.push(["Useful life left", y < 1 ? `~${Math.round(y * 12)} months` : `~${y.toFixed(1)} years`]);
  }
  if (sh) rows.push(["Security updates", sh.is_eol ? `ended ${when(sh.eol_from)}` : `until ${when(sh.eol_from)}`]);
  if (top?.label) rows.push(["Best move", top.label]);

  return (
    <div className="tldr card">
      <div className="tldr-head">
        <span className="tldr-score">{blend.combined_score}</span>
        <div>
          <div className="tldr-grade">{String(blend.grade || "").replace(/\s*-\s*/, " — ")}</div>
          <div className="note">the short version · full detail below</div>
        </div>
      </div>
      {rows.map(([k, v]) => (
        <div key={k} className="tldr-row">
          <span className="tldr-k">{k}</span>
          <span className="tldr-v">{v}</span>
        </div>
      ))}
    </div>
  );
}

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
            <span className="wf-label">{a.factor}</span>
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
