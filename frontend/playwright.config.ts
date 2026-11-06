import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      grepInvert: /@mobile-dashboard/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-account-dashboard",
      grep: /@mobile-dashboard/,
      use: { ...devices["Pixel 7"] },
    },
  ],
  webServer: process.env.PLAYWRIGHT_SKIP_WEBSERVER
    ? undefined
    : {
        command: "NEXT_PUBLIC_E2E_STORAGE_MOCK=1 pnpm dev",
        url: "http://localhost:3000/en",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
