import { describe, expect, it } from "vitest";
import { groupDevices } from "./MyScans.jsx";

const scan = (id, device_id, type, when, links) => ({
  id, scan_type: type, created_at: when,
  passport: { payload: { device_id }, ...(links ? { links } : {}) },
});

describe("groupDevices", () => {
  it("joins an instant and a deep scan of one machine when they are linked", () => {
    const d = groupDevices([
      scan(1, "AFL-AAAAAAAAAA", "instant", "2026-10-26T10:00:00Z"),
      scan(2, "AFL-BBBBBBBBBB", "deep", "2026-10-27T10:00:00Z", ["AFL-AAAAAAAAAA"]),
    ]);
    expect(d).toHaveLength(1);
    expect(d[0].deviceId).toBe("AFL-BBBBBBBBBB");          // the deep scan leads the card
    expect(d[0].ids.sort()).toEqual(["AFL-AAAAAAAAAA", "AFL-BBBBBBBBBB"]);
  });

  it("keeps unlinked machines apart", () => {
    const d = groupDevices([
      scan(1, "AFL-AAAAAAAAAA", "instant", "2026-10-26T10:00:00Z"),
      scan(2, "AFL-CCCCCCCCCC", "instant", "2026-10-27T10:00:00Z"),
    ]);
    expect(d).toHaveLength(2);
  });

  it("ignores links to devices that aren't in the list", () => {
    const d = groupDevices([scan(1, "AFL-AAAAAAAAAA", "instant", "2026-10-26T10:00:00Z", ["AFL-ZZZZZZZZZZ"])]);
    expect(d).toHaveLength(1);
  });
});
