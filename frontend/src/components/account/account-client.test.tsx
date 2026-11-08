import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CommerceError, type CommerceApi } from "@/lib/commerce/client";
import { sessionFixture } from "@/test/commerce-fixtures";
import { createFakeCommerceApi, renderWithCommerce } from "@/test/render-commerce";

import { AccountClient, type AccountLabels } from "./account-client";

const labels: AccountLabels = {
  title: "Account",
  subtitle: "Sign in",
  loading: "Loading",
  signedIn: {
    title: "Signed in",
    description: "Active",
    phone: "Phone",
    email: "Email",
    cartAdjusted: "Cart adjusted",
    logout: "Sign out",
    loggingOut: "Signing out",
  },
  available: { title: "Available", description: "Sign in only" },
  otp: {
    tab: "Phone code",
    title: "Phone sign in",
    description: "Request code",
    phone: "Mobile number",
    name: "Name",
    nameOptional: "optional",
    request: "Request code",
    requesting: "Requesting",
    requestSuccess: "Accepted",
    code: "Code",
    devCode: "Development code",
    verify: "Verify",
    verifying: "Verifying",
    resend: "Resend",
    resendIn: "Resend in {seconds}",
    expiresIn: "Expires in {seconds}",
    invalidPhone: "Invalid phone",
    retryAfter: "Retry in {seconds}",
  },
  email: {
    tab: "Email",
    title: "Email sign in",
    description: "Existing account",
    address: "Email address",
    password: "Password",
    login: "Sign in",
    loggingIn: "Signing in",
  },
  security: "Secure",
  genericError: "Error",
};

describe("AccountClient", () => {
  it("allows the backend contract minimum one-character email password", async () => {
    const loginWithEmail = vi.fn().mockResolvedValue(
      sessionFixture({
        authenticated: true,
        user: { id: "user-1", name: "Asha", phone: null, email: "a@example.test" },
      }),
    );
    const api = createFakeCommerceApi({ loginWithEmail }) as CommerceApi;
    const user = userEvent.setup();
    renderWithCommerce(<AccountClient isDevelopment={false} labels={labels} />, { api });

    await user.click(screen.getByRole("button", { name: "Email" }));
    await user.type(screen.getByLabelText("Email address"), "a@example.test");
    await user.type(screen.getByLabelText("Password"), "x");
    expect(screen.getByLabelText("Password")).toHaveAttribute("minlength", "1");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() =>
      expect(loginWithEmail).toHaveBeenCalledWith({ email: "a@example.test", password: "x" }),
    );
  });

  it("honors OTP Retry-After with an absolute disabled deadline", async () => {
    const requestOtp = vi.fn().mockRejectedValue(
      new CommerceError("Rate limited", {
        status: 429,
        code: "RATE_LIMITED",
        retryAfterSeconds: 37,
      }),
    );
    const api = createFakeCommerceApi({ requestOtp }) as CommerceApi;
    const user = userEvent.setup();
    renderWithCommerce(<AccountClient isDevelopment={false} labels={labels} />, { api });

    await user.type(screen.getByLabelText("Mobile number"), "০১৭০০০০০০০০");
    await user.click(screen.getByRole("button", { name: "Request code" }));

    expect(requestOtp).toHaveBeenCalledWith({ phone: "+8801700000000", locale: "en" });
    expect(await screen.findByRole("button", { name: "Retry in 37" })).toBeDisabled();
  });
});
