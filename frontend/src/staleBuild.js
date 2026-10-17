// A tab opened before a new version was published still asks for the old
// version's page pieces (DeepScan-<old>.js), which the new deploy no longer
// has. The fix is simply to load the current version, so the page reloads
// itself once. A short guard stops a reload loop if the file is genuinely
// missing for another reason; the error message then shows as before.

const KEY = "afterlife-stale-reload";
const GUARD_MS = 30_000;

export function isStaleBuildError(err) {
  const msg = String(err?.message || err || "");
  return /dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(msg);
}

/** Reload once for a stale-build error. Returns true when a reload was started. */
export function reloadIfStale(err, { storage = window.sessionStorage, reload = () => window.location.reload(), now = Date.now() } = {}) {
  if (!isStaleBuildError(err)) return false;
  try {
    const last = storage.getItem(KEY);
    if (last !== null && now - Number(last) < GUARD_MS) return false;   // tried just now: show the error instead
    storage.setItem(KEY, String(now));
  } catch {
    return false;                               // no storage, no guard: never risk a loop
  }
  reload();
  return true;
}
