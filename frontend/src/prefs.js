import { useEffect, useState } from "react";

// A persistent, profile-level reading preference. The default everywhere is
// plain language with the working folded away; a technical reader can flip this
// once and have every disclosure ("show the math", "method and limitations",
// "how this score was calculated") default to open -- instead of clicking a
// dozen triangles every session. It is ONE preference over the same components,
// not a second parallel UI: plain and technical are two states of one page.
const KEY = "afterlife-technical";
const EVT = "afterlife-technical-change";

export function getTechnical() {
  try { return localStorage.getItem(KEY) === "1"; } catch { return false; }
}

export function setTechnical(on) {
  try { localStorage.setItem(KEY, on ? "1" : "0"); } catch { /* private mode */ }
  // Same-tab listeners don't get the native `storage` event, so broadcast our own.
  window.dispatchEvent(new CustomEvent(EVT, { detail: !!on }));
}

// Subscribe a component to the preference. Re-renders when it flips, from this
// tab (custom event) or another (storage event).
export function useTechnical() {
  const [on, setOn] = useState(getTechnical);
  useEffect(() => {
    const h = () => setOn(getTechnical());
    window.addEventListener(EVT, h);
    window.addEventListener("storage", h);
    return () => {
      window.removeEventListener(EVT, h);
      window.removeEventListener("storage", h);
    };
  }, []);
  return on;
}
