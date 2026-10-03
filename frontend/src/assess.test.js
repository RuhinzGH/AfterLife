import { describe, it, expect, vi, beforeEach } from "vitest";

/**
 * The bridge from a signed passport to the score request.
 *
 * fetchAssessment is a mapping with fallback chains, which is the kind of code
 * that breaks silently: a wrong branch does not throw, it just sends a slightly
 * different number and the grade moves.
 *
 * Several assertions guard the bug class this project cares most about --
 * absence of evidence sent as evidence. A browser cannot read battery health,
 * so that field must never arrive as a confident figure.
 */

const { assess } = vi.hoisted(() => ({ assess: vi.fn(async () => ({ ok: true })) }));
vi.mock("./api.js", () => ({ api: { assess } }));

const { fetchAssessment } = await import("./assess.js");

/** The body that actually went to /api/assess. */
function sent() {
  expect(assess).toHaveBeenCalledTimes(1);
  return assess.mock.calls[0][0];
}

const SCANNED = {
  os: "Microsoft Windows 10 Home",
  age_years: 6,
  lifecycle: { eol_risk: 0.31, device_age: 4.2, fault_described: false },
};

const BARE = { os: "Microsoft Windows 10 Home", age_years: 6, lifecycle: {} };

beforeEach(() => { assess.mockClear(); });

describe("what a browser scan must NOT claim", () => {
  it("sends no battery health at all, even if one is present on the payload", async () => {
    await fetchAssessment({ ...SCANNED, battery_health: "90%" }, null);
    expect(sent()).not.toHaveProperty("battery_health");
  });

  it("starts from the documented default trust score", async () => {
    await fetchAssessment(SCANNED, null);
    expect(sent().hardware_trust).toBe(75);
  });
});

describe("the ML outlook travels with the request", () => {
  it("forwards the signed end-of-life risk", async () => {
    await fetchAssessment(SCANNED, null);
    expect(sent().eol_risk).toBe(0.31);
  });

  it("sends null when the model did not run", async () => {
    await fetchAssessment(BARE, null);
    expect(sent().eol_risk).toBeNull();
  });
});

describe("age falls back through three sources in order", () => {
  it("prefers the lifecycle figure", async () => {
    await fetchAssessment(SCANNED, { device_age: "9" });
    expect(sent().age_years).toBe(4.2);
  });

  it("uses the user's entry when lifecycle has none", async () => {
    await fetchAssessment(BARE, { device_age: "9" });
    expect(sent().age_years).toBe(9);
  });

  it("falls back to the payload's own age when neither is given", async () => {
    await fetchAssessment(BARE, null);
    expect(sent().age_years).toBe(6);
  });
});

describe("country and category", () => {
  it("lets an explicit country override the timezone guess", async () => {
    await fetchAssessment(SCANNED, { country: "IE" });
    expect(sent().country).toBe("IE");
  });

  it("sends the timezone rather than anything identifying", async () => {
    const body = await fetchAssessment(SCANNED, null).then(sent);
    expect(typeof body.timezone === "string" || body.timezone === null).toBe(true);
    expect(body).not.toHaveProperty("ip");
  });

  it("prefers the user's stated product category over the payload's", async () => {
    await fetchAssessment({ ...SCANNED, product_category: "Laptop" },
                          { product_category: "Tablet" });
    expect(sent().product_category).toBe("Tablet");
  });
});
