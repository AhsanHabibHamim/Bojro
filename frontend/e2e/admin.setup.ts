import { test as setup } from "@playwright/test";
import { mkdir } from "node:fs/promises";

import { adminLogin, hasAdminCredentials } from "./admin-helpers";

const authFile = "test-results/.auth/admin.json";

setup("authenticate dedicated admin session", async ({ page }) => {
  await mkdir("test-results/.auth", { recursive: true });
  if (process.env.CI === "true") {
    const missing = [
      ["E2E_ADMIN_EMAIL", process.env.E2E_ADMIN_EMAIL],
      ["E2E_ADMIN_PASSWORD", process.env.E2E_ADMIN_PASSWORD],
      ["E2E_ADMIN_ORDER_NUMBER", process.env.E2E_ADMIN_ORDER_NUMBER],
      ["NEXT_PUBLIC_E2E_STORAGE_MOCK", process.env.NEXT_PUBLIC_E2E_STORAGE_MOCK],
    ]
      .filter(([, value]) => !value)
      .map(([name]) => name);
    if (missing.length)
      throw new Error(`Missing required admin E2E environment: ${missing.join(", ")}`);
    if (process.env.NEXT_PUBLIC_E2E_STORAGE_MOCK !== "1") {
      throw new Error("NEXT_PUBLIC_E2E_STORAGE_MOCK must be 1 for admin E2E");
    }
  }
  if (hasAdminCredentials) await adminLogin(page);
  await page.context().storageState({ path: authFile });
});
