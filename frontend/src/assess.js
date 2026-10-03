import { api } from "./api.js";

// Derive the /api/assess inputs from a signed browser-scan passport plus the
// details the user typed in (device type, age, fault).
//
// A browser cannot read battery health, disk health or Windows 11 eligibility,
// so those are simply not sent -- the server treats a missing value as "not
// measured", never as healthy.
export async function fetchAssessment(payload, extra) {
  const lc = payload.lifecycle || {};
  return api.assess({
    // A browser scan has no measured hardware score, so it starts from the
    // documented default and the adjustments explain every point from there.
    hardware_trust: 75,
    // The ML model's end-of-life probability, signed into the passport.
    eol_risk: lc.eol_risk ?? null,
    age_years: lc.device_age ?? (extra ? Number(extra.device_age) : payload.age_years) ?? null,
    fault_described: lc.fault_described ?? false,
    make_model: payload.make_model || payload.os,
    os: payload.os,
    product_category: extra?.product_category || payload.product_category || null,
    // The browser's own timezone, which the server turns into a country for the
    // grid-carbon figure. Not the IP: the IANA mapping is public domain, nothing
    // personal is sent or stored, and a VPN changes an IP but not a clock.
    timezone: timezone(),
    // The user's explicit correction, if they have made one. Always wins.
    country: extra?.country || null,
  });
}

/** Best-effort IANA zone, e.g. "Asia/Kolkata". Null on anything that refuses. */
function timezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;   // never let a locale quirk break an assessment
  }
}
