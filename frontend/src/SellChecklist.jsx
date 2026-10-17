import { useState } from "react";
import { ChevronDown, ChevronUp } from "./icons.jsx";

// Sell checklist (S2-07). AfterLife never erases anything: it walks the owner
// through the operating system's own reset. On a deep scan it then shows the
// collector's clean-state check (afterlife/wipe.py), which says whether the
// machine *looks* factory-fresh. That is not proof that deleted data cannot be
// recovered, and the card says so.

const STEPS = [
  "Back up what you want to keep: photos, documents, saved passwords.",
  "Sign out of your accounts: Microsoft or Apple ID, browsers, cloud storage.",
  "Turn off Find My Device (or Find My on Apple devices) so the buyer can set it up.",
  "Remove any SIM or memory card.",
  "Reset it. On Windows: Settings → System → Recovery → Reset this PC → Remove everything, and choose to clean the drive.",
  "When it starts at a blank setup screen, it is ready. On Windows, run the deep scan once more to check it.",
];

const STATUS = {
  clean: ["ok", "✓", "Looks factory-fresh"],
  not_clean: ["warn", "!", "Not clean yet"],
  unknown: ["unknown", "?", "Couldn't check this"],
};

export default function SellChecklist({ wipe }) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button className="trigger-card" onClick={() => setOpen(true)}>
        <span className="trigger-icon" aria-hidden="true">🧹</span>
        <span className="trigger-text">
          <span className="trigger-title">Getting ready to sell or give it away?</span>
          <span className="trigger-sub">{wipe?.status === "clean" ? "Reset checked ✓" : "Reset it properly, then check"}</span>
        </span>
        <span className="trigger-chevron"><ChevronDown /></span>
      </button>
    );
  }

  const [cls, icon, title] = (wipe && STATUS[wipe.status]) || [];
  return (
    <div className="dash-card">
      <div className="card-head-row">
        <div className="k-label" style={{ marginBottom: 0 }}>Before you sell: clear your data</div>
        <button className="collapse-x" onClick={() => setOpen(false)} aria-label="Collapse"><ChevronUp /></button>
      </div>

      {title && (
        <div className={`wipe-status ${cls}`}>
          <div className="wipe-status-head">
            <span className="wipe-status-icon">{icon}</span>
            <span className="wipe-status-title">{title}</span>
            {wipe.verified_at && <span className="pill cyan">checked {wipe.verified_at}</span>}
          </div>
          {wipe.checks?.length > 0 && (
            <div className="wipe-checks">
              {wipe.checks.map((c) => (
                <div className={`wipe-check ${c.ok === true ? "pass" : c.ok === false ? "fail" : "skip"}`} key={c.label}>
                  <span className="wipe-check-mark">{c.ok === true ? "✓" : c.ok === false ? "✗" : "–"}</span>
                  <span className="wipe-check-label">{c.label}</span>
                  <span className="wipe-check-detail">{c.detail}</span>
                </div>
              ))}
            </div>
          )}
          {wipe.note && <p className="note" style={{ marginTop: "0.6rem" }}>{wipe.note}</p>}
        </div>
      )}

      <div className="sugg-list" style={{ marginTop: "0.6rem" }}>
        {STEPS.map((s, i) => (
          <div className="sugg" key={i}><span className="sugg-n">{i + 1}</span><span>{s}</span></div>
        ))}
      </div>

      <div className="disclaimer" style={{ marginTop: "1rem" }}>
        <span>⚠</span>
        <span>
          <b>A clean-state check, not forensic erasure.</b> The deep scan can confirm there are no
          leftover accounts, files or saved networks and that the system was reset recently. It
          cannot prove that deleted data is unrecoverable from the disk.
        </span>
      </div>
    </div>
  );
}
