import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AccountApi } from "@/lib/account/client";
import { renderWithAccount } from "@/test/render-account";

import { ProfileForm } from "./profile-form";

function SessionName() {
  return <output aria-label="shared session name">{useCommerce().session?.user?.name}</output>;
}

describe("ProfileForm", () => {
  it("patches the shared session name after a successful profile update", async () => {
    const profile = {
      id: "user-1",
      name: "Asha",
      phone: "01700000000",
      email: null,
      role: "customer" as const,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      revision: 1,
    };
    const accountApi = {
      profile: vi.fn().mockResolvedValue({ data: profile, etag: '"profile:user-1:1"' }),
      updateProfile: vi.fn().mockResolvedValue({
        data: { ...profile, name: "Nila", revision: 2 },
        etag: '"profile:user-1:2"',
      }),
    } as unknown as AccountApi;
    const user = userEvent.setup();
    renderWithAccount(
      <>
        <SessionName />
        <ProfileForm />
      </>,
      { accountApi },
    );

    const input = await screen.findByLabelText("Full name");
    await user.clear(input);
    await user.type(input, "Nila");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(screen.getByLabelText("shared session name")).toHaveTextContent("Nila"),
    );
  });
});
