import { useEffect, useState } from "react";

// Why the visitor came (S3-04): to sell or pass the device on, to keep it
// going, or to find out whether it is safe to use. The results page leads with
// the cards that answer that question; nothing is hidden, only reordered.
// Remembered for the browser session only (a per-visit convenience), and the
// page works the same if storage is blocked.

export const INTENTS = {
  sell: { label: "Sell or pass it on", lead: "what it is worth and how to hand it over" },
  keep: { label: "Keep it going", lead: "what fixing it buys and whether it suits your work" },
  safe: { label: "Is it safe to use?", lead: "security updates and what to do about them" },
};

const KEY = "afterlife-intent";
const EVT = "afterlife-intent-change";

export function getIntent() {
  try {
    const v = sessionStorage.getItem(KEY);
    return v in INTENTS ? v : null;
  } catch {
    return null;
  }
}

export function setIntent(v) {
  try {
    if (v in INTENTS) sessionStorage.setItem(KEY, v);
    else sessionStorage.removeItem(KEY);
  } catch { /* storage blocked: the choice lasts until the page closes */ }
  window.dispatchEvent(new CustomEvent(EVT, { detail: v in INTENTS ? v : null }));
}

export function useIntent() {
  const [v, setV] = useState(getIntent);
  useEffect(() => {
    const h = (e) => setV(e.detail !== undefined ? e.detail : getIntent());
    window.addEventListener(EVT, h);
    return () => window.removeEventListener(EVT, h);
  }, []);
  return v;
}

//: Which result cards lead for each intent, in order. Keys match the card
//: blocks in AssessmentDashboard.jsx.
export const LEAD_CARDS = {
  sell: ["price", "sell", "outlook"],
  keep: ["outlook", "eugrade", "usage", "life"],
  safe: ["security", "pathways"],
};

/** The card order for an intent: its lead cards first, then the rest as usual. */
export function orderCards(defaultOrder, intent) {
  const lead = (LEAD_CARDS[intent] || []).filter((k) => defaultOrder.includes(k));
  return [...lead, ...defaultOrder.filter((k) => !lead.includes(k))];
}
