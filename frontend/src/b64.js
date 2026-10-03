// UTF-8-safe, URL-safe base64 — plain btoa/atob only handle Latin1 (passports
// contain Unicode like em-dashes), and standard base64's +, /, = need percent-
// encoding in a URL, which was bloating QR payloads and made the double
// decode/encode round trip fragile. base64url has neither problem: its
// alphabet (A-Z a-z 0-9 - _) is already URL-safe, so it goes straight into a
// query string with no encodeURIComponent/decodeURIComponent needed at all.

import { deflate, inflate } from "pako";

export function b64encodeUtf8(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function b64decodeUtf8(b64) {
  let s = b64.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const bin = atob(s);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

// A passport with its full ML outlook can make a plain base64 verify-link
// longer than a QR code can hold, which throws. Gzip-deflating the JSON before
// base64-encoding shrinks it dramatically (JSON is highly repetitive) without
// dropping a single field, so nothing is left unverifiable.
export function b64encodeCompressed(obj) {
  const compressed = deflate(JSON.stringify(obj));
  let bin = "";
  for (const b of compressed) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function b64decodeCompressed(b64) {
  let s = b64.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const bin = atob(s);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  // pako v3 renamed this option from the older `{ to: "string" }` to
  // `{ toText: true }` -- the old name is silently ignored (returns a raw
  // Uint8Array instead of throwing), which is exactly the kind of API-version
  // trap worth a comment so it doesn't get "fixed" back by accident later.
  return JSON.parse(inflate(bytes, { toText: true }));
}
