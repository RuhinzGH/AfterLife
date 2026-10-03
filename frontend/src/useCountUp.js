import { useEffect, useRef, useState } from "react";

const REDUCED = () =>
  typeof window !== "undefined" &&
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Fast out of the gate, long settle. A linear count reads like a stopwatch;
// this reads like a needle finding its resting place, which is what the number
// actually is.
const ease = (t) => 1 - Math.pow(1 - t, 3);

/**
 * Counts from 0 up to `target` over `ms`, on rAF.
 *
 * Returns the target immediately, with no animation at all, when the visitor
 * has asked for reduced motion -- a number ticking upward is exactly the kind
 * of movement that setting exists to stop. Also returns it immediately for a
 * null or non-finite target, so a failed scan never shows a hopeful 0 climbing
 * toward nothing.
 */
export function useCountUp(target, ms = 900) {
  const valid = Number.isFinite(target);
  const [value, setValue] = useState(valid && !REDUCED() ? 0 : target);
  const frame = useRef(0);

  useEffect(() => {
    if (!valid || REDUCED()) {
      setValue(target);
      return undefined;
    }
    const from = 0;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / ms);
      setValue(from + (target - from) * ease(t));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);

    // requestAnimationFrame does not run in a hidden or backgrounded tab. Without
    // this, opening the app in a background tab and coming back to it later shows
    // a score frozen at 0 -- a wrong number, presented with total confidence,
    // which is far worse than no animation. The backstop lands on the real value
    // whether or not a single frame ever ran.
    const settle = setTimeout(() => setValue(target), ms + 60);

    return () => {
      cancelAnimationFrame(frame.current);
      clearTimeout(settle);
    };
  }, [target, ms, valid]);

  return value;
}
