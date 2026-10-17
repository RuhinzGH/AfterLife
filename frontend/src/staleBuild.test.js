import { describe, expect, it, vi } from "vitest";
import { isStaleBuildError, reloadIfStale } from "./staleBuild.js";

function store() {
  const m = new Map();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
}
const STALE = new Error("Failed to fetch dynamically imported module: https://afterlife-ruhin.vercel.app/assets/DeepScan-D58-D8Hk.js");

describe("an old tab after a new deploy reloads itself once", () => {
  it("recognises the browsers' stale-file messages, and nothing else", () => {
    expect(isStaleBuildError(STALE)).toBe(true);
    expect(isStaleBuildError(new TypeError("Importing a module script failed."))).toBe(true);
    expect(isStaleBuildError(new Error("Cannot read properties of undefined"))).toBe(false);
  });

  it("reloads on the first failure but not again within 30 seconds", () => {
    const storage = store(), reload = vi.fn();
    expect(reloadIfStale(STALE, { storage, reload, now: 1000 })).toBe(true);
    expect(reloadIfStale(STALE, { storage, reload, now: 5000 })).toBe(false);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(reloadIfStale(STALE, { storage, reload, now: 40000 })).toBe(true);
  });

  it("never reloads for an ordinary error", () => {
    const reload = vi.fn();
    expect(reloadIfStale(new Error("boom"), { storage: store(), reload })).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});
