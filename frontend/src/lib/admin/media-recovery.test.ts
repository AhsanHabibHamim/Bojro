import { beforeEach, describe, expect, it } from "vitest";

import {
  clearPendingMediaCompletion,
  persistPendingMediaCompletion,
  readPendingMediaCompletion,
  type PendingMediaCompletion,
} from "./media-recovery";

const pending: PendingMediaCompletion = {
  uploadId: "upload-1",
  uploadEtag: '"upload-etag"',
  idempotencyKey: "00000000-0000-4000-8000-000000000001",
  completion: {
    public_id: "admin/product/upload-1",
    provider_asset_id: "asset-1",
    byte_size: 1024,
    format: "png",
    width: 128,
    height: 128,
    version: 1,
    signature: "completion-proof",
  },
  createdAt: Date.now(),
};

describe("media completion recovery", () => {
  beforeEach(() => sessionStorage.clear());

  it("persists the exact completion command and replay key", () => {
    persistPendingMediaCompletion("admin-1", "product", pending);
    expect(readPendingMediaCompletion("admin-1", "product")).toEqual(pending);
  });

  it("clears only the matching principal and purpose record", () => {
    persistPendingMediaCompletion("admin-1", "product", pending);
    persistPendingMediaCompletion("admin-1", "banner", { ...pending, uploadId: "upload-2" });
    clearPendingMediaCompletion("admin-1", "product");
    expect(readPendingMediaCompletion("admin-1", "product")).toBeNull();
    expect(readPendingMediaCompletion("admin-1", "banner")?.uploadId).toBe("upload-2");
  });
});
