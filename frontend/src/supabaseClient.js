// The Supabase client for sign-up, sign-in and the session.
//
// The publishable key is safe in browser code by design: it can only do what
// Supabase's own sign-in rules allow. The secret key never comes here; it lives
// on the server only.
//
// Loaded on demand rather than with the first page: most visitors never sign
// in, and the library is the largest single piece of code they would otherwise
// download for nothing.
const URL_ = import.meta.env.VITE_SUPABASE_URL;
const KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const accountsConfigured = Boolean(URL_ && KEY);

let clientPromise = null;

export function getSupabase() {
  if (!accountsConfigured) return Promise.resolve(null);
  clientPromise ??= import("@supabase/supabase-js").then(({ createClient }) => createClient(URL_, KEY));
  return clientPromise;
}
