import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/shop",
  useSearchParams: () => new URLSearchParams("q=serum&sort=price_asc"),
}));

import { LocaleSwitch } from "./locale-switch";

describe("LocaleSwitch", () => {
  it("preserves the current path and query while changing locale", () => {
    window.history.replaceState({}, "", "/en/shop?q=serum&sort=price_asc#reviews");
    render(<LocaleSwitch label="বাংলা" locale="en" shortLabel="বাংলা" />);

    expect(screen.getByRole("link", { name: "বাংলা" })).toHaveAttribute(
      "href",
      "/bn/shop?q=serum&sort=price_asc#reviews",
    );
  });
});
