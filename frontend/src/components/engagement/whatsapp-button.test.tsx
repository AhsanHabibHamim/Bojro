import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WhatsAppButton } from "./whatsapp-button";

describe("WhatsAppButton", () => {
  it("renders one accessible noopener link with only configured localized copy", () => {
    render(
      <WhatsAppButton
        label="Open Bojro on WhatsApp"
        settings={{
          enabled: true,
          phone: "+880 (1712) 345-678",
          message: "Configured localized support message",
        }}
      />,
    );
    const link = screen.getByRole("link", { name: "Open Bojro on WhatsApp" });
    expect(link).toHaveAttribute(
      "href",
      "https://wa.me/8801712345678?text=Configured%20localized%20support%20message",
    );
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link.getAttribute("href")).not.toMatch(/transcript|order|email|phone=/i);
  });
});
