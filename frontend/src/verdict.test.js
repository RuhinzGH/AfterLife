import { describe, it, expect } from "vitest";
import { VERDICTS, verdictFor } from "./Verifier.jsx";

/**
 * The four verdicts a passport can earn.
 *
 * This is the product's trust claim reduced to one function, and getting it
 * wrong is the most damaging bug available here: a self-signed forgery shown
 * with a green seal would make every genuine passport worthless, because the
 * seal would no longer distinguish anything.
 *
 * The states are deliberately not a boolean. VERIFICATION.md draws the
 * distinction in a table — a valid signature by an UNKNOWN key proves the
 * document is internally consistent and NOTHING about who wrote it — and these
 * tests hold the UI to that table.
 */

const tampered = { valid: false, issued_by_afterlife: false };
const forged = { valid: true, issued_by_afterlife: false };
const genuine = { valid: true, issued_by_afterlife: true };
const unpinned = { valid: true, issued_by_afterlife: null };

describe("verdictFor", () => {
  it("an invalid signature is tampered, whatever the key says", () => {
    expect(verdictFor(tampered)).toBe(VERDICTS.tampered);
    // Even if the key somehow matched, a broken signature outranks it.
    expect(verdictFor({ valid: false, issued_by_afterlife: true })).toBe(VERDICTS.tampered);
  });

  it("a valid signature by an unknown key is NOT the green seal", () => {
    // The failure that would hollow out the whole product: anyone can generate
    // a keypair, sign whatever they like and embed the key. Internally
    // consistent is not genuine.
    const v = verdictFor(forged);
    expect(v).toBe(VERDICTS.unknown_issuer);
    expect(v.tone).toBe("warn");
    expect(v.tone).not.toBe("good");
  });

  it("only a pinned key earns 'Issued by AfterLife'", () => {
    expect(verdictFor(genuine)).toBe(VERDICTS.genuine);
    expect(verdictFor(genuine).label).toMatch(/issued by afterlife/i);
    expect(verdictFor(forged).label).not.toMatch(/issued by afterlife/i);
  });

  it("no trusted key available is its own state, not a pass or a fail", () => {
    // null means "could not check", which is different from "checked and it
    // did not match". Collapsing them either way would be a lie.
    expect(verdictFor(unpinned)).toBe(VERDICTS.valid_unpinned);
    expect(verdictFor(unpinned)).not.toBe(VERDICTS.genuine);
    expect(verdictFor(unpinned)).not.toBe(VERDICTS.unknown_issuer);
  });
});

describe("every verdict answers all three questions", () => {
  it("states what is NOT proven, always", () => {
    // C2PA's validated-vs-asserted split. Even the green seal has a limit:
    // the signature proves the document is intact, not that the scan read
    // true hardware. A verdict with no stated limit is overclaiming.
    for (const v of Object.values(VERDICTS)) {
      expect(v.asserted).toBeTruthy();
      expect(v.asserted.length).toBeGreaterThan(30);
    }
  });

  it("tells the reader what to do", () => {
    // The row most verifiers omit. "Signature valid" is not an instruction,
    // and the person reading this is deciding whether to buy a laptop.
    for (const v of Object.values(VERDICTS)) {
      expect(v.action).toBeTruthy();
      expect(v.action.length).toBeGreaterThan(20);
    }
  });

  it("only claims something proven when something IS proven", () => {
    // A tampered document proves nothing, so it must not show a Proven row.
    expect(VERDICTS.tampered.validated).toBeNull();
    for (const key of ["unknown_issuer", "genuine", "valid_unpinned"]) {
      expect(VERDICTS[key].validated).toBeTruthy();
    }
  });

  it("the genuine seal still admits the attestation gap", () => {
    // Ed25519 proves "not edited since issue", never "the scan was told
    // the truth by the machine". README lists this as a known limitation and
    // the UI should not quietly drop it.
    expect(VERDICTS.genuine.asserted.toLowerCase()).toContain("attestation");
  });

  it("exactly one verdict is green-toned on an unpinned-or-worse result", () => {
    expect(VERDICTS.tampered.tone).toBe("bad");
    expect(VERDICTS.unknown_issuer.tone).toBe("warn");
    expect(VERDICTS.genuine.tone).toBe("good");
  });
});
