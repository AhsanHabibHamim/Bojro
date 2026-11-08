import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import { EngagementError, type EngagementApi } from "@/lib/engagement/client";
import enMessages from "@/messages/en.json";

import { PreferencesPage } from "./preferences-page";

describe("PreferencesPage", () => {
  it("loads an ETag and sends If-Match through the engagement client", async () => {
    const user = userEvent.setup();
    const preferences = {
      locale: "en" as const,
      order_email: true,
      order_sms: false,
      abandoned_cart_email: false,
      abandoned_cart_sms: false,
      revision: 3,
      updated_at: "2026-11-07T12:00:00Z",
    };
    const updateCommunicationPreferences = vi.fn().mockResolvedValue({
      data: { ...preferences, abandoned_cart_email: true, revision: 4 },
      etag: '"prefs-4"',
    });
    const api = {
      communicationPreferences: vi.fn().mockResolvedValue({ data: preferences, etag: '"prefs-3"' }),
      updateCommunicationPreferences,
    } as unknown as EngagementApi;
    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <PreferencesPage api={api} />
      </NextIntlClientProvider>,
    );

    const cartEmail = (await screen.findAllByLabelText("Email"))[1]!;
    expect(cartEmail).not.toBeChecked();
    await user.click(cartEmail);
    await user.click(screen.getByRole("button", { name: "Save choices" }));
    expect(updateCommunicationPreferences).toHaveBeenCalledWith(
      expect.objectContaining({ abandoned_cart_email: true }),
      '"prefs-3"',
    );
    expect(await screen.findByText("Your communication choices were saved.")).toBeVisible();
  });

  it("surfaces a stale ETag and reloads instead of overwriting newer preferences", async () => {
    const user = userEvent.setup();
    const preferences = {
      locale: "en" as const,
      order_email: true,
      order_sms: false,
      abandoned_cart_email: false,
      abandoned_cart_sms: false,
      revision: 3,
    };
    const communicationPreferences = vi
      .fn()
      .mockResolvedValueOnce({ data: preferences, etag: '"prefs-3"' })
      .mockResolvedValueOnce({
        data: { ...preferences, order_sms: true, revision: 4 },
        etag: '"prefs-4"',
      });
    const updateCommunicationPreferences = vi
      .fn()
      .mockRejectedValue(
        new EngagementError("stale", { status: 412, code: "PRECONDITION_FAILED" }),
      );
    const api = {
      communicationPreferences,
      updateCommunicationPreferences,
    } as unknown as EngagementApi;
    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <PreferencesPage api={api} />
      </NextIntlClientProvider>,
    );

    const orderSms = (await screen.findAllByLabelText("SMS"))[0]!;
    await user.click(orderSms);
    await user.click(screen.getByRole("button", { name: "Save choices" }));
    expect(
      await screen.findByText(
        "These choices changed elsewhere. Reload the latest version before saving.",
      ),
    ).toBeVisible();
    expect(updateCommunicationPreferences).toHaveBeenCalledWith(
      expect.objectContaining({ order_sms: true }),
      '"prefs-3"',
    );

    await user.click(screen.getByRole("button", { name: "Reload latest choices" }));
    expect(await screen.findByRole("checkbox", { name: "SMS", checked: true })).toBeVisible();
    expect(communicationPreferences).toHaveBeenCalledTimes(2);
  });
});
