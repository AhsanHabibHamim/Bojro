import { describe, expect, it } from "vitest";

import { buildWhatsAppHref, whatsappDigits } from "./whatsapp";

describe("WhatsApp links", () => {
  it("normalizes a Bangladesh number to a digits-only wa.me path", () => {
    expect(whatsappDigits("+880 (1712) 345-678")).toBe("8801712345678");
    expect(whatsappDigits("০১৭১২-৩৪৫৬৭৮")).toBe("8801712345678");
  });

  it("uses only the configured localized message", () => {
    const href = buildWhatsAppHref({
      enabled: true,
      phone: "01712345678",
      message: "Configured support message",
    });
    expect(href).toBe("https://wa.me/8801712345678?text=Configured%20support%20message");
    expect(href).not.toMatch(/transcript|order|phone=/i);
  });

  it("rejects disabled or invalid configurations", () => {
    expect(buildWhatsAppHref({ enabled: false, phone: "01712345678", message: "Hi" })).toBeNull();
    expect(buildWhatsAppHref({ enabled: true, phone: "123", message: "Hi" })).toBeNull();
  });
});
