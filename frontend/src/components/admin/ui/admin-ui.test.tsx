import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";

import enMessages from "@/messages/en.json";

import { AdminDialog } from "./dialog";
import { AdminField, adminInputClass, fieldErrorProps } from "./form-field";

describe("admin accessible primitives", () => {
  it("associates field errors with invalid controls", () => {
    render(
      <AdminField error="Required" htmlFor="name" label="Name" required>
        <input {...fieldErrorProps("name", "Required")} className={adminInputClass} id="name" />
      </AdminField>,
    );
    const input = screen.getByLabelText(/Name/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Required");
  });

  it("closes on Escape and restores focus to the opener", () => {
    function Example() {
      const [open, setOpen] = useState(false);
      const opener = useRef<HTMLButtonElement>(null);
      return (
        <NextIntlClientProvider locale="en" messages={enMessages}>
          <button ref={opener} onClick={() => setOpen(true)} type="button">
            Open
          </button>
          <AdminDialog closeLabel="Close" onClose={() => setOpen(false)} open={open} title="Dialog">
            <button type="button">Inside</button>
          </AdminDialog>
        </NextIntlClientProvider>
      );
    }
    render(<Example />);
    const opener = screen.getByRole("button", { name: "Open" });
    opener.focus();
    fireEvent.click(opener);
    const dialog = screen.getByRole("dialog");
    fireEvent(dialog, new Event("cancel", { bubbles: true, cancelable: true }));
    expect(opener).toHaveFocus();
  });
});
