import { act, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CommerceApi } from "@/lib/commerce/client";
import type { SessionResponse } from "@/lib/commerce/types";
import type { ProductDetail } from "@/lib/catalog/types";
import { sessionFixture } from "@/test/commerce-fixtures";
import { createFakeCommerceApi, renderWithCommerce } from "@/test/render-commerce";

import { ProductReviews } from "./product-reviews";

const reviewEligibility = vi.hoisted(() => vi.fn());
vi.mock("@/lib/account/client", () => ({ accountApi: { reviewEligibility } }));

const product: ProductDetail = {
  id: "product-1",
  slug: "charger",
  name: "Charger",
  category: { id: "category-1", slug: "electronics", name: "Electronics" },
  brand: null,
  image: null,
  price: 100_000,
  compare_at_price: null,
  currency: "BDT",
  discount_percent: null,
  rating_avg: 5,
  rating_count: 0,
  stock_status: "in_stock",
  description: "Description",
  breadcrumb: [],
  images: [],
  options: [],
  variants: [],
  rating_histogram: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 },
  reviews: { items: [], next_cursor: null, total: 0 },
  related: [],
  seo: { title: "Charger", description: "Description" },
};

const labels = {
  title: "Reviews",
  basedOn: "Based on {count}",
  verified: "Verified",
  emptyTitle: "No reviews",
  emptyDescription: "No reviews yet",
  loadMore: "Load more",
  loading: "Loading",
  loadError: "Could not load",
  writeReview: "Write review",
  editReview: "Edit review",
  signInToReview: "Sign in",
};

describe("ProductReviews principal isolation", () => {
  it("does not expose a late eligibility result from the previous account", async () => {
    let notifySession: ((session: SessionResponse) => void) | undefined;
    let resolveFirst: ((value: unknown) => void) | undefined;
    reviewEligibility
      .mockReset()
      .mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce({
        product_id: "product-1",
        eligible: false,
        reason: "already_reviewed",
        existing_review: { id: "review-user-2", status: "approved", revision: 1 },
      });
    const api = createFakeCommerceApi({
      setSessionListener: vi.fn((listener: (session: SessionResponse) => void) => {
        notifySession = listener;
      }),
    }) as CommerceApi;
    renderWithCommerce(<ProductReviews labels={labels} locale="en" product={product} />, {
      api,
      session: sessionFixture({
        authenticated: true,
        user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
      }),
    });
    await waitFor(() => expect(reviewEligibility).toHaveBeenCalledTimes(1));

    act(() => {
      notifySession?.(
        sessionFixture({
          authenticated: true,
          user: { id: "user-2", name: "Nila", phone: "01800000000", email: null },
        }),
      );
    });
    expect(await screen.findByRole("link", { name: "Edit review" })).toHaveAttribute(
      "href",
      "/en/account/reviews/review-user-2/edit",
    );
    await act(async () => {
      resolveFirst?.({
        product_id: "product-1",
        eligible: true,
        reason: "eligible",
        existing_review: null,
      });
    });
    expect(screen.queryByRole("link", { name: "Write review" })).not.toBeInTheDocument();
  });
});
