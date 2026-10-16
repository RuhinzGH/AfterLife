// Sign-up password rules, following NIST SP 800-63B revision 4 (2024):
//   * length over complexity: at least 15 characters when a password is the
//     only way to sign in (as here: there is no second factor);
//   * no forced composition rules (no "must contain a capital / a symbol"),
//     because they push people towards predictable patterns like "Password1!";
//   * screen out passwords that are common or trivially guessable.
// Supabase also enforces the minimum on its side (set in its dashboard), so
// skipping this page cannot get a short password through. Supabase stores at
// most 72 characters of a password, so longer ones are refused rather than
// silently cut short.
//
// Sign-in never applies these rules: an existing password is checked by
// Supabase as it is, whatever rules were in force when it was made.

export const MIN_LENGTH = 15;
export const MAX_LENGTH = 72;

// Well-known long passwords and patterns that meet the length but not the spirit.
const COMMON = new Set([
  "passwordpassword", "passwordpassword1", "password123456789", "password1234567", "password12345678",
  "iloveyouiloveyou", "letmeinletmein", "qwertyuiopasdfg", "qwertyuiopasdfgh", "qwertyuiopasdfghjkl",
  "1q2w3e4r5t6y7u8i", "1q2w3e4r5t6y7u8i9o", "q1w2e3r4t5y6u7i8", "administrator123", "welcomewelcome1",
  "abcdefghijklmnop", "zxcvbnmasdfghjkl", "trustno1trustno1", "changemechangeme", "monkeymonkeymonkey",
]);

function normalise(pw) {
  return pw.toLowerCase().replace(/\s+/g, "");
}

// One character over and over, or a straight run along digits, the alphabet or a keyboard row.
function isTrivialPattern(n) {
  if (/^(.)\1+$/.test(n)) return true;
  if (/^(.{1,4})\1+$/.test(n)) return true;                       // "abcabcabc...", "12121212..."
  const runs = ["01234567890123456789", "abcdefghijklmnopqrstuvwxyz", "qwertyuiopasdfghjklzxcvbnm"];
  return runs.some((r) => r.includes(n) || [...r].reverse().join("").includes(n));
}

// The checks shown live under the password field. `email` lets a password that
// is just the user's own email name be refused.
export function passwordChecks(pw, email = "") {
  const n = normalise(pw);
  const name = normalise((email.split("@")[0] || ""));
  const guessable = COMMON.has(n) || isTrivialPattern(n) || (name.length >= 4 && n.replace(/\d+/g, "") === name);
  return {
    length: pw.length >= MIN_LENGTH,
    notTooLong: pw.length <= MAX_LENGTH,
    notCommon: n.length > 0 && !guessable,
  };
}

export function passwordValid(pw, email = "") {
  const c = passwordChecks(pw, email);
  return c.length && c.notTooLong && c.notCommon;
}
