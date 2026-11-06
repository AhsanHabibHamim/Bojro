import { describe, expect, it } from "vitest";

import {
  clearSubmissionKey,
  digestOrderRequest,
  isValidBangladeshPhone,
  normalizeBangladeshPhone,
  readSubmissionKey,
  submissionKeyForDigest,
  writeSubmissionKey,
} from "./checkout";
import type { PlaceOrderRequest } from "./types";

const request: PlaceOrderRequest = {
  quote_token: "quote-1",
  customer: { name: "Asha", phone: "01700000000", email: null },
  shipping_address: {
    recipient: "Asha",
    phone: "01700000000",
    division_id: "division-1",
    district_id: "district-1",
    upazila_id: "upazila-1",
    address_line: "12 Test Road",
  },
  notes: null,
  payment_method: "cod",
};

describe("checkout helpers", () => {
  it("normalizes and validates Bangladesh mobile numbers", () => {
    expect(normalizeBangladeshPhone("+880 1700-000000")).toBe("+8801700000000");
    expect(normalizeBangladeshPhone("00880 (১৭) ০০০.০০-০০০")).toBe("+8801700000000");
    expect(normalizeBangladeshPhone("৮৮০১৭০০০০০০০০")).toBe("+8801700000000");
    expect(isValidBangladeshPhone("01700000000")).toBe(true);
    expect(isValidBangladeshPhone("০০৮৮০-১৭-০০০০০০০০")).toBe(true);
    expect(isValidBangladeshPhone("01200000000")).toBe(false);
    expect(isValidBangladeshPhone("0170000000")).toBe(false);
  });

  it("reuses one key for the same payload digest and resets it after an edit", async () => {
    let counter = 0;
    const createKey = () => `key-${++counter}`;
    const digest = await digestOrderRequest(request);
    const editedDigest = await digestOrderRequest({ ...request, notes: "Call first" });
    const first = submissionKeyForDigest(null, digest, createKey);
    const retry = submissionKeyForDigest(first, digest, createKey);
    const edited = submissionKeyForDigest(first, editedDigest, createKey);

    expect(retry.key).toBe(first.key);
    expect(edited.key).not.toBe(first.key);
    expect(first.digest).toMatch(/^[a-f0-9]{64}$/);
    expect(counter).toBe(2);
  });

  it("restores only the UUID and non-PII digest after a reload", async () => {
    const digest = await digestOrderRequest(request);
    const value = {
      digest,
      key: "123e4567-e89b-42d3-a456-426614174000",
    };
    writeSubmissionKey(value);

    expect(readSubmissionKey()).toEqual(value);
    expect(sessionStorage.getItem("bojro:checkout-submission:v1")).not.toContain("Asha");
    clearSubmissionKey();
    expect(readSubmissionKey()).toBeNull();
  });
});
