import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, fetchApiJson, getPublicApiUrl, getServerApiUrl } from "./client";

describe("central API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("prefers the internal URL only for server calls", () => {
    const env = {
      INTERNAL_API_URL: "http://backend:8000/",
      NEXT_PUBLIC_API_URL: "https://api.bojro.test/",
    };
    expect(getServerApiUrl(env)).toBe("http://backend:8000");
    expect(getPublicApiUrl(env)).toBe("https://api.bojro.test");
  });

  it("returns typed JSON and builds one normalized URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      fetchApiJson<{ ok: boolean }>("/api/v1/example", { baseUrl: "https://api.test/" }),
    ).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.test/api/v1/example",
      expect.objectContaining({ headers: expect.objectContaining({ Accept: "application/json" }) }),
    );
  });

  it("throws a descriptive error with status and a bounded body", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("catalog unavailable", { status: 503, statusText: "Unavailable" }),
        ),
    );

    const request = fetchApiJson("/api/v1/catalog/products", { baseUrl: "https://api.test" });
    await expect(request).rejects.toBeInstanceOf(ApiError);
    await expect(request).rejects.toMatchObject({
      name: "ApiError",
      status: 503,
      responseBody: "catalog unavailable",
      url: "https://api.test/api/v1/catalog/products",
    });
  });
});
