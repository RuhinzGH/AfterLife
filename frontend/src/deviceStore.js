// Small per-browser store for two things the backend genuinely cannot know.
//
// 1. WHICH DEVICE YOU ARE ON. A scan report reads identically no matter what you
//    open it on, so "Scan again" was offered on every card in the history --
//    including the laptop you sold last year, from your phone. The only way to
//    know is a marker left on the device at scan time and checked later. Disclosed
//    limitation, not a hidden one: clearing site data or using a private window
//    makes this browser look like a device it has never seen, and the card falls
//    back to "view report" rather than pretending.
//
// 2. WHAT YOU CALL IT. "HP Victus" is what the hardware reports; "mum's laptop"
//    is what makes a grid of six cards readable. Kept locally rather than in the
//    scans table because it is a display preference, and adding a column to a
//    signed-record store for one is not worth the migration.

const SEEN_KEY = "afterlife.devices.seen";
const NAME_KEY = "afterlife.devices.names";
// 3. WHICH ONE IS YOUR MAIN DAILY DRIVER. Distinct from "this device": that is
//    auto-detected (the machine you're browsing from right now), this is a
//    deliberate choice you make and can change -- you might browse your scans
//    from a work laptop while your phone is the one you've marked Primary. Local,
//    single-valued: one device is primary at a time.
const PRIMARY_KEY = "afterlife.devices.primary";

function read(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : {};
  } catch {
    // Private mode, disabled storage, or corrupted JSON. All three mean the same
    // thing here -- no local knowledge -- and none of them should take down a page
    // whose actual content came from the server.
    return {};
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch { /* nothing here is important enough to surface a failure for */ }
}

/** Record that a scan of this device_id happened in this browser, just now. */
export function markScanned(deviceId) {
  if (!deviceId) return;
  write(SEEN_KEY, { ...read(SEEN_KEY), [deviceId]: new Date().toISOString() });
}

/** Was this device scanned from this browser before? */
export function isThisDevice(deviceId) {
  return Boolean(deviceId && read(SEEN_KEY)[deviceId]);
}

/** The device_id the user has marked as their primary/daily driver, or null. */
export function getPrimary() {
  try { return localStorage.getItem(PRIMARY_KEY) || null; } catch { return null; }
}

/** Set (or, with a falsy id, clear) the primary device. User-chosen, not detected. */
export function setPrimary(deviceId) {
  try {
    if (deviceId) localStorage.setItem(PRIMARY_KEY, deviceId);
    else localStorage.removeItem(PRIMARY_KEY);
  } catch { /* storage disabled -- preference simply doesn't persist */ }
}

export function isPrimary(deviceId) {
  return Boolean(deviceId && getPrimary() === deviceId);
}

export function getNickname(deviceId) {
  return read(NAME_KEY)[deviceId] || null;
}

export function setNickname(deviceId, name) {
  if (!deviceId) return;
  const names = read(NAME_KEY);
  const trimmed = (name || "").trim();
  if (trimmed) names[deviceId] = trimmed;
  else delete names[deviceId];   // clearing the box restores the detected name
  write(NAME_KEY, names);
}

/** "2 days ago" -- the form people actually parse at a glance. */
export function relativeTime(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
  const days = Math.round(hrs / 24);
  if (days < 31) return `${days} day${days === 1 ? "" : "s"} ago`;
  const months = Math.round(days / 30.44);
  if (months < 12) return `${months} month${months === 1 ? "" : "s"} ago`;
  const years = (days / 365.25).toFixed(1);
  return `${years} years ago`;
}
