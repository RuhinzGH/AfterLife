// Progressive disclosure, used everywhere a card has more to say than a first-time
// reader needs.
//
// The rule this enforces: nothing is ever deleted to make a page calmer. Three
// audiences read the same card -- someone checking their laptop, a technical
// reviewer, and eventually an auditor -- and they want the same facts at three
// different depths. Hiding the deeper layers behind a control serves all three;
// cutting them serves only the first, and cutting them is what most products do.
//
// Built on <details>/<summary> rather than useState, deliberately:
//   * it is keyboard-operable and screen-reader-announced with no work from us,
//   * Ctrl+F finds text inside a closed one in Chrome and Edge, which matters a
//     lot for a page whose whole claim is "check my sources",
//   * and it survives a re-render without a state hook per card.

import { useEffect, useState } from "react";
import { useTechnical } from "./prefs.js";

export default function Disclose({ label = "See details", children, tone = "", open = false }) {
  // Default open when this card is asked to, OR when the reader has turned on
  // technical mode. Internal state (kept in sync via onToggle) so a reader can
  // still collapse or open any individual one without React re-asserting the
  // preference on the next render -- the preference sets the default, not a lock.
  const tech = useTechnical();
  const [isOpen, setIsOpen] = useState(open || tech);
  useEffect(() => { setIsOpen(open || tech); }, [tech, open]);
  return (
    <details className={`disclose ${tone}`} open={isOpen}
             onToggle={(e) => setIsOpen(e.currentTarget.open)}>
      <summary className="disclose-summary">
        <span className="disclose-chevron" aria-hidden="true">▸</span>
        {label}
      </summary>
      <div className="disclose-body">{children}</div>
    </details>
  );
}

// The conclusion-first pattern from the brief, as one component so every card
// states its result the same way:
//
//     verdict  ->  one plain sentence  ->  everything else, folded away
//
// `verdict` is the thing a casual reader should be able to leave with. `children`
// is the technical layer, and is never rendered inline.
export function Conclusion({ tone = "good", icon, verdict, plain, label, children }) {
  return (
    <div className={`conclusion ${tone}`}>
      <div className="conclusion-head">
        {icon && <span className="conclusion-icon" aria-hidden="true">{icon}</span>}
        <b className="conclusion-verdict">{verdict}</b>
      </div>
      {plain && <p className="conclusion-plain">{plain}</p>}
      {children && <Disclose label={label || "Why?"}>{children}</Disclose>}
    </div>
  );
}
