import { describe, expect, it } from "vitest";

import bnMessages from "./bn.json";
import enMessages from "./en.json";

function collectLeafKeys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return [prefix];
  }

  return Object.entries(value).flatMap(([key, nestedValue]) =>
    collectLeafKeys(nestedValue, prefix ? `${prefix}.${key}` : key),
  );
}

function placeholders(message: string): string[] {
  const names = new Set<string>();
  let depth = 0;
  for (let index = 0; index < message.length; index += 1) {
    if (message[index] === "{") {
      if (depth === 0) {
        const match = message.slice(index + 1).match(/^([A-Za-z][A-Za-z0-9_]*)\s*[,}]/);
        if (match?.[1]) names.add(match[1]);
      }
      depth += 1;
    } else if (message[index] === "}") {
      depth = Math.max(0, depth - 1);
    }
  }
  return [...names].sort();
}

function collectMessages(value: unknown, prefix = ""): Record<string, string> {
  if (typeof value === "string") return { [prefix]: value };
  if (typeof value !== "object" || value === null || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, nestedValue]) =>
      Object.entries(collectMessages(nestedValue, prefix ? `${prefix}.${key}` : key)),
    ),
  );
}

describe("message catalogs", () => {
  it("keeps Bangla and English message coverage in sync", () => {
    expect(collectLeafKeys(bnMessages).sort()).toEqual(collectLeafKeys(enMessages).sort());
  });

  it("keeps ICU placeholder names in sync across locales", () => {
    const bn = collectMessages(bnMessages);
    const en = collectMessages(enMessages);
    for (const key of Object.keys(en)) {
      expect(placeholders(bn[key] ?? ""), key).toEqual(placeholders(en[key]!));
    }
  });

  it("keeps Phase 6 payment, refund, courier, and webhook UX translated", () => {
    expect(bnMessages.paymentReturn.states.unknown.title).not.toBe(
      enMessages.paymentReturn.states.unknown.title,
    );
    expect(bnMessages.checkout.payment.methods.bkash.description).not.toBe(
      enMessages.checkout.payment.methods.bkash.description,
    );
    expect(bnMessages.admin.orders.refund.submit).not.toBe(enMessages.admin.orders.refund.submit);
    expect(bnMessages.admin.webhooks.deadLetterDetail).not.toBe(
      enMessages.admin.webhooks.deadLetterDetail,
    );
  });
});
