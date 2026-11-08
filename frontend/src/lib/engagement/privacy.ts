import type { AnalyticsRouteName, AssistantAction, AssistantCitation } from "./types";

const emailPattern = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i;
const bdPhonePattern = /(?:\+?880|00880)?0?1[3-9]\d{8}/;
const orderPattern = /\bBJ[-\s]?\d{4}[-\s]?\d{6}\b/i;

export function containsSensitiveChatInput(value: string): boolean {
  const compact = value.replace(/[\s()-]/g, "");
  return emailPattern.test(value) || bdPhonePattern.test(compact) || orderPattern.test(value);
}

export function redactPotentialPii(value: string): string {
  return value
    .replace(new RegExp(emailPattern.source, "gi"), "[redacted]")
    .replace(/(?:\+?880|00880)?0?1[3-9][\d\s()-]{7,12}\d/g, "[redacted]")
    .replace(new RegExp(orderPattern.source, "gi"), "[redacted]")
    .slice(0, 4_000);
}

export function enforceAssistantIdentity(value: string, locale: "bn" | "en"): string {
  const redacted = redactPotentialPii(value);
  if (
    /\b(?:i am|i'm|im)\s+(?:a\s+)?(?:real\s+)?human\b/i.test(redacted) ||
    /আমি\s+(?:একজন\s+)?মানুষ/.test(redacted)
  ) {
    return locale === "bn"
      ? "আমি বজ্রের এআই সহায়ক, কোনো মানুষ নই। এই তথ্য নিশ্চিতভাবে যাচাই করতে হোয়াটসঅ্যাপ ব্যবহার করুন।"
      : "I am Bojro's AI assistant, not a person. Use WhatsApp to verify this information.";
  }
  return redacted;
}

export function isAssistantIdentityQuestion(value: string): boolean {
  return (
    /\b(?:are|r)\s+(?:you|u)\s+(?:an?\s+)?(?:ai|bot|human|person)\b/i.test(value) ||
    /\bwhat\s+are\s+you\b/i.test(value) ||
    /(?:তুমি|আপনি)\s+(?:কি|কী)\s+(?:এআই|মানুষ|বট)/.test(value)
  );
}

export function stripRepeatedAssistantDisclosure(
  value: string,
  disclosures: Array<string | null | undefined>,
): string {
  const content = value.trim();
  for (const disclosure of disclosures) {
    const prefix = disclosure?.trim();
    if (!prefix || !content.startsWith(prefix)) continue;
    const answer = content
      .slice(prefix.length)
      .replace(/^\s*[:\-–—]?\s*/, "")
      .trim();
    return answer || content;
  }
  return content;
}

export function safeAnalyticsRouteName(pathname: string): AnalyticsRouteName {
  const path = pathname.split("?", 1)[0]?.replace(/^\/(bn|en)(?=\/|$)/, "") || "/";
  if (path === "/") return "home";
  if (/^\/(?:shop|search|categories|category\/[^/]+)\/?$/.test(path)) return "catalog";
  if (/^\/product\/[^/]+\/?$/.test(path)) return "product_detail";
  if (path === "/cart") return "cart";
  if (path === "/checkout") return "checkout";
  if (/^\/order-success\/[^/]+\/?$/.test(path)) return "order_success";
  if (/^\/newsletter\/(?:confirm|unsubscribe)\/?$/.test(path)) return "newsletter_result";
  if (/^\/account(?:\/|$)/.test(path)) return "account";
  return "other";
}

export function safeAssistantHref(href: string | null, locale: "bn" | "en"): string | null {
  if (!href) return null;
  let url: URL;
  try {
    url = new URL(href, "https://bojro.invalid");
  } catch {
    return null;
  }
  if (url.origin !== "https://bojro.invalid" || url.search || url.hash) return null;
  let path = url.pathname.replace(/^\/(bn|en)(?=\/|$)/, "");
  if (path.startsWith("/products/")) path = path.replace("/products/", "/product/");
  if (
    !/^\/(?:product\/[a-z0-9]+(?:-[a-z0-9]+)*|help|return-refund|privacy|terms|warranty)\/?$/.test(
      path,
    )
  ) {
    return null;
  }
  return `/${locale}${path}`;
}

export function sanitizeCitation(value: AssistantCitation, locale: "bn" | "en"): AssistantCitation {
  return {
    id: String(value.id).slice(0, 100),
    type: ["product", "policy", "order_status"].includes(value.type) ? value.type : "policy",
    label: redactPotentialPii(String(value.label)).slice(0, 160),
    href: safeAssistantHref(value.href, locale),
  };
}

export function sanitizeAction(value: AssistantAction, locale: "bn" | "en"): AssistantAction {
  const allowed = ["view_product", "view_policy", "verify_order", "whatsapp_handoff"];
  const type = allowed.includes(value.type) ? value.type : "whatsapp_handoff";
  return {
    type,
    label: redactPotentialPii(String(value.label)).slice(0, 120),
    href:
      type === "view_product" || type === "view_policy"
        ? safeAssistantHref(value.href, locale)
        : null,
  };
}
