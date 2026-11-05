import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Logo } from "./logo";

describe("Logo", () => {
  it("renders the centralized wordmark with an accessible name and stable dimensions", () => {
    render(<Logo label="Bojro home" />);

    const logo = screen.getByRole("img", { name: "Bojro home" });
    expect(logo).toHaveAttribute("src", "/logo.png");
    expect(logo).toHaveAttribute("width", "176");
    expect(logo).toHaveAttribute("height", "62");
  });

  it("uses the same component for the compact brand mark", () => {
    render(<Logo label="Bojro mark" variant="icon" />);

    expect(screen.getByRole("img", { name: "Bojro mark" })).toHaveAttribute("src", "/icon.png");
  });
});
