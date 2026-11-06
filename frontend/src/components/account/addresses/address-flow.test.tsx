import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AccountApi } from "@/lib/account/client";
import { AccountError } from "@/lib/account/client";
import type { CommerceApi } from "@/lib/commerce/client";
import { createFakeCommerceApi } from "@/test/render-commerce";
import { renderWithAccount } from "@/test/render-account";

import { AddressForm } from "./address-form";
import { AddressList } from "./address-list";

const replace = vi.fn();
const back = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, back, push: vi.fn() }),
}));

const baseAddress = {
  id: "address-1",
  label: "Home",
  recipient: "Asha",
  phone: "+8801700000000",
  division: { id: "division-1", code: "30", name: "Dhaka", name_bn: "ঢাকা", name_en: "Dhaka" },
  district: { id: "district-1", code: "47", name: "Dhaka", name_bn: "ঢাকা", name_en: "Dhaka" },
  upazila: {
    id: "upazila-1",
    code: "123",
    name: "Dhanmondi",
    name_bn: "ধানমন্ডি",
    name_en: "Dhanmondi",
  },
  address_line: "12 Test Road",
  is_default: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  revision: 1,
};

describe("address account flows", () => {
  beforeEach(() => {
    replace.mockReset();
    back.mockReset();
  });

  it("resets dependent district and upazila selections when division changes", async () => {
    const commerceApi = createFakeCommerceApi({
      divisions: vi.fn().mockResolvedValue([
        { id: "division-1", code: "30", name: "Dhaka", name_bn: "ঢাকা", name_en: "Dhaka" },
        {
          id: "division-2",
          code: "20",
          name: "Chattogram",
          name_bn: "চট্টগ্রাম",
          name_en: "Chattogram",
        },
      ]),
      districts: vi.fn(async (divisionId: string) => [
        {
          id: `district-${divisionId}`,
          code: "1",
          name: `District ${divisionId}`,
          name_bn: "জেলা",
          name_en: "District",
        },
      ]),
      upazilas: vi.fn().mockResolvedValue([
        {
          id: "upazila-1",
          code: "1",
          name: "Dhanmondi",
          name_bn: "ধানমন্ডি",
          name_en: "Dhanmondi",
        },
      ]),
    }) as CommerceApi;
    const accountApi = {} as AccountApi;
    const user = userEvent.setup();
    renderWithAccount(<AddressForm locale="en" />, { accountApi, commerceApi });

    await user.selectOptions(await screen.findByLabelText("Division"), "division-1");
    await user.selectOptions(screen.getByLabelText("District"), "district-division-1");
    await user.selectOptions(screen.getByLabelText("Upazila"), "upazila-1");
    expect(screen.getByLabelText("Upazila")).toHaveValue("upazila-1");

    await user.selectOptions(screen.getByLabelText("Division"), "division-2");
    expect(screen.getByLabelText("District")).toHaveValue("");
    expect(screen.getByLabelText("Upazila")).toHaveValue("");
    expect(screen.getByLabelText("Upazila")).toBeDisabled();
  });

  it("sets a new default and surfaces stale delete revisions", async () => {
    const accountApi = {
      addresses: vi
        .fn()
        .mockResolvedValue([
          baseAddress,
          { ...baseAddress, id: "address-2", label: "Office", is_default: false },
        ]),
      setDefaultAddress: vi
        .fn()
        .mockResolvedValue({ ...baseAddress, id: "address-2", is_default: true }),
      address: vi.fn().mockResolvedValue({ data: baseAddress, etag: '"address:1"' }),
      deleteAddress: vi
        .fn()
        .mockRejectedValue(new AccountError("stale", { status: 412, code: "PRECONDITION_FAILED" })),
    } as unknown as AccountApi;
    const user = userEvent.setup();
    renderWithAccount(<AddressList locale="en" />, { accountApi });

    await user.click(await screen.findByRole("button", { name: "Make default" }));
    expect(accountApi.setDefaultAddress).toHaveBeenCalledWith("address-2", "en");

    const deleteButtons = screen.getAllByRole("button", { name: "Delete" });
    await user.click(deleteButtons[0]!);
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(screen.getByText(/changed on another screen/i)).toBeVisible());
    expect(accountApi.deleteAddress).toHaveBeenCalledWith("address-1", '"address:1"');
  });

  it("does not delete when the fetched revision differs from the displayed card", async () => {
    const accountApi = {
      addresses: vi.fn().mockResolvedValue([baseAddress]),
      address: vi.fn().mockResolvedValue({
        data: { ...baseAddress, recipient: "Changed elsewhere", revision: 2 },
        etag: '"address:2"',
      }),
      deleteAddress: vi.fn(),
    } as unknown as AccountApi;
    const user = userEvent.setup();
    renderWithAccount(<AddressList locale="en" />, { accountApi });

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(screen.getByText(/changed on another screen/i)).toBeVisible());
    expect(accountApi.deleteAddress).not.toHaveBeenCalled();
  });
});
