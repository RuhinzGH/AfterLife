import { api } from "./api.js";

// Derive the /api/assess inputs from a signed browser-scan passport plus the
// details the user typed in (device type, age, fault).
//
// A browser cannot read battery health, disk health or Windows 11 eligibility,
// so those are simply not sent -- the server treats a missing value as "not
// measured", never as healthy.
function num(v) {
  const m = String(v ?? "").match(/[\d.]+/);
  return m ? Number(m[0]) : null;
}

// A deep scan carries a measured trust score and real battery, Windows 11 and
// support facts; a browser scan carries none of them, and must never send them.
export async function fetchAssessment(payload, extra, doc) {
  const lc = payload.lifecycle || {};
  if (payload.trust_score != null) {
    return api.assess({
      hardware_trust: payload.trust_score,
      trust_measured: true,                  // battery and age are inside the trust score: counted once
      eol_risk: null,                        // no repair-model run on a deep scan: the support date decides
      battery_health: num(payload.battery_health),
      age_years: payload.age_years ?? null,
      fault_described: false,
      make_model: payload.make_model || null,
      manufacturer: payload.manufacturer || null,
      cpu: payload.cpu || null,
      os: payload.os || null,
      win11: payload.win11 || null,
      win11_blockers: payload.win11_blockers || null,
      win11_permanently_blocked: payload.win11_permanently_blocked ?? null,
      win11_firmware_fixable: payload.win11_firmware_fixable ?? null,
      storage: payload.storage || null,
      product_category: payload.product_category || null,
      timezone: timezone(),
      country: extra?.country || null,
    });
  }
  return api.assess({
    // A browser scan has no measured hardware score, so it starts from the
    // documented default and the adjustments explain every point from there.
    hardware_trust: 75,
    // The ML model's end-of-life probability, signed into the passport.
    eol_risk: lc.eol_risk ?? null,
    age_years: lc.device_age ?? (extra ? Number(extra.device_age) : payload.age_years) ?? null,
    fault_described: lc.fault_described ?? false,
    // The recognised fault theme(s), named on the waterfall instead of "user-described".
    fault_detail: lc.fault_themes?.length ? lc.fault_themes.join(", ") : null,
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
