import { describe, it, expect } from "vitest";
import {
  b64decodeCompressed, b64decodeUtf8, b64encodeCompressed, b64encodeUtf8,
} from "./b64.js";

/**
 * The passport encoding behind every QR code and verify link.
 *
 * This is the most consequential pure function in the frontend and it had no
 * test. A passport is signed over canonical JSON, so the encoding must return
 * BYTE-IDENTICAL text — not merely equivalent JSON. A round trip that reorders
 * a key, drops a trailing space, or normalises a Unicode character produces a
 * document that looks right, reads right, and fails verification, with the
 * blame landing on the signature rather than on the transport.
 *
 * Three specific hazards are pinned:
 *   btoa is Latin1-only, and passports carry em-dashes and degree signs;
 *   base64url's alphabet must survive a query string with no escaping;
 *   pako v3 renamed { to: "string" } to { toText: true }, and the OLD name is
 *   silently ignored rather than throwing — it returns a raw Uint8Array, so
 *   JSON.parse fails somewhere far from the cause.
 */

const PASSPORT = {
  payload: {
    device_id: "AFL-VMLJDHVZIG",
    make_model: "Dell Latitude 5490 — Core i5",
    os: "Microsoft Windows 10 Pro",
    grade: "C - serviceable",
    battery_health: "71%",
    temperature_note: "48°C under load",
    win11_blockers: ["cpu_generation", "tpm"],
    sub_scores: [{ name: "Windows 11 ready", points: 4, max_points: 30 }],
    est_safe_years: "3–4 years",
  },
  signature: "kAx9_Qm-7ZrT4w",
  issuer_pubkey: "IfGATgEm_IluUMuw",
  issuer: "did:key:afterlife:IfGATgEm_IluUMuw",
  validFrom: "2026-09-11T08:00:00+00:00",
};

describe("b64encodeUtf8 / b64decodeUtf8", () => {
  it("round-trips plain ASCII", () => {
    expect(b64decodeUtf8(b64encodeUtf8("hello"))).toBe("hello");
  });

  it("round-trips the Unicode that actually appears in passports", () => {
    // btoa alone throws InvalidCharacterError on every one of these.
    const s = "Latitude 5490 — 48°C — 3–4 years · ±2% · “quoted”";
    expect(b64decodeUtf8(b64encodeUtf8(s))).toBe(s);
  });

  it("produces only URL-safe characters", () => {
    // The whole reason for base64url: this goes straight into ?verify= with no
    // encodeURIComponent, so + / = would each need escaping and bloat the QR.
    const enc = b64encodeUtf8("ÿÿÿ??>>>~~~" + JSON.stringify(PASSPORT));
    expect(enc).toMatch(/^[A-Za-z0-9_-]*$/);
  });

  it("survives a query-string round trip untouched", () => {
    const enc = b64encodeUtf8(JSON.stringify(PASSPORT));
    const url = new URL(`https://example.test/?verify=${enc}`);
    expect(url.searchParams.get("verify")).toBe(enc);
  });

  it("handles an empty string", () => {
    expect(b64decodeUtf8(b64encodeUtf8(""))).toBe("");
  });

  it("strips padding but still decodes at every length", () => {
    // Padding is dropped on encode, so the decoder has to restore it. Lengths
    // 1..8 cover all three residues of the base64 block.
    for (let n = 1; n <= 8; n++) {
      const s = "x".repeat(n);
      expect(b64encodeUtf8(s)).not.toContain("=");
      expect(b64decodeUtf8(b64encodeUtf8(s))).toBe(s);
    }
  });
});

describe("b64encodeCompressed / b64decodeCompressed", () => {
  it("round-trips a realistic large passport exactly", () => {
    const out = b64decodeCompressed(b64encodeCompressed(PASSPORT));
    expect(out).toEqual(PASSPORT);
  });

  it("preserves the signed envelope fields", () => {
    // issuer and validFrom are inside the signed bytes. An earlier bug dropped
    // them from the QR payload and every legitimately-signed passport came back
    // "invalid", with the signature blamed for a transport fault.
    const out = b64decodeCompressed(b64encodeCompressed(PASSPORT));
    expect(out.issuer).toBe(PASSPORT.issuer);
    expect(out.validFrom).toBe(PASSPORT.validFrom);
    expect(out.issuer_pubkey).toBe(PASSPORT.issuer_pubkey);
  });

  it("preserves Unicode through the deflate path too", () => {
    const out = b64decodeCompressed(b64encodeCompressed(PASSPORT));
    expect(out.payload.make_model).toBe("Dell Latitude 5490 — Core i5");
    expect(out.payload.temperature_note).toBe("48°C under load");
    expect(out.payload.est_safe_years).toBe("3–4 years");
  });

  it("keeps number types rather than stringifying them", () => {
    // JavaScript has no distinct float type, and the signer already collapses
    // whole-number floats to ints so a value round-trips identically. Types
    // changing here would break that agreement from the other end.
    const out = b64decodeCompressed(b64encodeCompressed(PASSPORT));
    expect(out.payload.sub_scores[0].points).toBe(4);
    expect(typeof out.payload.sub_scores[0].points).toBe("number");
  });

  it("preserves array order", () => {
    const out = b64decodeCompressed(b64encodeCompressed(PASSPORT));
    expect(out.payload.win11_blockers).toEqual(["cpu_generation", "tpm"]);
  });

  it("actually compresses — which is the entire reason it exists", () => {
    // A large passport's plain base64 link can exceed a QR's data capacity
    // and throw, which used to break the whole scan flow silently.
    const plain = b64encodeUtf8(JSON.stringify(PASSPORT));
    const packed = b64encodeCompressed(PASSPORT);
    expect(packed.length).toBeLessThan(plain.length);
  });

  it("is URL-safe like the uncompressed form", () => {
    expect(b64encodeCompressed(PASSPORT)).toMatch(/^[A-Za-z0-9_-]*$/);
  });

  it("handles an empty object and an empty array", () => {
    expect(b64decodeCompressed(b64encodeCompressed({}))).toEqual({});
    expect(b64decodeCompressed(b64encodeCompressed({ a: [] }))).toEqual({ a: [] });
  });

  it("round-trips a large passport without truncating", () => {
    const big = { ...PASSPORT, payload: { ...PASSPORT.payload,
      notes: Array.from({ length: 400 }, (_, i) => `finding ${i} — 48°C`) } };
    expect(b64decodeCompressed(b64encodeCompressed(big))).toEqual(big);
  });

  it("rejects corrupted input rather than returning half a passport", () => {
    // A truncated QR read must fail loudly. Silently returning a partial object
    // would be verified against a signature covering the whole one.
    const enc = b64encodeCompressed(PASSPORT);
    expect(() => b64decodeCompressed(enc.slice(0, Math.floor(enc.length / 2))))
      .toThrow();
  });
});
