import { describe, expect, it } from "vitest";
import { parseRecoveryHash } from "./recovery.js";

describe("parseRecoveryHash", () => {
  it("reads the tokens from a reset link", () => {
    const r = parseRecoveryHash("#access_token=aaa&expires_in=3600&refresh_token=bbb&token_type=bearer&type=recovery");
    expect(r).toEqual({ tokens: { access_token: "aaa", refresh_token: "bbb" } });
  });

  it("explains an expired or used link", () => {
    const r = parseRecoveryHash("#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired");
    expect(r.error).toMatch(/expired/);
  });

  it("ignores the site's own routes and sign-up links", () => {
    expect(parseRecoveryHash("#/home")).toBeNull();
    expect(parseRecoveryHash("#/verify")).toBeNull();
    expect(parseRecoveryHash("")).toBeNull();
    expect(parseRecoveryHash("#access_token=aaa&refresh_token=bbb&type=signup")).toBeNull();
  });
});
