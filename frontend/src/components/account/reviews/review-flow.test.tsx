import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccountError, type AccountApi } from "@/lib/account/client";
import { renderWithAccount } from "@/test/render-account";

import { ReviewForm } from "./review-form";
import { ReviewPhotoUploader } from "./review-photo-uploader";

const replace = vi.fn();
const back = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, back, push: vi.fn() }),
}));

describe("review customer flows", () => {
  beforeEach(() => {
    replace.mockReset();
    back.mockReset();
    sessionStorage.clear();
  });

  it("signs, externally uploads, completes, and cancels review photos", async () => {
    const accountApi = {
      signReviewPhoto: vi.fn().mockResolvedValue({
        upload_id: "upload-1",
        provider: "cloudinary",
        upload_url: "https://storage.example/upload",
        upload_method: "POST",
        fields: { signature: "signed" },
        expires_at: "2026-11-07T00:00:00Z",
      }),
      uploadReviewPhoto: vi.fn().mockResolvedValue({
        public_id: "review/upload-1",
        provider_asset_id: "asset-1",
        byte_size: 5,
        format: "webp",
        width: 100,
        height: 100,
        signature: "verified",
      }),
      completeReviewPhoto: vi.fn().mockResolvedValue({
        upload_id: "upload-1",
        state: "ready",
        preview_url: "https://res.cloudinary.com/demo/review.webp",
      }),
      cancelReviewPhoto: vi.fn().mockResolvedValue(undefined),
    } as unknown as AccountApi;
    const onChange = vi.fn();
    const owned = new Set<string>();
    const ownershipProps = {
      isOwnedUpload: (id: string) => owned.has(id),
      onUploadReady: (id: string) => owned.add(id),
      onUploadReleased: (id: string) => owned.delete(id),
    };
    const { container, rerender } = renderWithAccount(
      <ReviewPhotoUploader {...ownershipProps} onChange={onChange} photos={[]} />,
      { accountApi },
    );
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(screen.getByLabelText("Choose review photos")).toBe(input);
    const file = new File(["photo"], "review.webp", { type: "image/webp" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const photos = onChange.mock.calls[0]![0];
    expect(accountApi.signReviewPhoto).toHaveBeenCalledWith(
      { filename: "review.webp", mime_type: "image/webp", byte_size: file.size },
      expect.any(String),
    );
    expect(accountApi.completeReviewPhoto).toHaveBeenCalledWith("upload-1", {
      public_id: "review/upload-1",
      provider_asset_id: "asset-1",
      byte_size: 5,
      format: "webp",
      width: 100,
      height: 100,
      signature: "verified",
    });

    rerender(<ReviewPhotoUploader {...ownershipProps} onChange={onChange} photos={photos} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Remove photo" }));
    expect(accountApi.cancelReviewPhoto).toHaveBeenCalledWith("upload-1");
  });

  it("submits only eligible rating/body reviews with one replay-safe key", async () => {
    const accountApi = {
      reviewEligibility: vi.fn().mockResolvedValue({
        product_id: "product-1",
        eligible: true,
        reason: "eligible",
        existing_review: null,
      }),
      createReview: vi.fn().mockResolvedValue({ data: { id: "review-1" }, etag: '"review:1"' }),
    } as unknown as AccountApi;
    const user = userEvent.setup();
    renderWithAccount(<ReviewForm locale="en" productId="product-1" />, { accountApi });

    await screen.findByRole("heading", { name: "Write a verified review" });
    await user.click(screen.getByRole("button", { name: "Choose 5 out of 5 stars" }));
    await user.type(
      screen.getByLabelText("Your review"),
      "Excellent battery life and dependable charging during travel.",
    );
    await user.click(screen.getByRole("button", { name: "Submit for review" }));

    await waitFor(() => expect(accountApi.createReview).toHaveBeenCalled());
    expect(accountApi.createReview).toHaveBeenCalledWith(
      expect.objectContaining({ product_id: "product-1", rating: 5, photos: [] }),
      expect.stringMatching(/^[0-9a-f-]{36}$/),
      "en",
    );
    expect(replace).toHaveBeenCalledWith("/en/account/reviews");
  });

  it("reuses the persisted photo-signing key after an ambiguous 5xx and remount", async () => {
    const accountApi = reviewUploadApi();
    const signReviewPhoto = vi
      .mocked(accountApi.signReviewPhoto)
      .mockReset()
      .mockRejectedValueOnce(
        new AccountError("unknown", { status: 503, code: "SERVICE_UNAVAILABLE" }),
      )
      .mockResolvedValueOnce({
        upload_id: "upload-1",
        provider: "cloudinary",
        upload_url: "https://storage.example/upload",
        upload_method: "POST",
        fields: { signature: "signed" },
        expires_at: "2026-11-07T00:00:00Z",
      });
    const file = new File(["photo"], "retry.webp", {
      type: "image/webp",
      lastModified: 1_700_000_000_000,
    });
    const first = renderWithAccount(<ReviewPhotoUploader onChange={vi.fn()} photos={[]} />, {
      accountApi,
    });
    fireEvent.change(first.container.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });
    await screen.findByRole("alert");
    first.unmount();

    const second = renderWithAccount(<ReviewPhotoUploader onChange={vi.fn()} photos={[]} />, {
      accountApi,
    });
    fireEvent.change(second.container.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });
    await waitFor(() => expect(signReviewPhoto).toHaveBeenCalledTimes(2));
    expect(signReviewPhoto.mock.calls[1]![1]).toBe(signReviewPhoto.mock.calls[0]![1]);
  });

  it("cancels an owned photo on explicit form cancellation", async () => {
    const accountApi = reviewUploadApi();
    const user = userEvent.setup();
    const { container } = renderWithAccount(<ReviewForm locale="en" productId="product-1" />, {
      accountApi,
    });
    await screen.findByRole("heading", { name: "Write a verified review" });
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [new File(["photo"], "review.webp", { type: "image/webp" })] },
    });
    await screen.findByAltText("Review photo preview");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(accountApi.cancelReviewPhoto).toHaveBeenCalledWith("upload-1"));
    expect(back).toHaveBeenCalled();
  });

  it("reconciles an abandoned owned upload on the next form mount", async () => {
    const accountApi = reviewUploadApi();
    const first = renderWithAccount(<ReviewForm locale="en" productId="product-1" />, {
      accountApi,
    });
    await screen.findByRole("heading", { name: "Write a verified review" });
    fireEvent.change(first.container.querySelector('input[type="file"]')!, {
      target: { files: [new File(["photo"], "review.webp", { type: "image/webp" })] },
    });
    await screen.findByAltText("Review photo preview");
    first.unmount();

    renderWithAccount(<ReviewForm locale="en" productId="product-1" />, { accountApi });
    await waitFor(() => expect(accountApi.cancelReviewPhoto).toHaveBeenCalledWith("upload-1"));
  });
});

function reviewUploadApi(): AccountApi {
  return {
    reviewEligibility: vi.fn().mockResolvedValue({
      product_id: "product-1",
      eligible: true,
      reason: "eligible",
      existing_review: null,
    }),
    signReviewPhoto: vi.fn().mockResolvedValue({
      upload_id: "upload-1",
      provider: "cloudinary",
      upload_url: "https://storage.example/upload",
      upload_method: "POST",
      fields: { signature: "signed" },
      expires_at: "2026-11-07T00:00:00Z",
    }),
    uploadReviewPhoto: vi.fn().mockResolvedValue({
      public_id: "review/upload-1",
      provider_asset_id: "asset-1",
      byte_size: 5,
      format: "webp",
      width: 100,
      height: 100,
      signature: "verified",
    }),
    completeReviewPhoto: vi.fn().mockResolvedValue({
      upload_id: "upload-1",
      state: "ready",
      preview_url: "https://res.cloudinary.com/demo/review.webp",
    }),
    cancelReviewPhoto: vi.fn().mockResolvedValue(undefined),
  } as unknown as AccountApi;
}
