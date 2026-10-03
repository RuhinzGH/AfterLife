// Coarse, honest device-family detection -- enough to know "phone vs laptop vs
// tablet" for defaulting the category dropdown in Scanner.jsx, not a real
// fingerprint.
export function currentDeviceCategory() {
  const ua = navigator.userAgent;
  if (/iPad/i.test(ua) || (navigator.maxTouchPoints > 2 && /Macintosh/i.test(ua))) return "tablet";
  if (/Mobi|Android|iPhone/i.test(ua)) return "mobile";
  return "desktop";
}

// Maps the coarse category to the dropdown's actual option value.
export function defaultProductCategory() {
  const cat = currentDeviceCategory();
  if (cat === "mobile") return "Mobile";
  if (cat === "tablet") return "Tablet";
  return "Laptop";
}
