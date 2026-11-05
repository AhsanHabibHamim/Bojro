import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";

import bnMessages from "@/messages/bn.json";
import enMessages from "@/messages/en.json";

import { Marquee } from "./marquee";

describe("Marquee", () => {
  it("renders the exact Bangla trust messages and hides the duplicate track", () => {
    render(
      <NextIntlClientProvider locale="bn" messages={bnMessages}>
        <Marquee />
      </NextIntlClientProvider>,
    );

    const region = screen.getByRole("region", { name: "বজ্রের কেনাকাটার সুবিধা" });
    expect(screen.getAllByText("১০০% অথেনটিক ⚡")).toHaveLength(2);
    expect(screen.getAllByText("ক্যাশ অন ডেলিভারি 🚚")).toHaveLength(2);
    expect(screen.getAllByText("ফাস্ট ডেলিভারি ⚡")).toHaveLength(2);
    expect(screen.getAllByText("ইজি রিটার্ন ↩")).toHaveLength(2);
    expect(region.querySelector('.marquee-group[aria-hidden="true"]')).toBeInTheDocument();
  });

  it("renders localized English trust messages", () => {
    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <Marquee />
      </NextIntlClientProvider>,
    );

    expect(screen.getAllByText("100% Authentic ⚡")).toHaveLength(2);
    expect(screen.getAllByText("Cash on Delivery 🚚")).toHaveLength(2);
    expect(screen.getAllByText("Fast Delivery ⚡")).toHaveLength(2);
    expect(screen.getAllByText("Easy Returns ↩")).toHaveLength(2);
  });
});
