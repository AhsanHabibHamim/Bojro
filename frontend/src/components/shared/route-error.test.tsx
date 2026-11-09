import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RouteError } from "./route-error";

vi.mock("@/lib/monitoring/error-reporting", () => ({ captureClientError: vi.fn() }));

afterEach(() => {
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
});

describe("accessible localized route errors", () => {
  it("announces the English error, focuses its heading, and provides recovery", async () => {
    const reset = vi.fn();
    render(<RouteError error={new Error("failure")} locale="en" reset={reset} />);

    const alert = screen.getByRole("alert");
    const heading = screen.getByRole("heading", { level: 1 });
    expect(alert).toHaveAccessibleName("This page cannot be displayed right now");
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByRole("link", { name: "Return home" })).toHaveAttribute("href", "/en");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
  });

  it("switches to a Bangla offline status and prevents a futile retry", async () => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    render(
      <RouteError error={new Error("failure")} locale="bn" reset={vi.fn()} variant="commerce" />,
    );

    expect(await screen.findByRole("heading", { name: "আপনি অফলাইনে আছেন" })).toBeVisible();
    expect(screen.getByRole("button", { name: "আবার চেষ্টা করুন" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "হোমে ফিরুন" })).toHaveAttribute("href", "/bn");
  });
});
