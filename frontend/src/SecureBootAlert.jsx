// The Secure Boot certificate cliff, explained to someone who has never heard the
// phrase "Secure Boot".
//
// The underlying facts are unavoidably technical -- three certificate authorities
// with different expiry dates. But the thing a person needs to take away is
// simple: your PC checks some digital ID cards when it turns on, the old ones
// expired, and if yours didn't get the new ones you're missing part of your
// security updates. It's usually a free fix.
//
// Framing matters as much as accuracy: presented badly this reads as "your PC is
// finished", which is the exact reflex Afterlife exists to argue against.

const TONE = {
  ok: { cls: "fix", label: "all good" },
  action_needed: { cls: "rep", label: "worth doing" },
  at_risk: { cls: "eol", label: "needs attention" },
  unknown: { cls: "unk", label: "not checked" },
  not_applicable: { cls: "unk", label: "n/a" },
};

// The certificate names are meaningless to a normal reader, so each gets a plain
// description of what it actually guards.
const PLAIN_DEADLINE = {
  "KEK CA 2011 (key exchange)": "The master key that lets Windows update the list below",
  "UEFI CA 2011 (third-party boot)": "Covers non-Microsoft startup software, like Linux boot menus",
  "Windows Production PCA 2011 (bootloader)": "Signs the Windows startup file itself",
};

export default function SecureBootAlert({ secureBoot }) {
  if (!secureBoot || !secureBoot.status) return null;
  // A machine that's fine doesn't need a card telling it so, and legacy BIOS has
  // no certificates to expire. Both stay quiet rather than adding noise.
  if (secureBoot.status === "ok" || secureBoot.status === "not_applicable") return null;

  const tone = TONE[secureBoot.status] || TONE.unknown;
  const deadlines = secureBoot.deadlines || [];

  return (
    <div className={`card pad sb sb-${secureBoot.status}`}>
      <div className="sh-head">
        <div>
          <h3 className="sh-title">Your PC's startup security</h3>
          <span className="note">Something expired in 2026 that most people never hear about</span>
        </div>
        <span className={`life-tag ${tone.cls}`}>{tone.label}</span>
      </div>

      {/* Explain the concept before delivering the verdict about it. */}
      <p className="sb-explain">
        When your PC turns on, it checks a set of digital ID cards to make sure nothing has
        tampered with Windows before it loads. Microsoft's original ID cards expired during
        2026 and new ones replaced them. They normally arrive through Windows Update on their
        own.
      </p>

      <p className="sb-headline">{secureBoot.headline}</p>
      <p className="sb-detail">{secureBoot.detail}</p>

      {deadlines.length > 0 && (
        <div className="sb-dates">
          {deadlines.map((d) => (
            <div key={d.label} className={`sb-date ${d.passed ? "past" : ""}`}>
              <span className="sb-date-label">
                {PLAIN_DEADLINE[d.label] || d.label}
              </span>
              <span className="sb-date-when">
                {new Date(d.date).toLocaleDateString(undefined, { month: "short", year: "numeric" })}
              </span>
              <span className="sb-date-state">
                {d.passed ? "expired" : `${d.days_remaining} days`}
              </span>
            </div>
          ))}
        </div>
      )}

      {secureBoot.fixable && secureBoot.fix && (
        <div className="sb-fix">
          <b>This is fixable, and it is usually free</b>
          <ol>
            {secureBoot.fix.map((f, i) => <li key={i}>{f}</li>)}
          </ol>
        </div>
      )}
    </div>
  );
}
