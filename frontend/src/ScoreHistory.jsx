import { useMemo, useState } from "react";
import { relativeTime } from "./deviceStore.js";

// A device's grade is not a fact, it is a reading that moves -- batteries wear,
// support windows close, disks accumulate errors. Every one of those readings was
// already being stored; nothing was ever showing them next to each other.
//
// Deliberately a single series on a single axis. The obvious temptation is to
// overlay battery % on the same chart, which would mean two different scales
// sharing one y-axis and a line whose slope means nothing. Battery lives in the
// detail rows below instead.

const W = 520, H = 150, PAD_L = 30, PAD_R = 14, PAD_T = 14, PAD_B = 26;

// Battery health arrives as a display string ("74%", "74.2 % of design capacity"),
// because that is what the passport carries for humans to read. Pulling the number
// back out is preferable to storing it twice and letting the two drift.
function pct(v) {
  if (typeof v === "number") return v;
  const m = String(v ?? "").match(/(\d+(?:\.\d+)?)\s*%/);
  return m ? Number(m[1]) : null;
}

//: Only metrics that are genuinely comparable across scans and stored on every
//: row. Security exposure is deliberately absent: the CVE corpus is refreshed
//: independently of any device, so a "rise" in exposure between two scans would
//: mostly measure our own data updates rather than anything about the machine.
const METRICS = [
  { key: "score", label: "Overall score", pick: (s) => s.passport?.assessment?.blend?.combined_score },
  { key: "battery", label: "Battery health", pick: (s) => pct(s.passport?.payload?.battery_health) },
];

export default function ScoreHistory({ history }) {
  const [hover, setHover] = useState(null);
  const [metric, setMetric] = useState("score");

  // Which metrics this particular device actually has more than one reading for.
  // An instant-scan-only device has no battery series, and offering an empty tab
  // is worse than not offering it.
  const available = useMemo(() => METRICS.filter((m) =>
    (history || []).filter((s) => typeof m.pick(s) === "number").length >= 2
  ), [history]);

  const active = available.find((m) => m.key === metric) || available[0];

  const points = useMemo(() => {
    if (!active) return [];
    return (history || [])
      .map((s) => ({
        t: new Date(s.created_at).getTime(),
        score: active.pick(s),
        grade: s.passport?.assessment?.blend?.grade,
        deep: s.scan_type === "deep",
        iso: s.created_at,
      }))
      .filter((r) => typeof r.score === "number" && !Number.isNaN(r.t))
      .sort((a, b) => a.t - b.t);
  }, [history, active]);

  // One point is not a trend. Showing a chart of it would be decoration.
  if (!active || points.length < 2) return null;

  const t0 = points[0].t, t1 = points[points.length - 1].t;
  const span = t1 - t0 || 1;
  // Fixed 0-100 domain rather than fitting to the data: a score that moved 82->80
  // on an auto-fitted axis looks like a collapse. The whole point of this chart is
  // proportion, so the axis has to be the real one.
  const x = (t) => PAD_L + ((t - t0) / span) * (W - PAD_L - PAD_R);
  const y = (s) => PAD_T + (1 - s / 100) * (H - PAD_T - PAD_B);

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.t).toFixed(1)},${y(p.score).toFixed(1)}`).join(" ");
  const first = points[0], last = points[points.length - 1];
  const delta = last.score - first.score;

  return (
    <div className="score-history">
      <div className="hist-head">
        <div className="k-label" style={{ marginTop: "1.1rem", marginBottom: 0 }}>
          {active.label} over time
        </div>
        {available.length > 1 && (
          <div className="seg hist-seg">
            {available.map((m) => (
              <button
                key={m.key}
                type="button"
                className={active.key === m.key ? "on" : ""}
                onClick={() => setMetric(m.key)}
              >
                {m.label}
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="note" style={{ marginTop: "0.25rem", marginBottom: "0.5rem" }}>
        {delta === 0
          ? `Unchanged at ${last.score} across ${points.length} scans.`
          : `${delta > 0 ? "Up" : "Down"} ${Math.abs(delta).toFixed(delta % 1 ? 1 : 0)} point${Math.abs(delta) === 1 ? "" : "s"} `
            + `across ${points.length} scans, ${relativeTime(first.iso)} to ${relativeTime(last.iso)}.`}
      </p>

      <div className="hist-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} className="hist-svg" role="img"
             aria-label={`Combined score across ${points.length} scans`}>
          {[0, 50, 100].map((g) => (
            <g key={g}>
              <line x1={PAD_L} x2={W - PAD_R} y1={y(g)} y2={y(g)} className="hist-grid" />
              <text x={PAD_L - 6} y={y(g)} className="hist-axis" textAnchor="end" dominantBaseline="middle">{g}</text>
            </g>
          ))}

          <path d={path} className="hist-line" fill="none" />

          {points.map((p, i) => (
            <circle
              key={i}
              cx={x(p.t)} cy={y(p.score)} r={hover === i ? 6 : 4.5}
              className={`hist-dot ${p.deep ? "deep" : "instant"}`}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
        </svg>

        {hover != null && (
          <div className="hist-tip">
            <b>{points[hover].score}</b>
            {active.key === "score" && points[hover].grade ? ` · ${points[hover].grade}` : "%"}
            <span className="note">
              {points[hover].deep ? "Deep scan" : "Instant scan"} · {relativeTime(points[hover].iso)}
            </span>
          </div>
        )}
      </div>

      <div className="hist-legend">
        <span><i className="hist-key deep" /> deep scan</span>
        <span><i className="hist-key instant" /> instant scan</span>
        {points.some((p) => !p.deep) && points.some((p) => p.deep) && (
          <span className="note">
            Instant scans read less, so they usually sit lower — a dip between two dot types
            is a change of method, not of the machine.
          </span>
        )}
      </div>
    </div>
  );
}
