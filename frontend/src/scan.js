// Browser-side device scan — reads everything the browser exposes, with the
// user's explicit click as the permission moment. Deeper fields (TPM, disk
// health, battery wear) are not visible to a browser; this is the instant,
// no-download profile.

async function highEntropy() {
  const uaData = navigator.userAgentData;
  if (!uaData?.getHighEntropyValues) return {};
  try {
    return await uaData.getHighEntropyValues([
      "platform", "platformVersion", "architecture", "bitness",
      "model", "uaFullVersion", "fullVersionList",
    ]);
  } catch {
    return {};
  }
}

function gpuInfo() {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl") || c.getContext("experimental-webgl");
    if (!gl) return null;
    const dbg = gl.getExtension("WEBGL_debug_renderer_info");
    const renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    const vendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR);
    return { renderer, vendor };
  } catch {
    return null;
  }
}

function windowsFromUA(platformVersion) {
  // Chromium reports Win11 as platformVersion major >= 13.
  const major = parseInt((platformVersion || "0").split(".")[0], 10);
  if (!major) return null;
  return major >= 13 ? "11" : "10";
}

// The OS label, e.g. "Windows 11 (build 15.0.0)" or "Android 16 (build 16.0.0)".
// Only Windows needs translating: Chromium reports Windows 11 as platformVersion
// 13+, while on Android and macOS the major version IS the release number. The
// Windows rule used to run on every platform, so Android 16 read "Android 11"
// and was matched to Android 11's ended support (defect S2-D16).
export function osLabel(he, fallback) {
  if (!(he?.platform && he?.platformVersion)) return fallback || "Unknown OS";
  if (he.platform === "Windows") {
    const win = windowsFromUA(he.platformVersion);
    return `Windows${win ? " " + win : ""} (build ${he.platformVersion})`;
  }
  const major = parseInt(he.platformVersion.split(".")[0], 10);
  return `${he.platform}${major ? " " + major : ""} (build ${he.platformVersion})`;
}

export async function scanDevice() {
  const he = await highEntropy();
  const gpu = gpuInfo();
  const winMajor = he.platform === "Windows" ? windowsFromUA(he.platformVersion) : null;
  const os = osLabel(he, navigator.platform);

  return {
    // shown on the card
    os,
    os_family: he.platform || navigator.platform || "Unknown",
    architecture: he.architecture ? `${he.architecture} ${he.bitness || ""}`.trim() : null,
    model: he.model || null,
    gpu: gpu?.renderer || null,
    gpu_vendor: gpu?.vendor || null,
    cpu_cores: navigator.hardwareConcurrency || null,
    ram_gb: navigator.deviceMemory || null, // coarse, capped at 8 by Chrome
    // NOTE: the browser only exposes live battery *charge*, not health/wear, and it
    // changes constantly — so it is intentionally NOT in the passport.
    screen: `${window.screen.width}×${window.screen.height}`,
    color_depth: window.screen.colorDepth,
    pixel_ratio: window.devicePixelRatio,
    languages: (navigator.languages || []).slice(0, 3).join(", "),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    touch: navigator.maxTouchPoints > 0,
    // for the backend passport builder (browser can't see these)
    win_major: winMajor,
    scanned_at: new Date().toISOString(),
    source: "browser-scan",
  };
}

// Fields to reveal one-by-one during the scan animation.
export const SCAN_STEPS = [
  { key: "os", label: "Operating system" },
  { key: "gpu", label: "Graphics processor" },
  { key: "cpu_cores", label: "CPU cores", fmt: (v) => `${v} logical` },
  { key: "ram_gb", label: "Memory", fmt: (v) => `${v} GB+` },
  { key: "architecture", label: "Architecture" },
  { key: "screen", label: "Display" },
  { key: "timezone", label: "Timezone" },
];
