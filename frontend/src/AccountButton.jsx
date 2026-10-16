import { useAuth } from "./AuthContext.jsx";

// Fixed top-right, always reachable regardless of which nav tab is active --
// same anchor point Linear/GitHub/Notion use for the account entry point, so
// it reads as "the account control" on sight rather than needing a label.
export default function AccountButton() {
  const { available, user, openAuthModal } = useAuth();
  const initial = user?.email?.[0]?.toUpperCase();
  if (!available) return null;

  return (
    <button
      className={`account-btn ${user ? "signed-in" : ""}`}
      onClick={openAuthModal}
      title={user ? user.email : "Sign in"}
      aria-label={user ? "Account menu" : "Sign in"}
    >
      {initial || (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.8" />
          <path d="M4 20c0-4.4 3.6-7 8-7s8 2.6 8 7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      )}
    </button>
  );
}
