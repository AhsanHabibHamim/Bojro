import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { EMPTY_RICH_DOCUMENT } from "@/lib/admin/rich-document";
import type { RichDocument } from "@/lib/admin/types";
import messages from "@/messages/en.json";

import { RichDocumentEditor } from "./rich-document-editor";

function Harness() {
  const [document, setDocument] = useState<RichDocument>(EMPTY_RICH_DOCUMENT);
  const [valid, setValid] = useState(true);
  return (
    <NextIntlClientProvider locale="en" messages={messages}>
      <RichDocumentEditor
        help="Structured document"
        id="document"
        invalidMessage="Invalid document"
        label="Document"
        onChange={setDocument}
        onValidityChange={setValid}
        previewLabel="Preview"
        value={document}
      />
      <button disabled={!valid} type="button">
        Save
      </button>
    </NextIntlClientProvider>
  );
}

describe("RichDocumentEditor validity", () => {
  it("blocks the parent submit state while visible JSON is invalid", () => {
    render(<Harness />);
    fireEvent.change(screen.getByLabelText(/Document/), { target: { value: "{" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByText("Invalid document")).toBeVisible();
  });
});
