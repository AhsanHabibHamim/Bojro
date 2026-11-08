import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { EngagementApi } from "@/lib/engagement/client";

import { NewsletterForm } from "./newsletter-form";

const labels = {
  emailLabel: "Email",
  emailPlaceholder: "you@example.com",
  consent: "Email me news",
  subscribe: "Subscribe",
  pending: "Submitting",
  success: "Check your inbox",
  error: "Try again",
};

describe("NewsletterForm", () => {
  it("submits an explicit double-opt-in request and stays idle while unchecked", async () => {
    const user = userEvent.setup();
    const subscribeNewsletter = vi.fn().mockResolvedValue({ accepted: true });
    const api = { subscribeNewsletter } as unknown as EngagementApi;
    render(<NewsletterForm api={api} labels={labels} locale="en" policyVersion="policy-7" />);

    await user.type(screen.getByLabelText("Email"), "reader@example.com");
    expect(screen.getByRole("button", { name: "Subscribe" })).toBeDisabled();
    expect(subscribeNewsletter).not.toHaveBeenCalled();
    await user.click(screen.getByText("Email me news"));
    await user.click(screen.getByRole("button", { name: "Subscribe" }));

    expect(subscribeNewsletter).toHaveBeenCalledWith({
      email: "reader@example.com",
      locale: "en",
      consent: true,
      policy_version: "policy-7",
      source: "footer",
    });
    expect(await screen.findByText("Check your inbox")).toBeVisible();
  });

  it("uses the same non-enumerating error for failures", async () => {
    const user = userEvent.setup();
    const api = {
      subscribeNewsletter: vi.fn().mockRejectedValue(new Error("address exists")),
    } as unknown as EngagementApi;
    render(<NewsletterForm api={api} labels={labels} locale="en" policyVersion="policy-7" />);
    await user.type(screen.getByLabelText("Email"), "known@example.com");
    await user.click(screen.getByText("Email me news"));
    await user.click(screen.getByRole("button", { name: "Subscribe" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Try again");
    expect(screen.queryByText(/exists/i)).not.toBeInTheDocument();
  });
});
