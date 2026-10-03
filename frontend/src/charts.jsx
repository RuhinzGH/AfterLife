// Lightweight inline-SVG charts — no external chart library, CSP-safe.

export function DecayChart({ decay }) {
  const s7 = (decay.series["Windows 7"] || []).filter((d) => d.month >= -12);
  const s10 = (decay.series["Windows 10"] || []).filter((d) => d.month >= -12);
  const proj = decay.projection || [];
  const W = 640, H = 260, P = { t: 14, r: 16, b: 28, l: 34 };
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const X0 = -12, X1 = 84, Y1 = 80;
  const sx = (m) => P.l + ((m - X0) / (X1 - X0)) * iw;
  const sy = (v) => P.t + ih - (v / Y1) * ih;
  const path = (pts) => pts.map((p, i) => (i ? "L" : "M") + sx(p.month) + "," + sy(p.share)).join(" ");
  const last = s10[s10.length - 1];

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="OS decay after end of support">
      {[0, 20, 40, 60, 80].map((v) => (
        <g key={v}>
          <line className="grid-line" x1={P.l} x2={P.l + iw} y1={sy(v)} y2={sy(v)} />
          <text className="axis-txt" x={P.l - 6} y={sy(v) + 4} textAnchor="end">{v}%</text>
        </g>
      ))}
      <line className="grid-line" x1={sx(0)} x2={sx(0)} y1={P.t} y2={sy(0)} strokeDasharray="3 3" />
      <line className="grid-line" x1={P.l} x2={P.l + iw} y1={sy(5)} y2={sy(5)} strokeDasharray="3 3" />
      {[0, 24, 48, 72].map((m) => (
        <text key={m} className="axis-txt" x={sx(m)} y={sy(0) + 18} textAnchor="middle">{m > 0 ? "+" + m : m}</text>
      ))}
      {proj.length > 0 && (
        <polygon
          fill="rgba(139,92,246,0.18)"
          points={
            proj.map((d) => `${sx(d.month)},${sy(Math.min(d.hi, Y1))}`).join(" ") + " " +
            proj.slice().reverse().map((d) => `${sx(d.month)},${sy(d.lo)}`).join(" ")
          }
        />
      )}
      <path d={path(s7)} fill="none" stroke="var(--second)" strokeWidth="2.2" strokeLinejoin="round" />
      <path d={path(s10)} fill="none" stroke="var(--brand)" strokeWidth="2.2" strokeLinejoin="round" />
      {last && proj.length > 0 && (
        <path
          d={"M" + sx(last.month) + "," + sy(last.share) + " " + proj.map((d) => "L" + sx(d.month) + "," + sy(d.fit)).join(" ")}
          fill="none" stroke="var(--brand)" strokeWidth="2" strokeDasharray="5 4"
        />
      )}
      <text className="lbl" x={sx(-11)} y={sy(38)} fill="var(--second)">Win 7</text>
      <text className="lbl" x={sx(2)} y={sy(30)} fill="var(--brand)">Win 10</text>
    </svg>
  );
}

export function HBars({ data, unit = "", colorFn }) {
  const max = Math.max(...data.map((d) => d.value));
  return (
    <div>
      {data.map((d, i) => (
        <div className="rowbar" key={d.label}>
          <span className="lbl">{d.label}</span>
          <span className="meter">
            {/* The bar grows from nothing to its share when the row scrolls into
                view. scaleX, not width, so it never touches layout -- and the
                width is still the real number, so a browser that ignores the
                animation shows a correct chart rather than an empty one. */}
            <i
              style={{
                width: `${(d.value / max) * 100}%`,
                background: colorFn ? colorFn(d) : "var(--brand)",
                "--i": i,
              }}
            />
          </span>
          <span className="num">{d.value}{unit}</span>
        </div>
      ))}
    </div>
  );
}
