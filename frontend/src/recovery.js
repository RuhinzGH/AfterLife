// Password reset: reading the link Supabase emails.
//
// The reset email links back to the site with the sign-in tokens in the URL
// fragment: "#access_token=...&refresh_token=...&type=recovery" (or, when the
// link has expired, "#error=access_denied&error_code=otp_expired&..."). This
// site also routes on the fragment ("#/home"), so the tokens are read and
// removed once, at start-up, before the router ever sees them.

export function parseRecoveryHash(hash) {
  const h = String(hash || "").replace(/^#\/?/, "");
  if (!h.includes("=")) return null;
  const q = new URLSearchParams(h);
  if (q.get("type") === "recovery" && q.get("access_token") && q.get("refresh_token")) {
    return { tokens: { access_token: q.get("access_token"), refresh_token: q.get("refresh_token") } };
  }
  if (q.get("error_code") || (q.get("error") && q.get("error_description"))) {
    const expired = q.get("error_code") === "otp_expired";
    return {
      error: expired
        ? "That reset link has expired or was already used. Ask for a new one below."
        : (q.get("error_description") || "That link didn't work.").replace(/\+/g, " "),
    };
  }
  return null;
}

// Read once, at import time, and clean the address bar.
export const RECOVERY = (() => {
  if (typeof window === "undefined") return null;
  const found = parseRecoveryHash(window.location.hash);
  if (found) window.history.replaceState({}, "", `${window.location.pathname}#/home`);
  return found;
})();
