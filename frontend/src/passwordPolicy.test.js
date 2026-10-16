import { describe, expect, it } from "vitest";
import { MIN_LENGTH, passwordChecks, passwordValid } from "./passwordPolicy.js";

describe("sign-up passwords follow NIST SP 800-63B rev. 4", () => {
  it("asks for at least 15 characters", () => {
    expect(MIN_LENGTH).toBe(15);
    expect(passwordValid("short pass 123")).toBe(false);          // 14 characters
    expect(passwordValid("purple tea before seven")).toBe(true);
  });

  it("forces no capitals, digits or symbols", () => {
    expect(passwordValid("purple tea before seven")).toBe(true);  // all lower case, no digit, no symbol
  });

  it("refuses common and trivially guessable long passwords", () => {
    for (const pw of ["passwordpassword", "aaaaaaaaaaaaaaaaaaa", "123456789012345", "qwertyuiopasdfgh", "abcabcabcabcabcabc"]) {
      expect(passwordChecks(pw).notCommon).toBe(false);
    }
  });

  it("refuses a password that is just the email name", () => {
    expect(passwordValid("ruhinzaidiruhin", "ruhinzaidiruhin@gmail.com")).toBe(false);
  });

  it("refuses more than Supabase stores (72 characters) instead of silently cutting it", () => {
    expect(passwordChecks("x".repeat(30) + "y".repeat(50)).notTooLong).toBe(false);
  });
});
