import { describe, expect, it } from "vitest";
import { passportHtml, passportRows } from "./passportPdf.js";

const INSTANT = {
  payload: { device_id: "AL-1", tier: "browser profile", issued: "2026-10-19", os: "Windows 10", gpu: "Intel UHD",
    cpu_cores: 8, ram_gb: 8, product_category: "Laptop", lifecycle: { device_age: 4, fault_themes: ["Battery"] } },
  signature: "sig", issuer_pubkey: "abcdef0123456789zzzz",
};
const DEEP = {
  payload: { device_id: "AL-2", tier: "full scan", issued: "2026-10-19", make_model: "Dell Latitude 5490",
    cpu: "i5-8250U", cpu_cores: 4, os: "Windows 10 Pro", trust_score: 62, grade: "C - serviceable",
    battery_health: "55%", storage: "256 GB SSD", storage_health: "healthy (Windows)", win11: "ELIGIBLE" },
  signature: "sig",
};

describe("the PDF passport (S3-02)", () => {
  it("prints only the facts the passport holds, and labels browser readings", () => {
    const rows = Object.fromEntries(passportRows(INSTANT.payload));
    expect(rows.Memory).toBe("8 GB or more (browser reading)");
    expect(rows["Reported fault"]).toBe("Battery");
    expect(rows).not.toHaveProperty("Battery");          // a browser cannot read it
  });

  it("a deep scan prints its measured facts and score", () => {
    const rows = Object.fromEntries(passportRows(DEEP.payload));
    expect(rows.Battery).toBe("55%");
    expect(rows["Measured hardware score"]).toBe("62 / 100");
  });

  it("shows the full assessment's score when given, and carries the QR", () => {
    const html = passportHtml(INSTANT, { qr: "data:image/png;base64,xx", final: { score: 67, grade: "C - serviceable" }, origin: "https://x" });
    expect(html).toContain(">67<");
    expect(html).toContain("data:image/png;base64,xx");
    expect(html).toContain("the signature lives in the QR");
  });

  it("escapes text so a crafted field cannot inject markup", () => {
    const evil = { ...INSTANT, payload: { ...INSTANT.payload, os: "<script>alert(1)</script>" } };
    expect(passportHtml(evil)).not.toContain("<script>alert");
  });
});
