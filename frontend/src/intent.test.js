import { beforeEach, describe, expect, it } from "vitest";
import { getIntent, LEAD_CARDS, orderCards, setIntent } from "./intent.js";

const ORDER = ["life", "pipeline", "plain", "summary", "usage", "carbon", "pathways",
  "outlook", "eugrade", "rights", "price", "sell", "security"];

// The tests run without a browser: a minimal session store and event target.
const store = new Map();
globalThis.sessionStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
};
globalThis.window ??= globalThis;
globalThis.window.dispatchEvent ??= () => true;
globalThis.CustomEvent ??= class { constructor(type, init) { this.type = type; this.detail = init?.detail; } };

describe("why the visitor came decides which cards lead (S3-04)", () => {
  beforeEach(() => sessionStorage.clear());

  it("selling brings the price and the sell checklist to the top", () => {
    expect(orderCards(ORDER, "sell").slice(0, 3)).toEqual(["price", "sell", "outlook"]);
  });

  it("safety leads with the security card", () => {
    expect(orderCards(ORDER, "safe")[0]).toBe("security");
  });

  it("only reorders: every card is still there, once", () => {
    for (const k of Object.keys(LEAD_CARDS)) {
      const o = orderCards(ORDER, k);
      expect([...o].sort()).toEqual([...ORDER].sort());
    }
  });

  it("no answer keeps the usual order", () => {
    expect(orderCards(ORDER, null)).toEqual(ORDER);
  });

  it("remembers the answer for the visit and ignores unknown values", () => {
    setIntent("keep");
    expect(getIntent()).toBe("keep");
    setIntent("nonsense");
    expect(getIntent()).toBeNull();
  });
});
