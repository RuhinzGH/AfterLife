/**
 * Whether the opening animation should play.
 *
 * Once per browser session, not on every load. The intro is the most
 * expensive thing the page draws, and replaying it on every reload spends that
 * cost again for nothing the visitor has not already seen -- the green
 * computing case for gating it. A new session (a new tab or browser window)
 * plays it once more.
 *
 * It never plays for someone whose system asks for reduced motion.
 *
 * Storage is passed in rather than read from window, so the rule can be tested
 * without a browser. If storage is unavailable (private mode, blocked cookies)
 * the intro plays and nothing throws -- a broken store must not break the page.
 */
export const INTRO_KEY = "afterlife-intro-played";

export function shouldPlayIntro(storage, prefersReducedMotion) {
  if (prefersReducedMotion) return false;
  try {
    return storage?.getItem(INTRO_KEY) !== "1";
  } catch {
    return true;
  }
}

export function markIntroPlayed(storage) {
  try {
    storage?.setItem(INTRO_KEY, "1");
  } catch {
    /* storage blocked: the intro simply plays again next load */
  }
}
