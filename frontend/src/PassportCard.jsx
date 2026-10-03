// Shared, elegant device-passport card. Renders a signed scan-passport doc
// ({payload, signature, issuer_pubkey, verified}) with an optional QR and verify badge.

function Field({ k, v, wide }) {
  return (
    <div className={`pc-field${wide ? " wide" : ""}`}>
      <span className="pc-k">{k}</span>
      <span className="pc-v">{v ?? "—"}</span>
    </div>
  );
}

// `final` is the assessed blend ({score, grade}), passed in wherever the card
// renders next to an assessment. The card used to headline the SIGNED
// hardware-trust score (say 95) while the dashboard beside it concluded 85
// after security and battery deductions -- two different numbers wearing the
// same grade, reading as a bug. The signed payload is not rewritten; the
// headline simply shows the number the page actually concludes with, and
// hardware trust drops to a labelled sub-line. Without `final` (the Verifier,
// or while the assessment is still loading) the trust score keeps the headline
// but is explicitly labelled for what it is.
export default function PassportCard({ doc, qr, verified, final = null }) {
  const p = doc.payload || doc;
  const ok = verified ?? doc.verified;
  const isDeep = p.trust_score != null;
  const w11Color = { ELIGIBLE: "green", "NOT ELIGIBLE": "red", INDETERMINATE: "amber" }[p.win11] || "muted";

  return (
    <div className="passport-card">
      <div className="pc-glow" />
      <div className="pc-top">
        <div>
          <div className="pc-brand">Afterlife · Device Passport</div>
          <div className="pc-id">{p.device_id}</div>
          {isDeep && <div className="note" style={{ marginTop: "0.25rem" }}>{p.make_model}</div>}
        </div>
        <div style={{ textAlign: "right" }}>
          <span className={`pill ${isDeep ? "amber" : "muted"}`}>{p.tier || "profile"}</span>
          {isDeep && (final ? (
            <div className="pc-trust">
              <span className="pc-trust-v">{final.score}</span>
              <span className="pc-trust-g">{final.grade}</span>
              <span className="pc-trust-sub">hardware trust {p.trust_score}</span>
            </div>
          ) : (
            <div className="pc-trust">
              <span className="pc-trust-k">hardware trust</span>
              <span className="pc-trust-v">{p.trust_score}</span>
              <span className="pc-trust-g">{p.grade}</span>
            </div>
          ))}
        </div>
      </div>

      {isDeep ? (
        <div className="pc-grid">
          <Field k="Processor" v={p.cpu} wide />
          <Field k="Operating system" v={p.os} />
          <Field k="Memory" v={p.ram_gb ? `${p.ram_gb} GB` : null} />
          <Field k="Storage" v={p.storage_health ? `${p.storage} · ${p.storage_health}` : p.storage} wide />
          <Field k="Battery" v={p.battery_health} />
          <Field k="Age" v={p.age_years ? `~${p.age_years} yr` : null} />
          <div className="pc-field wide">
            <span className="pc-k">Windows 11</span>
            <span className="pc-v">
              <span className={`life-tag ${w11Color === "green" ? "fix" : w11Color === "red" ? "eol" : "rep"}`}>
                {p.win11}
              </span>
              <span className="note" style={{ marginLeft: "0.5rem" }}>{p.win11_note}</span>
            </span>
          </div>
          <Field k="Recommended use" v={p.recommended_use} wide />
          <Field k="Est. safe service life" v={p.est_safe_years} />
          {p.repairability && (
            <Field k="Brand repairability" v={`${p.repairability.grade} · ${p.repairability.source}`} wide />
          )}
        </div>
      ) : (
        <div className="pc-grid">
          <Field k="Operating system" v={p.os} wide />
          <Field k="Graphics" v={p.gpu || "not exposed"} wide />
          <Field k="CPU cores" v={p.cpu_cores ? `${p.cpu_cores} logical` : null} />
          <Field k="Memory" v={p.ram_gb ? `${p.ram_gb} GB+` : null} />
          <Field k="Architecture" v={p.architecture} />
          <Field k="Battery wear" v="not visible to a browser" />
          <Field k="Display" v={p.screen} />
          <Field k="Timezone" v={p.timezone} />
        </div>
      )}

      {/* Only ever present when the check passed, and it lives inside the signed
          payload -- so a buyer scanning this QR is reading something the seller
          could not have edited without breaking the signature. The scope caveat
          travels with it rather than being left on the seller's screen. */}
      {p.wipe_verified && (
        <div className="pc-wipe">
          <span className="pc-wipe-mark">✓</span>
          <span>
            <b>Looked factory-fresh on {p.wipe_verified}</b>
            <span className="note"> — no leftover accounts, files, saved networks or
            installed software, and Windows had been reset recently. {p.wipe_scope}.</span>
          </span>
        </div>
      )}

      {p.lifecycle && (
        <div className="pc-lifecycle">
          <div className="pc-k" style={{ marginBottom: "0.5rem" }}>
            Lifecycle outlook · {p.lifecycle.basis}
          </div>
          <div className="pc-life-head">
            <span className={`life-tag ${{ "End of life": "eol", Repairable: "rep", Fixed: "fix" }[p.lifecycle.prediction]}`}>
              {p.lifecycle.prediction}
            </span>
            <span className="note">end-of-life risk {(p.lifecycle.eol_risk * 100).toFixed(0)}%</span>
          </div>
          <div style={{ marginTop: "0.6rem" }}>
            {p.lifecycle.probabilities.map((pr) => (
              <div className="rowbar" key={pr.label} style={{ gridTemplateColumns: "6rem 1fr 2.6rem" }}>
                <span className="lbl">{pr.label}</span>
                <span className="meter">
                  <i style={{
                    width: `${pr.probability * 100}%`,
                    background: { "End of life": "var(--red)", Repairable: "var(--amber)", Fixed: "var(--green)" }[pr.label],
                  }} />
                </span>
                <span className="num">{(pr.probability * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="pc-foot">
        {qr && <img className="pc-qr" src={qr} alt="passport QR" />}
        <div className="pc-sign">
          {ok != null && (
            <div className={`badge ${ok ? "ok" : "bad"}`}>
              {ok ? "✓ signed & verified" : "✗ signature invalid"}
            </div>
          )}
          <div className="note" style={{ marginTop: "0.5rem" }}>
            {ok === false
              ? "This passport was altered after issue. Do not trust it."
              : "Digitally signed and tamper-proof. ⚠ Don't attempt to edit any field — it will instantly invalidate this passport."}
            {p.completeness_pct != null && (
              <> Profile completeness {p.completeness_pct}% of what a browser can read.</>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
