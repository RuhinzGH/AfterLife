import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import QRCode from "qrcode";
import jsQR from "jsqr";

/**
 * The passport QR has to be readable by the app's own verifier, which decodes
 * with jsQR. Testing found that jsQR misreads some level-L codes in exactly the
 * size range a real passport link occupies (about 1,000 characters), so the QR
 * is generated at level M. This test draws codes the way the app does and
 * decodes them the way the verifier does.
 */

function drawAndDecode(text, level) {
  const qr = QRCode.create(text, { errorCorrectionLevel: level });
  const n = qr.modules.size, scale = 6, margin = 4, W = (n + 2 * margin) * scale;
  const px = new Uint8ClampedArray(W * W * 4).fill(255);
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    if (!qr.modules.get(y, x)) continue;
    for (let dy = 0; dy < scale; dy++) for (let dx = 0; dx < scale; dx++) {
      const i = (((y + margin) * scale + dy) * W + (x + margin) * scale + dx) * 4;
      px[i] = px[i + 1] = px[i + 2] = 14;
    }
  }
  return jsQR(px, W, W)?.data;
}

function link(length, seed) {
  const abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
  let s = "https://afterlife.example/?verify=", r = seed;
  while (s.length < length) { r = (r * 1103515245 + 12345) % 2147483648; s += abc[r % 64]; }
  return s;
}

describe("passport QR codes", () => {
  it("are generated at error-correction level M", () => {
    const src = readFileSync(new URL("./Scanner.jsx", import.meta.url), "utf8");
    expect(src).toContain('errorCorrectionLevel: "M"');
    expect(src).not.toContain('errorCorrectionLevel: "L"');
  });

  // Decoding is CPU-heavy, so this test gets a longer limit than Vitest's 5 s
  // default: it must not fail just because other test files run alongside it.
  it("decode exactly across the sizes real passports produce", () => {
    for (let len = 600; len <= 1400; len += 40) {
      const text = link(len, len);
      expect(drawAndDecode(text, "M")).toBe(text);
    }
  }, 30_000);
});
