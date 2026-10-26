import { describe, expect, it } from "vitest";
import QRCode from "qrcode";
import { crop, decodeQR, resize } from "./qrDecode.js";

// A passport-sized link, drawn as a QR inside a larger "photo", the way a phone
// camera or a screenshot sees it.
const LINK = "https://afterlife.example/?verify=" + "Ab3-_x".repeat(160);

function photo({ side, scale, invert = false }) {
  const qr = QRCode.create(LINK, { errorCorrectionLevel: "M" });
  const n = qr.modules.size, margin = 4, q = (n + 2 * margin) * scale;
  const bg = invert ? 20 : 235, ink = invert ? 235 : 20;
  const px = new Uint8ClampedArray(side * side * 4);
  for (let i = 0; i < px.length; i += 4) { px[i] = px[i + 1] = px[i + 2] = bg; px[i + 3] = 255; }
  const off = Math.floor((side - q) / 2);
  for (let y = 0; y < q; y++) for (let x = 0; x < q; x++) {
    const my = Math.floor(y / scale) - margin, mx = Math.floor(x / scale) - margin;
    const dark = my >= 0 && mx >= 0 && my < n && mx < n && qr.modules.get(my, mx);
    const i = ((off + y) * side + off + x) * 4;
    const v = dark ? ink : (invert ? 20 : 255);
    px[i] = px[i + 1] = px[i + 2] = v;
  }
  return { data: px, width: side, height: side };
}

describe("decodeQR", () => {
  it("reads a passport QR that fills the image", () => {
    expect(decodeQR(photo({ side: 900, scale: 6 }))).toBe(LINK);
  }, 30_000);

  it("reads a passport QR in the middle of a large photo (the 'had to zoom in' case)", () => {
    expect(decodeQR(photo({ side: 2400, scale: 6 }))).toBe(LINK);
  }, 30_000);

  it("reads a light-on-dark QR, as shown on a dark screen", () => {
    expect(decodeQR(photo({ side: 900, scale: 6, invert: true }))).toBe(LINK);
  }, 30_000);

  it("returns null when there is no QR", () => {
    const blank = { data: new Uint8ClampedArray(200 * 200 * 4).fill(255), width: 200, height: 200 };
    expect(decodeQR(blank)).toBeNull();
  }, 30_000);
});

describe("image helpers", () => {
  const img = { data: new Uint8ClampedArray([1, 1, 1, 255, 2, 2, 2, 255, 3, 3, 3, 255, 4, 4, 4, 255]), width: 2, height: 2 };

  it("crop keeps the chosen pixels", () => {
    const c = crop(img, 1, 1, 1, 1);
    expect([c.width, c.height, c.data[0]]).toEqual([1, 1, 4]);
  });

  it("resize scales up by nearest neighbour", () => {
    const r = resize(img, 4, 4);
    expect([r.width, r.height, r.data[0], r.data[(3 * 4 + 3) * 4]]).toEqual([4, 4, 1, 4]);
  });
});
