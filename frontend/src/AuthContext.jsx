import { createContext, useContext, useEffect, useState } from "react";
import { accountsConfigured, getSupabase } from "./supabaseClient.js";
import { RECOVERY } from "./recovery.js";

const AuthCtx = createContext(null);

// Accounts are optional: every scan works signed out. When the site has no
// Supabase settings at all, `available` is false and the sign-in button hides.
export function AuthProvider({ children }) {
  const [session, setSession] = useState(accountsConfigured ? undefined : null); // undefined = still loading
  // Arrived from a password-reset email: open the modal on "set a new password"
  // (or on the expired-link message, with a way to ask for a new one).
  const [authModalOpen, setAuthModalOpen] = useState(Boolean(RECOVERY && accountsConfigured));
  const [recovering, setRecovering] = useState(false);
  const [recoveryError, setRecoveryError] = useState(RECOVERY?.error || null);

  useEffect(() => {
    if (!accountsConfigured) return undefined;
    let sub = null;
    let alive = true;
    getSupabase().then((sb) => {
      if (!sb || !alive) return;
      if (RECOVERY?.tokens) {
        sb.auth.setSession(RECOVERY.tokens).then(({ data, error }) => {
          if (!alive) return;
          if (error) setRecoveryError("That reset link didn't work. Ask for a new one below.");
          else { setSession(data.session); setRecovering(true); }
        });
      }
      sb.auth.getSession().then(({ data }) => alive && setSession(data.session));
      sub = sb.auth.onAuthStateChange((_event, s) => alive && setSession(s)).data.subscription;
    }).catch(() => alive && setSession(null));
    return () => { alive = false; sub?.unsubscribe(); };
  }, []);

  const call = (fn) => async (...args) => {
    const sb = await getSupabase();
    if (!sb) return { data: null, error: { message: "Accounts are not available on this site." } };
    return fn(sb, ...args);
  };

  const value = {
    available: accountsConfigured,
    session,
    user: session?.user ?? null,
    loading: session === undefined,
    signUp: call((sb, email, password) => sb.auth.signUp({ email, password })),
    signIn: call((sb, email, password) => sb.auth.signInWithPassword({ email, password })),
    signOut: call((sb) => sb.auth.signOut()),
    // Supabase always answers "sent", whether or not the email has an account,
    // so the form can't be used to find out who has one.
    requestReset: call((sb, email) => sb.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/` })),
    updatePassword: call((sb, password) => sb.auth.updateUser({ password })),
    recovering,
    recoveryError,
    finishRecovery: () => { setRecovering(false); setRecoveryError(null); },
    authModalOpen,
    openAuthModal: () => setAuthModalOpen(true),
    closeAuthModal: () => setAuthModalOpen(false),
  };

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  return useContext(AuthCtx);
}
