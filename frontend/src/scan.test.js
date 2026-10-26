import { describe, expect, it } from "vitest";
import { osLabel } from "./scan.js";

describe("osLabel", () => {
  it("translates Windows platform versions into Windows 10 or 11", () => {
    expect(osLabel({ platform: "Windows", platformVersion: "15.0.0" })).toBe("Windows 11 (build 15.0.0)");
    expect(osLabel({ platform: "Windows", platformVersion: "10.0.0" })).toBe("Windows 10 (build 10.0.0)");
  });

  it("keeps Android's own release number (S2-D16: Android 16 used to read 'Android 11')", () => {
    expect(osLabel({ platform: "Android", platformVersion: "16.0.0" })).toBe("Android 16 (build 16.0.0)");
    expect(osLabel({ platform: "Android", platformVersion: "13.0.0" })).toBe("Android 13 (build 13.0.0)");
  });

  it("keeps macOS's own release number", () => {
    expect(osLabel({ platform: "macOS", platformVersion: "15.1.0" })).toBe("macOS 15 (build 15.1.0)");
  });

  it("falls back to the browser's platform string when versions are hidden", () => {
    expect(osLabel({}, "Linux armv81")).toBe("Linux armv81");
    expect(osLabel(undefined, undefined)).toBe("Unknown OS");
  });
});
