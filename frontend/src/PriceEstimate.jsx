import { useEffect, useState } from "react";
import { api } from "./api.js";
import { ChevronDown, ChevronUp } from "./icons.jsx";
import Disclose from "./Disclose.jsx";

// Resale estimate (S2-07). Opt-in, because it needs one thing the scan cannot
// read: what the device cost new. The formula is in afterlife/pricing.py and is
// shown in full under the result; the grade is the one this assessment awarded.

const CATEGORIES = ["Laptop", "Desktop computer", "Tablet", "Mobile", "Games console"];
const COSMETIC = ["Like new", "Good", "Fair", "Poor"];

function money(n, currency) {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(n);
  } catch {
    return `${currency} ${Math.round(n).toLocaleString()}`;
  }
}

export default function PriceEstimate({ grade, ageYears, productCategory, currency: localCurrency, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => { if (defaultOpen) setOpen(true); }, [defaultOpen]);   // chose "sell" after the page loaded
  const [currency, setCurrency] = useState(localCurrency || "USD");
  const [category, setCategory] = useState(productCategory || "Laptop");
  const [cosmetic, setCosmetic] = useState("Good");
  const [price, setPrice] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const currencies = [...new Set([localCurrency || "USD", "USD", "EUR", "INR"])];

  async function run() {
    const n = Number(price);
    if (!n || n <= 0) { setErr("Enter what it cost new."); return; }
    setBusy(true); setErr(null);
    try {
      setRes(await api.priceEstimate({
        price_new: n, product_category: category, grade, cosmetic, currency,
        age_years: ageYears == null || ageYears === "" ? null : Number(ageYears),
      }));
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  if (!open) {
    return (
      <button className="trigger-card" onClick={() => setOpen(true)}>
        <span className="trigger-icon" aria-hidden="true">💰</span>
        <span className="trigger-text">
          <span className="trigger-title">What is it worth second-hand?</span>
          <span className="trigger-sub">A rough resale range from its age and condition</span>
        </span>
        <span className="trigger-chevron"><ChevronDown /></span>
      </button>
    );
  }

  const i = res?.inputs;
  return (
    <div className="dash-card">
      <div className="card-head-row">
        <div className="k-label" style={{ marginBottom: 0 }}>Resale estimate</div>
        <button className="collapse-x" onClick={() => setOpen(false)} aria-label="Collapse"><ChevronUp /></button>
      </div>

      {!res ? (
        <div className="form">
          <div className="row2">
            <div className="field">
              <label>What did it cost new?</label>
              <input type="number" min="1" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)}
                placeholder={currency === "INR" ? "e.g. 60000" : "e.g. 900"} />
            </div>
            <div className="field">
              <label>Currency</label>
              <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
                {currencies.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div className="row2">
            <div className="field">
              <label>Device type</label>
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Scratches and dents (your own view)</label>
              <select value={cosmetic} onChange={(e) => setCosmetic(e.target.value)}>
                {COSMETIC.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <p className="note">The scan cannot see the outside of the device, so this answer is yours and is not checked.</p>
          {err && <div className="badge bad">⚠ {err}</div>}
          <button className="cta" onClick={run} disabled={busy}>{busy ? "Working it out…" : "Estimate resale value"}</button>
        </div>
      ) : (
        <>
          <div className="metric-big" style={{ fontSize: "2rem" }}>
            {money(res.low, res.currency)} – {money(res.high, res.currency)}
          </div>
          <p className="note" style={{ marginTop: "0.3rem" }}>
            For a {i.age_years}-year-old {i.category.toLowerCase()} graded {grade}, in “{i.cosmetic}” outer condition.
          </p>
          {res.potential && (
            <p className="note" style={{ marginTop: "0.6rem" }}>
              Repaired up to <b>{res.potential.grade}</b> (see the repair outlook above), the same formula gives{" "}
              <b>{money(res.potential.low, res.currency)} – {money(res.potential.high, res.currency)}</b>.
            </p>
          )}
          <div className="disclaimer" style={{ marginTop: "0.9rem" }}>
            <span>⚠</span>
            <span><b>An estimate, not an appraisal.</b> Inspect the device yourself before buying or selling on this number.</span>
          </div>
          <Disclose label="The formula, with this device's numbers">
            <p className="note" style={{ marginTop: 0 }}>
              price new {money(i.price_new, res.currency)} × age factor {i.age_factor} (losing {Math.round(i.yearly_loss * 100)}% a
              year for {i.age_years} years) × condition {i.grade_factor} ({i.grade}) × outer condition {i.cosmetic_factor},
              then ±15% for the range, and never above the price new.
            </p>
            <p className="note">
              The yearly loss and the condition factors are stated assumptions, not measurements: there
              is no public dataset of used computer prices by condition to learn them from.
            </p>
          </Disclose>
          <button className="ghost" style={{ marginTop: "0.8rem" }} onClick={() => setRes(null)}>Change the answers</button>
        </>
      )}
    </div>
  );
}
