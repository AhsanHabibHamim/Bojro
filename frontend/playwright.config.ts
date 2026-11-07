import { defineConfig, devices } from "@playwright/test";

const adminAuthFile = "test-results/.auth/admin.json";

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
      name: "admin-setup",
      testMatch: /admin\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium",
      grepInvert: /@mobile-dashboard|@admin/,
      testIgnore: /admin\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile-account-dashboard",
      grep: /@mobile-dashboard/,
      testIgnore: /admin\.setup\.ts/,
      use: { ...devices["Pixel 7"] },
    },
    {
      name: "admin-auth",
      grep: /@admin-auth/,
      testIgnore: /admin\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "admin-chromium",
      dependencies: ["admin-setup"],
      grep: /@admin/,
      grepInvert: /@admin-auth|@admin-mobile/,
      testIgnore: /admin\.setup\.ts/,
      use: { ...devices["Desktop Chrome"], storageState: adminAuthFile },
    },
    {
      name: "admin-mobile",
      dependencies: ["admin-setup"],
      grep: /@admin-mobile/,
      testIgnore: /admin\.setup\.ts/,
      use: { ...devices["Pixel 7"], storageState: adminAuthFile },
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
