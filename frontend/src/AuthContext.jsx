import { createContext, useContext, useEffect, useState } from "react";
import { accountsConfigured, getSupabase } from "./supabaseClient.js";

const AuthCtx = createContext(null);

// Accounts are optional: every scan works signed out. When the site has no
// Supabase settings at all, `available` is false and the sign-in button hides.
export function AuthProvider({ children }) {
  const [session, setSession] = useState(accountsConfigured ? undefined : null); // undefined = still loading
  const [authModalOpen, setAuthModalOpen] = useState(false);

  useEffect(() => {
    if (!accountsConfigured) return undefined;
    let sub = null;
    let alive = true;
    getSupabase().then((sb) => {
      if (!sb || !alive) return;
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
    authModalOpen,
    openAuthModal: () => setAuthModalOpen(true),
    closeAuthModal: () => setAuthModalOpen(false),
  };

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  return useContext(AuthCtx);
}
