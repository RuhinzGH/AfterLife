import { describe, expect, it } from "vitest";
import { INTRO_KEY, shouldPlayIntro, markIntroPlayed } from "./introGate.js";

// A stand-in for sessionStorage: same getItem/setItem surface.
function memoryStore(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    data,
  };
}

describe("intro plays once per browser session", () => {
  it("plays on the first load of a session", () => {
    expect(shouldPlayIntro(memoryStore(), false)).toBe(true);
  });

  it("does not play again once marked as played", () => {
    const store = memoryStore();
    markIntroPlayed(store);
    expect(store.data[INTRO_KEY]).toBe("1");
    expect(shouldPlayIntro(store, false)).toBe(false);
  });

  it("never plays for someone who asked for reduced motion", () => {
    expect(shouldPlayIntro(memoryStore(), true)).toBe(false);
  });

  it("still plays when storage is unavailable, rather than crashing", () => {
    const broken = {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("blocked"); },
    };
    expect(shouldPlayIntro(broken, false)).toBe(true);
    expect(() => markIntroPlayed(broken)).not.toThrow();
  });
});
