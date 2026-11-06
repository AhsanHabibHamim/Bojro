import { revalidateTag } from "next/cache";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

const endpoint = "http://localhost:3000/api/revalidate";

describe("catalog revalidation endpoint", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.REVALIDATION_SECRET = "test-revalidation-secret";
  });

  it("rejects requests without the shared secret", async () => {
    const response = await POST(
      new Request(endpoint, {
        method: "POST",
        body: JSON.stringify({ entity: "homepage", event: "updated" }),
      }),
    );
    expect(response.status).toBe(401);
    expect(revalidateTag).not.toHaveBeenCalled();
  });

  it("accepts Bangla identifiers and invalidates all product dependencies", async () => {
    const response = await POST(
      new Request(endpoint, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-revalidation-secret": "test-revalidation-secret",
        },
        body: JSON.stringify({ entity: "product", event: "updated", slug: "চা-পাতা" }),
      }),
    );
    const body = (await response.json()) as { revalidated: boolean; tags: string[] };

    expect(response.status).toBe(200);
    expect(body.revalidated).toBe(true);
    expect(body.tags).toContain("catalog:products");
    expect(body.tags.some((tag) => tag.startsWith("catalog:product:চা-পাতা-"))).toBe(true);
    expect(revalidateTag).toHaveBeenCalledWith("catalog:filters", "max");
  });
});
