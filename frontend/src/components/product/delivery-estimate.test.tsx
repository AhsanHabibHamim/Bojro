import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const { deliveryEstimate } = vi.hoisted(() => ({ deliveryEstimate: vi.fn() }));
vi.mock("@/lib/api/browser", () => ({ browserCatalogApi: { deliveryEstimate } }));

import { DeliveryEstimate } from "./delivery-estimate";

const labels = {
  title: "Delivery",
  select: "Select district",
  loading: "Loading estimate",
  error: "Estimate error",
  days: "days",
  fee: "Fee",
};
const districts = [{ id: "district-1", slug: "dhaka", name: "Dhaka" }];

describe("DeliveryEstimate", () => {
  it("hides the previous variant estimate immediately when the variant changes", async () => {
    deliveryEstimate.mockResolvedValueOnce({
      district: "dhaka",
      district_name: "Dhaka",
      minimum_days: 1,
      maximum_days: 2,
      shipping_fee: 9_000,
      currency: "BDT",
      message: null,
    });
    deliveryEstimate.mockReturnValueOnce(new Promise(() => undefined));
    const user = userEvent.setup();
    const { rerender } = render(
      <DeliveryEstimate districts={districts} labels={labels} locale="en" variantId="variant-1" />,
    );

    await user.selectOptions(screen.getByLabelText("Select district"), "district-1");
    expect(await screen.findByText("৳90")).toBeVisible();

    rerender(
      <DeliveryEstimate districts={districts} labels={labels} locale="en" variantId="variant-2" />,
    );
    expect(screen.queryByText("৳90")).not.toBeInTheDocument();
    expect(screen.getByText("Loading estimate")).toBeVisible();
  });
});
