// Which deep-scan command this visitor should be given, and whether one exists.
//
// The deep scan is a script the visitor runs themselves, so the instruction has
// to match the machine they are sitting at. Getting this wrong is not cosmetic:
// pasting a PowerShell one-liner into a Mac terminal fails in a way that reads
// as "this product is broken", not "wrong command".
//
// Phones and tablets get told the truth instead of a command. There is no way to
// run a shell script on stock iOS or Android, so a deep scan is genuinely
// impossible there without shipping an app -- and the browser-based instant scan
// already reads everything a phone will expose. Saying that plainly is better
// than offering something that cannot work.

export const PLATFORM = {
  windows: "windows",
  macos: "macos",
  linux: "linux",
  mobile: "mobile",
  unknown: "unknown",
};

export function detectPlatform() {
  // userAgentData is the modern, non-deprecated source and is not spoofed by
  // the compatibility strings still baked into every userAgent. Chromium only,
  // hence the fallback below.
  const ua = navigator.userAgent || "";
  const hinted = navigator.userAgentData?.platform || "";
  const p = (hinted || ua).toLowerCase();

  // Mobile first: an iPad reports a Mac-like userAgent, so checking for macOS
  // before touch support would file every modern iPad as a Mac.
  const touch = navigator.maxTouchPoints > 1;
  if (/android|iphone|ipod/.test(p)) return PLATFORM.mobile;
  if (/ipad/.test(p) || (/mac/.test(p) && touch)) return PLATFORM.mobile;

  if (/win/.test(p)) return PLATFORM.windows;
  if (/mac|darwin/.test(p)) return PLATFORM.macos;
  if (/linux|x11|cros|ubuntu|fedora|debian/.test(p)) return PLATFORM.linux;
  return PLATFORM.unknown;
}

// One entry per platform: what to call it, whether a deep scan is possible, and
// the exact line to run. Both scripts are fetched from the backend rather than
// referenced by path, because the visitor's machine has no copy of this repo.
export function deepScanCommand(platform, apiOrigin, token) {
  switch (platform) {
    case PLATFORM.windows:
      return {
        label: "Windows",
        shell: "PowerShell",
        supported: true,
        command:
          `powershell -NoProfile -Command "& ([scriptblock]::Create((irm ${apiOrigin}/api/collector.ps1))) ` +
          `-PostUrl ${apiOrigin}/api/deep-scan -Token ${token}"`,
        note: "Paste this into PowerShell and press Enter.",
      };
    case PLATFORM.macos:
      return {
        label: "macOS",
        shell: "Terminal",
        supported: true,
        command:
          `curl -fsSL ${apiOrigin}/api/collector.sh | sh -s -- ` +
          `--post ${apiOrigin}/api/deep-scan --token ${token}`,
        note: "Paste this into Terminal and press Return. No password needed.",
      };
    case PLATFORM.linux:
      return {
        label: "Linux",
        shell: "your terminal",
        supported: true,
        command:
          `curl -fsSL ${apiOrigin}/api/collector.sh | sh -s -- ` +
          `--post ${apiOrigin}/api/deep-scan --token ${token}`,
        note: "Paste this into a terminal. It runs as you, not as root.",
      };
    case PLATFORM.mobile:
      return {
        label: "Phone or tablet",
        supported: false,
        note:
          "A deep scan needs to run a small script on the device, and neither iOS nor " +
          "Android allows that without installing an app. The instant scan already reads " +
          "everything your phone's browser will hand over, so that is the honest ceiling here.",
      };
    default:
      return {
        label: "this device",
        supported: false,
        note:
          "We could not tell what kind of machine this is, so we are not going to guess at a " +
          "command for it. Pick the one that matches below, or use the instant scan.",
      };
  }
}

// Every command, for the "I'm on something else" case -- someone reading this on
// one machine and scanning another is a normal thing to want.
export function allCommands(apiOrigin, token) {
  return [PLATFORM.windows, PLATFORM.macos, PLATFORM.linux]
    .map((p) => deepScanCommand(p, apiOrigin, token));
}
