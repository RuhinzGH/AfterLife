import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
  test: {
    // Node by default, NOT jsdom. Booting jsdom cost 72 seconds of a 76-second
    // run, and most of these modules are pure logic -- btoa, TextEncoder and
    // structuredClone are all native in Node now. The handful that genuinely
    // read document or matchMedia opt in per file with
    //     // @vitest-environment jsdom
    // on the first line, which keeps that cost on the files that need it
    // instead of on every run.
    environment: "node",
    include: ["src/**/*.test.js"],
    // Keep the runner out of the production bundle's way -- vitest only reads
    // this block, and `npm run build` ignores it entirely.
    restoreMocks: true,
  },
});
