import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EngagementApi } from "@/lib/engagement/client";
import { resetAnalyticsAdaptersForTests } from "@/lib/engagement/analytics-adapters";
import type { StorefrontShell } from "@/lib/catalog/types";

import { EngagementProvider, type ConsentLabels } from "./engagement-provider";

vi.mock("next/navigation", () => ({ usePathname: () => "/en" }));

const labels: ConsentLabels = {
  title: "Your privacy",
  description: "Optional tools stay off.",
  accept: "Accept optional cookies",
  reject: "Reject optional cookies",
  manage: "Choose settings",
  modalTitle: "Privacy settings",
  modalDescription: "Choose separately.",
  necessaryTitle: "Necessary",
  necessaryDescription: "Required.",
  analyticsTitle: "Analytics",
  analyticsDescription: "Store measurement.",
  advertisingTitle: "Advertising",
  advertisingDescription: "Ad measurement.",
  save: "Save",
  saving: "Saving",
  close: "Close",
  error: "Could not save",
};

const shell = {
  analytics: {
    google_analytics_id: "G-ABC12345",
    meta_pixel_id: "1234567890",
  },
  engagement: {
    consent_policy_version: "2026-11-07-v1",
  },
} as StorefrontShell;

function consentResponse(analytics: boolean, advertising: boolean) {
  return {
    policy_version: "2026-11-07-v1",
    analytics,
    advertising,
    updated_at: "2026-11-07T12:00:00Z",
  };
}

describe("EngagementProvider", () => {
  beforeEach(() => {
    document.cookie = "bojro_consent=; Path=/; Max-Age=0";
    resetAnalyticsAdaptersForTests();
  });

  it("makes accept and reject equal-weight and records selected consent before loading providers", async () => {
    const user = userEvent.setup();
    const updateConsent = vi.fn().mockResolvedValue(consentResponse(true, true));
    const api = { updateConsent } as unknown as EngagementApi;
    render(
      <EngagementProvider
        api={api}
        labels={labels}
        locale="en"
        nonce="nonce"
        reload={vi.fn()}
        shell={shell}
      >
        <div>Store</div>
      </EngagementProvider>,
    );
    const accept = screen.getByRole("button", { name: "Accept optional cookies" });
    const reject = screen.getByRole("button", { name: "Reject optional cookies" });
    expect(accept).toHaveClass("min-h-12", "border-2");
    expect(reject).toHaveClass("min-h-12", "border-2");
    expect(
      document.querySelectorAll('script[src*="googletagmanager"], script[src*="facebook"]'),
    ).toHaveLength(0);
    await user.click(accept);
    expect(updateConsent).toHaveBeenCalledWith({
      policy_version: "2026-11-07-v1",
      locale: "en",
      analytics: true,
      advertising: true,
    });
    expect(document.cookie).toContain("bojro_consent=");
    expect(decodeURIComponent(document.cookie)).not.toMatch(/email|phone|user_id/i);
    await waitFor(() => {
      expect(document.querySelector('script[src*="googletagmanager"]')).toBeTruthy();
      expect(document.querySelector('script[src*="facebook.net"]')).toBeTruthy();
    });
  });

  it("loads only a granularly selected provider and makes the dialog modal", async () => {
    const user = userEvent.setup();
    const updateConsent = vi.fn().mockResolvedValue(consentResponse(true, false));
    render(
      <EngagementProvider
        api={{ updateConsent } as unknown as EngagementApi}
        labels={labels}
        locale="en"
        nonce="nonce"
        reload={vi.fn()}
        shell={shell}
      >
        <button type="button">Store action</button>
      </EngagementProvider>,
    );

    expect(
      document.querySelectorAll('script[src*="googletagmanager"], script[src*="facebook"]'),
    ).toHaveLength(0);
    const opener = screen.getByRole("button", { name: "Choose settings" });
    await user.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Privacy settings" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Store action" }).closest("[inert]")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Save" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(opener).toHaveFocus());
    expect(document.querySelector("[inert]")).toBeNull();
    await user.click(opener);

    await user.click(screen.getByRole("checkbox", { name: /Analytics/ }));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(document.querySelector("[inert]")).toBeNull();
    await waitFor(() => {
      expect(document.querySelector('script[src*="googletagmanager"]')).toBeTruthy();
      expect(document.querySelector('script[src*="facebook.net"]')).toBeNull();
    });
  });
});
