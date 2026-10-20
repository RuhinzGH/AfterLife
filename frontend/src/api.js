// In dev, Vite proxies "/api" to localhost:8000 (see vite.config.js). In prod the
// frontend and backend are on different domains, so VITE_API_BASE points at the
// deployed backend's origin.
const BASE = `${import.meta.env.VITE_API_BASE || ""}/api`;

async function req(path, opts) {
  const res = await fetch(BASE + path, opts);
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

const postJson = (path, body) =>
  req(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const api = {
  // Fired once on app mount, purely to wake the backend -- a free hosting tier
  // sleeps when idle, and that first slow request should not be the one the
  // visitor is waiting on. Deliberately un-awaited and failure-silent.
  warm: () => { fetch(`${BASE}/health`).catch(() => {}); },
  findings: () => req("/findings"),
  sources: () => req("/sources"),
  thesis: () => req("/thesis"),
  // Same payload, one network trip per session. The hero headline and the proof
  // band both read from findings on the landing screen. A failed fetch clears
  // the memo so the next caller retries instead of getting a cached rejection.
  findingsOnce: () => {
    if (!api._findingsMemo) {
      api._findingsMemo = req("/findings").catch((e) => {
        api._findingsMemo = null;
        throw e;
      });
    }
    return api._findingsMemo;
  },
  verify: (passport) => postJson("/verify", { passport }),
  scanPassport: (scan) => postJson("/scan-passport", scan),
  // Deep scan: the exact collector script the command runs, as text, so the
  // page can show it and hash it; and the poll for the collector's upload.
  collectorSource: (file) =>
    fetch(`${BASE}/${file}`).then((r) => {
      if (!r.ok) throw new Error(r.statusText || "could not load script");
      return r.text();
    }),
  pollDeep: (token) => req(`/deep-scan/${token}`),
  // Saved scans: the Supabase access token proves who is asking; the server
  // checks it with Supabase and only ever reads or writes that user's rows.
  myScans: (authToken) => req("/my-scans", { headers: { Authorization: `Bearer ${authToken}` } }),
  saveScan: (passport, scanType, authToken, assessment) =>
    req("/save-scan", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
      body: JSON.stringify({ passport, scan_type: scanType, assessment }),
    }),
  assess: (body) => postJson("/assess", body),
  priceEstimate: (body) => postJson("/price-estimate", body),
  explain: (assessment, tier) => postJson("/explain", { assessment, tier }),
  assumptions: () => req("/assumptions"),
  sensitivity: () => req("/sensitivity"),
  // Redesign endpoints: read-only and computed server-side.
  esu: () => req("/esu"),
  gridCountries: () => req("/grid-countries"),
  carbonCalc: ({ country, deviceClass, oldTdp, newTdp }) => {
    const q = new URLSearchParams();
    if (country) q.set("country", country);
    if (deviceClass) q.set("device_class", deviceClass);
    if (oldTdp != null) q.set("old_tdp_w", String(oldTdp));
    if (newTdp != null) q.set("new_tdp_w", String(newTdp));
    return req(`/carbon-calc?${q}`);
  },
};
