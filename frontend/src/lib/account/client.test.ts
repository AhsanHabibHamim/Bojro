import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthenticatedTransport } from "@/lib/api/authenticated-transport";
import { sessionFixture } from "@/test/commerce-fixtures";

import { AccountClient } from "./client";

afterEach(() => vi.unstubAllEnvs());

function jsonResponse(body: unknown, status = 200, headers: HeadersInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

const profile = {
  id: "user-1",
  name: "Asha",
  phone: "01700000000",
  email: null,
  role: "customer" as const,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  revision: 2,
};

describe("AccountClient", () => {
  it("sends credentials, CSRF, If-Match, no-store, and reads strong ETags", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ ...profile, name: "Nila", revision: 3 }, 200, { ETag: '"profile:3"' }),
      );
    const transport = new AuthenticatedTransport({
      baseUrl: "https://api.example.test",
      fetch: fetchMock,
    });
    transport.setCsrfToken("csrf-account");
    const client = new AccountClient({ transport });

    await expect(client.updateProfile("Nila", '"profile:2"')).resolves.toEqual({
      data: { ...profile, name: "Nila", revision: 3 },
      etag: '"profile:3"',
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(url).toBe("https://api.example.test/api/v1/account/profile");
    expect(init.credentials).toBe("include");
    expect(init.cache).toBe("no-store");
    expect(headers.get("X-CSRF-Token")).toBe("csrf-account");
    expect(headers.get("If-Match")).toBe('"profile:2"');
  });

  it("keeps idempotency headers across the single refresh retry", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              code: "ACCESS_EXPIRED",
              message: "Expired",
              field_errors: [],
              request_id: "r1",
            },
          },
          401,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(sessionFixture({ can_refresh: true })))
      .mockResolvedValueOnce(
        jsonResponse(
          sessionFixture({
            authenticated: true,
            can_refresh: true,
            user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
            access_expires_at: new Date(Date.now() + 900_000).toISOString(),
          }),
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ id: "address-1", revision: 1 }, 201));
    const transport = new AuthenticatedTransport({
      baseUrl: "https://api.example.test",
      fetch: fetchMock,
    });
    transport.setCsrfToken("csrf-before");
    const client = new AccountClient({ transport });

    await client.createAddress(
      {
        label: "Home",
        recipient: "Asha",
        phone: "+8801700000000",
        division_id: "division-1",
        district_id: "district-1",
        upazila_id: "upazila-1",
        address_line: "12 Test Road",
      },
      "00000000-0000-4000-8000-000000000001",
      "en",
    );

    const firstHeaders = new Headers((fetchMock.mock.calls[0] as [string, RequestInit])[1].headers);
    const retryHeaders = new Headers((fetchMock.mock.calls[3] as [string, RequestInit])[1].headers);
    expect(firstHeaders.get("Idempotency-Key")).toBe("00000000-0000-4000-8000-000000000001");
    expect(retryHeaders.get("Idempotency-Key")).toBe("00000000-0000-4000-8000-000000000001");
    expect(retryHeaders.get("X-CSRF-Token")).toBe("csrf-test");
  });

  it("uploads signed photos as external FormData without credentials", async () => {
    const uploadFetch = vi.fn().mockResolvedValue(
      jsonResponse({
        public_id: "review/upload-1",
        asset_id: "asset-1",
        bytes: 3,
        format: "png",
        width: 1,
        height: 1,
        signature: "provider-signature",
      }),
    );
    const client = new AccountClient({
      transport: new AuthenticatedTransport({
        baseUrl: "https://api.example.test",
        fetch: vi.fn(),
      }),
      uploadFetch,
    });
    const file = new File(["img"], "review.png", { type: "image/png" });

    await client.uploadReviewPhoto(
      {
        upload_id: "upload-1",
        provider: "cloudinary",
        upload_url: "https://api.cloudinary.com/v1_1/demo/image/upload",
        upload_method: "POST",
        fields: { signature: "signed", api_key: "public-key" },
        expires_at: "2026-11-07T00:00:00Z",
      },
      file,
    );

    const [url, init] = uploadFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("api.cloudinary.com");
    expect(init.credentials).toBe("omit");
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it("accepts mock storage only behind the explicit local E2E build flag", async () => {
    const uploadFetch = vi.fn();
    const client = new AccountClient({
      transport: new AuthenticatedTransport({
        baseUrl: "https://api.example.test",
        fetch: vi.fn(),
      }),
      uploadFetch,
    });
    const signed = {
      upload_id: "upload-1",
      provider: "mock" as const,
      upload_url: "https://bojro-storage-mock.invalid/upload-1",
      upload_method: "POST" as const,
      fields: { public_id: "review/upload-1", signature: "signed" },
      expires_at: "2026-11-07T00:00:00Z",
    };
    const file = new File(["img"], "review.png", { type: "image/png" });

    await expect(client.uploadReviewPhoto(signed, file)).rejects.toMatchObject({
      code: "PHOTO_UPLOAD_FAILED",
    });
    vi.stubEnv("NEXT_PUBLIC_E2E_STORAGE_MOCK", "1");
    await expect(client.uploadReviewPhoto(signed, file)).resolves.toMatchObject({
      public_id: "review/upload-1",
      byte_size: 3,
      format: "png",
    });
    expect(uploadFetch).not.toHaveBeenCalled();
  });

  it("adapts nested page_info and account wishlist cards", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        items: [
          {
            id: "wishlist-1",
            saved_at: "2026-11-07T00:00:00Z",
            product: {
              id: "product-1",
              slug: "charger",
              name: "Charger",
              name_bn: "চার্জার",
              name_en: "Charger",
              thumbnail: { id: "image-1", url: "/charger.webp", alt: "Charger", variant_id: null },
              category: { id: "category-1", slug: "electronics", name: "Electronics" },
              brand: null,
              price: {
                current_poisha: 125_000,
                compare_at_poisha: 150_000,
                currency: "BDT",
                discount_percent: 17,
                default_variant_id: "variant-1",
              },
              rating: { average: 4.5, count: 12 },
              sold_count: 30,
              is_featured: true,
              in_stock: true,
              available: true,
            },
          },
        ],
        page_info: { next_cursor: "next-page", has_next: true },
      }),
    );
    const client = new AccountClient({
      transport: new AuthenticatedTransport({
        baseUrl: "https://api.example.test",
        fetch: fetchMock,
      }),
    });

    await expect(client.wishlist("en")).resolves.toEqual({
      items: [
        expect.objectContaining({
          id: "wishlist-1",
          available: true,
          product: expect.objectContaining({
            price: 125_000,
            compare_at_price: 150_000,
            stock_status: "in_stock",
          }),
        }),
      ],
      next_cursor: "next-page",
    });
  });
});
