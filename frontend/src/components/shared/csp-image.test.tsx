import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CspImage } from "./csp-image";

describe("CSP-safe optimized images", () => {
  it("keeps optimizer attributes and fill geometry without inline style attributes", () => {
    render(
      <div className="relative size-40">
        <CspImage alt="Product" fill sizes="10rem" src="/logo.png" />
      </div>,
    );
    const image = screen.getByRole("img", { name: "Product" });
    expect(image).not.toHaveAttribute("style");
    expect(image).toHaveClass("absolute", "inset-0", "size-full");
    expect(image).toHaveAttribute("srcset");
    expect(image).toHaveAttribute("sizes", "10rem");
  });
});
