import { describe, expect, it, vi } from "vitest";

import { AdminClient } from "./client";
import { AdminTransport } from "./transport";
import type { AdminMediaUpload } from "./types";

describe("admin media boundary", () => {
  it("fails closed for signed mock uploads unless explicit local E2E mode is enabled", async () => {
    vi.stubEnv("NEXT_PUBLIC_E2E_STORAGE_MOCK", "0");
    const client = new AdminClient({
      transport: new AdminTransport({
        baseUrl: "https://api.test",
        fetch: vi.fn(),
      }),
    });
    const signed: AdminMediaUpload = {
      id: "upload-1",
      provider: "mock",
      purpose: "product",
      state: "pending",
      upload_url: "https://bojro-storage-mock.invalid/upload",
      upload_method: "POST",
      fields: { public_id: "admin/product/upload-1", signature: "signed" },
      expires_at: new Date(Date.now() + 60_000).toISOString(),
    };
    await expect(
      client.uploadMedia(signed, new File(["image"], "image.jpg", { type: "image/jpeg" })),
    ).rejects.toMatchObject({ code: "MEDIA_UPLOAD_FAILED" });
    vi.unstubAllEnvs();
  });
});
