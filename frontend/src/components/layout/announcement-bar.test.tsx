import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import bnMessages from "@/messages/bn.json";
import enMessages from "@/messages/en.json";

import { AnnouncementBar } from "./announcement-bar";

describe("AnnouncementBar", () => {
  it.each([
    ["bn", bnMessages, "ফ্রি ডেলিভারি ৳১৫০০+ অর্ডারে ⚡"],
    ["en", enMessages, "Free delivery on orders ৳1,500+ ⚡"],
  ] as const)("renders the localized offer for %s", (locale, messages, offer) => {
    render(
      <NextIntlClientProvider locale={locale} messages={messages}>
        <AnnouncementBar />
      </NextIntlClientProvider>,
    );

    expect(screen.getByText(offer)).toBeVisible();
  });
});
