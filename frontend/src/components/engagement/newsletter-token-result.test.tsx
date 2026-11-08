import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { EngagementApi } from "@/lib/engagement/client";

import { NewsletterTokenResult, type NewsletterTokenLabels } from "./newsletter-token-result";

const labels: NewsletterTokenLabels = {
  loading: "Checking",
  confirmTitle: "Newsletter confirmation",
  unsubscribeTitle: "Newsletter preferences",
  confirmed: "Confirmed",
  unsubscribed: "Unsubscribed",
  alreadyUnsubscribed: "Already unsubscribed",
  invalid: "Invalid",
  expired: "Expired",
  home: "Home",
};

describe("NewsletterTokenResult", () => {
  it("strips the token with replaceState before posting it", async () => {
    const token = "a".repeat(40);
    window.history.replaceState(null, "", `/en/newsletter/confirm?source=email#token=${token}`);
    const confirmNewsletter = vi.fn().mockImplementation(async (received: string) => {
      expect(received).toBe(token);
      expect(window.location.search).toBe("?source=email");
      expect(window.location.hash).toBe("");
      return { result: "confirmed" as const };
    });
    render(
      <NewsletterTokenResult
        action="confirm"
        api={{ confirmNewsletter } as unknown as EngagementApi}
        labels={labels}
        locale="en"
      />,
    );
    expect(await screen.findByText("Confirmed")).toBeVisible();
    expect(window.location.href).not.toContain(token);
  });

  it("rejects query tokens after stripping them without a mutation", async () => {
    const token = "b".repeat(40);
    window.history.replaceState(null, "", `/en/newsletter/confirm?token=${token}`);
    const confirmNewsletter = vi.fn();
    render(
      <NewsletterTokenResult
        action="confirm"
        api={{ confirmNewsletter } as unknown as EngagementApi}
        labels={labels}
        locale="en"
      />,
    );
    expect(await screen.findByText("Invalid")).toBeVisible();
    expect(confirmNewsletter).not.toHaveBeenCalled();
    expect(window.location.search).toBe("");
  });
});
