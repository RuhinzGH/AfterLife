import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthContext.jsx";

export default function AuthModal({ onAuthed, onNavigate }) {
  const { user, authModalOpen, closeAuthModal } = useAuth();

  useEffect(() => {
    if (!authModalOpen) return;
    const onKey = (e) => e.key === "Escape" && closeAuthModal();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [authModalOpen, closeAuthModal]);

  if (!authModalOpen) return null;

  return (
    <div className="auth-backdrop" onMouseDown={(e) => e.target === e.currentTarget && closeAuthModal()}>
      <div className="auth-card">
        <button className="auth-close" onClick={closeAuthModal} aria-label="Close">✕</button>
        {user ? <AccountView onNavigate={onNavigate} /> : <SignInUp onAuthed={onAuthed} />}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- password strength */
// Minimum bar for "standard" strength: 8+ characters, at least one number, at
// least one letter. Shown live, only in signup mode -- sign-in just needs
// whatever password already exists, right or wrong.
function passwordChecks(pw) {
  return {
    length: pw.length >= 8,
    number: /\d/.test(pw),
    letter: /[a-zA-Z]/.test(pw),
  };
}
function passwordValid(pw) {
  const c = passwordChecks(pw);
  return c.length && c.number && c.letter;
}

function PasswordChecklist({ password }) {
  const c = passwordChecks(password);
  const items = [
    [c.length, "8+ characters"],
    [c.number, "at least one number"],
    [c.letter, "at least one letter"],
  ];
  return (
    <div className="pw-checklist">
      {items.map(([ok, label]) => (
        <span key={label} className={`pw-check ${ok ? "ok" : ""}`}>
          {ok ? "✓" : "○"} {label}
        </span>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- signed out */
// Sign-in is deliberately just email + password -- no extra fields. Confirm
// password only appears on sign-up, since that's the one place a typo is
// unrecoverable (a mistyped sign-in just fails and you retype it).
function SignInUp({ onAuthed }) {
  const { signIn, signUp, closeAuthModal } = useAuth();
  const [mode, setMode] = useState("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [err, setErr] = useState(null);
  const [notice, setNotice] = useState(null);
  const slowTimer = useRef(null);

  function switchMode(m) {
    setMode(m); setErr(null); setNotice(null);
  }

  // Supabase's own signup endpoint can genuinely take 6-20+ seconds under load
  // (it waits on the confirmation-email send before responding) -- without this,
  // that reads as a hung/broken button instead of a slow-but-working one.
  function startBusy() {
    setBusy(true); setSlow(false);
    slowTimer.current = setTimeout(() => setSlow(true), 4000);
  }
  function stopBusy() {
    setBusy(false); setSlow(false);
    clearTimeout(slowTimer.current);
  }

  async function submit(e) {
    e.preventDefault();
    setErr(null); setNotice(null);

    if (mode === "signup") {
      if (!passwordValid(password)) { setErr("Password doesn't meet the requirements below."); return; }
      if (password !== confirm) { setErr("Passwords don't match."); return; }
    }

    startBusy();
    if (mode === "signin") {
      const { error } = await signIn(email, password);
      stopBusy();
      if (error) { setErr(error.message); return; }
      closeAuthModal();
      return;
    }

    // Supabase never returns a hard error for "this email already has an
    // account" when confirmation is on -- for enumeration-protection reasons
    // it silently returns a user object with an empty identities array
    // instead. That's the actual signal to check.
    const { data, error } = await signUp(email, password);
    stopBusy();
    const alreadyRegistered =
      (data?.user?.identities && data.user.identities.length === 0) ||
      /already registered|already exists/i.test(error?.message || "");
    if (alreadyRegistered) {
      setErr("An account with this email already exists.");
      return;
    }
    if (/rate limit/i.test(error?.message || "")) {
      setErr("Too many signup attempts right now — please wait a few minutes and try again.");
      return;
    }
    if (error) { setErr(error.message); return; }

    if (data?.session) {
      // Email confirmation is off (or not required) -- already signed in.
      closeAuthModal();
      onAuthed?.();
    } else {
      setNotice("Account created — check your email to confirm, then sign in.");
    }
  }

  return (
    <>
      <div className="auth-icon-badge">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
          <rect x="4" y="10" width="16" height="10" rx="2.5" stroke="currentColor" strokeWidth="1.7" />
          <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
          <circle cx="12" cy="15" r="1.6" fill="currentColor" />
        </svg>
      </div>
      <div className="auth-eyebrow">Account</div>
      <h2 className="auth-title">{mode === "signin" ? "Sign in" : "Create an account"}</h2>
      <p className="auth-sub">
        {mode === "signin"
          ? "Every device you've scanned, kept — so your next one has something to be compared against."
          : "Scanning works without an account too. Sign up and we'll keep your results, so a future device can be measured against its predecessor."}
      </p>

      <form className="form" onSubmit={submit}>
        <div className="field">
          <label>Email</label>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label>Password</label>
          <input type="password" required minLength={mode === "signup" ? 8 : 6} value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {mode === "signup" && (
          <>
            <PasswordChecklist password={password} />
            <div className="field">
              <label>Confirm password</label>
              <input type="password" required minLength={8} value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </div>
            {/* Live, like the checklist above: shown once something is typed in Confirm. */}
            {confirm && (
              <span className={`pw-check pw-match ${confirm === password ? "ok" : "bad"}`} role="status">
                {confirm === password ? "✓ Passwords match" : "✕ Passwords do not match"}
              </span>
            )}
          </>
        )}
        {err && (
          <div className="badge bad">
            ⚠ {err}
            {/already exists/i.test(err) && (
              <> — <a href="#" onClick={(e) => { e.preventDefault(); switchMode("signin"); }}>sign in instead</a></>
            )}
          </div>
        )}
        {notice && <div className="badge" style={{ borderColor: "var(--green)", color: "var(--green)" }}>{notice}</div>}
        <button className="cta" type="submit" disabled={busy}>
          {busy ? "Working…" : mode === "signin" ? "Sign in" : "Sign up"}
        </button>
        {slow && <p className="note" style={{ marginTop: "0.4rem" }}>Still working — this can take a few seconds.</p>}
      </form>
      <p className="note" style={{ marginTop: "1rem" }}>
        {mode === "signin" ? "No account yet? " : "Already have an account? "}
        <a href="#" onClick={(e) => { e.preventDefault(); switchMode(mode === "signin" ? "signup" : "signin"); }}>
          {mode === "signin" ? "Sign up" : "Sign in"}
        </a>
      </p>
    </>
  );
}

/* ---------------------------------------------------------------- signed in */
// Signing out is not a destructive action -- one click, no re-authentication,
// same as every other account menu on the web.
function AccountView({ onNavigate }) {
  const { user, signOut, closeAuthModal } = useAuth();
  const initial = user.email[0].toUpperCase();

  async function handleSignOut() {
    await signOut();
    closeAuthModal();
  }

  return (
    <>
      <div className="account-head">
        <div className="account-avatar-lg">{initial}</div>
        <div>
          <div className="auth-eyebrow" style={{ marginBottom: "0.2rem" }}>Signed in</div>
          <div className="account-email">{user.email}</div>
        </div>
      </div>
      <p className="auth-sub" style={{ marginTop: "1rem" }}>
        Every device you scan from here on is added to your history — see it anytime under My Scans.
      </p>
      <button className="v2-btn" style={{ marginTop: "0.8rem" }}
              onClick={() => { closeAuthModal(); onNavigate?.("scans"); }}>
        Open My Scans
      </button>
      <div className="auth-divider" />
      <button className="account-signout" onClick={handleSignOut}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M15 4h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M10 8l-4 4 4 4M6 12h11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Sign out
      </button>
    </>
  );
}
