import { defineConfig, devices } from "@playwright/test";

// Starts the FastAPI backend (offline: stub model, local index) and the production Next.js build.
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
    ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}),
  },
  webServer: [
    {
      command: "python -m uvicorn dealroom.api.app:app --port 8000",
      cwd: "..",
      url: "http://localhost:8000/health",
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run build && npm run start",
      url: "http://localhost:3000",
      timeout: 300_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
