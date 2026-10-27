// One-page passport for printing or saving as a PDF (S3-02).
//
// No PDF library: it builds a small self-contained page and opens the browser's
// own print dialog, where "Save as PDF" makes the file. That keeps the download
// small and the output identical in every browser that can print.
//
// The paper itself is not signed; the QR on it carries the signed passport, so
// whoever holds the printout can scan it and check the signature on the Verify
// page. The page says exactly that.

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** The facts printed for each kind of passport, label first. Empty ones are left out. */
export function passportRows(p) {
  const deep = p.trust_score != null;
  const rows = deep
    ? [
        ["Device", p.device_name || p.make_model],
        ["Processor", p.cpu ? `${p.cpu}${p.cpu_cores ? ` (${p.cpu_cores} cores)` : ""}` : null],
        ["Operating system", p.os],
        ["Memory", p.ram_gb ? `${p.ram_gb} GB` : null],
        ["Storage", [p.storage, p.storage_health].filter(Boolean).join(" · ")],
        ["Battery", p.battery_health],
        ["Age", p.age_years != null ? `about ${p.age_years} years` : null],
        ["Windows 11", p.win11 ? `${p.win11.toLowerCase()}${p.win11_note ? ` (${p.win11_note})` : ""}` : null],
        ["Measured hardware score", `${p.trust_score} / 100`],
        ["Factory reset checked", p.wipe_verified ? `${p.wipe_verified} (${p.wipe_scope})` : null],
      ]
    : [
        ["Device type", p.product_category],
        ["Operating system", p.os],
        ["Graphics", p.gpu],
        ["Processor", p.cpu_cores ? `${p.cpu_cores} logical cores` : null],
        ["Memory", p.ram_gb ? `${p.ram_gb} GB or more (browser reading)` : null],
        ["Age", p.lifecycle?.device_age != null ? `${p.lifecycle.device_age} years (owner's answer)` : null],
        ["Reported fault", p.lifecycle?.fault_themes?.length ? p.lifecycle.fault_themes.join(", ") : null],
      ];
  return rows.filter(([, v]) => v != null && v !== "" && v !== "UNKNOWN");
}

/** The print page's HTML. Exported so it can be tested without opening a window. */
export function passportHtml(doc, { qr = null, final = null, origin = "", link = null } = {}) {
  const p = doc.payload || {};
  const deep = p.trust_score != null;
  const score = final?.score ?? (deep ? p.trust_score : null);
  const grade = final?.grade ?? (deep ? p.grade : null);
  const rows = passportRows(p).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join("");
  const key = (doc.issuer_pubkey || "").slice(0, 16);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>AfterLife passport ${esc(p.device_id)}</title>
<style>
  @page { size: A4; margin: 16mm; }
  * { box-sizing: border-box; }
  body { font: 12px/1.5 "Segoe UI", Roboto, Arial, sans-serif; color: #14201f; margin: 0; }
  .head { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #14201f; padding-bottom: 10px; }
  .brand { font-weight: 700; font-size: 16px; display: flex; align-items: center; gap: 8px; }
  .brand img { width: 22px; height: 22px; }
  .sub { color: #5c6b68; font-size: 11px; margin-top: 2px; }
  .id { font-family: Consolas, monospace; font-size: 11px; margin-top: 4px; }
  .score { text-align: right; }
  .score .n { font-size: 34px; font-weight: 800; line-height: 1; }
  .score .g { font-size: 13px; color: #5c6b68; }
  table { width: 100%; border-collapse: collapse; margin-top: 14px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #e5e9e8; vertical-align: top; }
  th { width: 36%; color: #5c6b68; font-weight: 600; }
  .verify { margin-top: 16px; padding: 12px 14px; border: 1px solid #cdd6d4; border-radius: 8px; display: flex; gap: 14px; align-items: center; }
  .verify img { width: 170px; height: 170px; }
  .key { font-family: Consolas, monospace; font-size: 10px; color: #5c6b68; margin-top: 4px; }
  .foot { margin-top: 16px; font-size: 10px; color: #8a9794; }
</style></head><body>
  <div class="head">
    <div>
      <div class="brand"><img src="${esc(origin)}/afterlife-logo.png" alt="">AfterLife device passport</div>
      <div class="sub">${deep ? "Deep scan (measured on the device)" : "Instant scan (what a browser can see)"} · issued ${esc(p.issued)}</div>
      <div class="id">${esc(p.device_id)}</div>
    </div>
    ${score != null ? `<div class="score"><div class="n">${esc(score)}<span style="font-size:14px;color:#8a9794"> / 100</span></div><div class="g">${esc(grade)}</div></div>` : ""}
  </div>
  <table><tbody>${rows}</tbody></table>
  <div class="verify">
    ${qr ? (link ? `<a href="${esc(link)}"><img src="${qr}" alt="QR code holding the signed passport"></a>` : `<img src="${qr}" alt="QR code holding the signed passport">`) : ""}
    <div>
      <b>Check it yourself.</b> The QR holds the signed passport. Scan it with a phone camera, or open
      ${esc(origin)} and choose "Verify a passport". If anything in it was changed after signing, the check fails.
      ${link ? `<div class="key"><a href="${esc(link)}">Open the verify link</a> (in a PDF viewer, this link works too).</div>` : ""}
      ${key ? `<div class="key">Signing key starts ${esc(key)}…</div>` : ""}
    </div>
  </div>
  <div class="foot">Printed from AfterLife on ${esc(new Date().toISOString().slice(0, 10))}. This sheet is a copy for reading;
    the signature lives in the QR. ${score != null && final ? "The score shown is the full assessment's; the signed passport holds the measured facts above." : ""}</div>
</body></html>`;
}

export function openPassportPdf(doc, opts = {}) {
  const w = window.open("", "_blank", "width=820,height=1000");
  if (!w) {
    alert("Please allow pop-ups for this site to save the passport as a PDF.");
    return false;
  }
  w.document.write(passportHtml(doc, { ...opts, origin: window.location.origin }));
  w.document.close();
  // Printed from here (the app's own script): the site's security policy blocks
  // scripts written into the new page. A short wait lets the logo and QR load.
  const go = () => { try { w.focus(); w.print(); } catch { /* window closed */ } };
  if (w.document.readyState === "complete") setTimeout(go, 400);
  else w.addEventListener("load", () => setTimeout(go, 250));
  return true;
}
