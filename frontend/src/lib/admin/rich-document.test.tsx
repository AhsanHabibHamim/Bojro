import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RichDocumentRenderer } from "@/components/content/rich-document-renderer";

import { parseRichDocument, parseRichDocumentSource } from "./rich-document";

describe("safe rich documents", () => {
  it("renders text as text and never creates arbitrary HTML", () => {
    const document = parseRichDocument({
      version: 1,
      type: "doc",
      content: [
        { type: "paragraph", content: [{ type: "text", text: "<script>alert(1)</script>" }] },
      ],
    });
    const { container } = render(<RichDocumentRenderer document={document} />);
    expect(screen.getByText("<script>alert(1)</script>")).toBeVisible();
    expect(container.querySelector("script")).toBeNull();
  });

  it("rejects unsupported nodes and javascript links", () => {
    expect(() =>
      parseRichDocumentSource(
        JSON.stringify({
          version: 1,
          type: "doc",
          content: [
            {
              type: "paragraph",
              content: [
                {
                  type: "text",
                  text: "bad",
                  marks: [{ type: "link", attrs: { href: "javascript:alert(1)" } }],
                },
              ],
            },
          ],
        }),
      ),
    ).toThrow(/Unsafe link/);
    expect(() =>
      parseRichDocument({ version: 1, type: "doc", content: [{ type: "html", html: "<b>x</b>" }] }),
    ).toThrow(/Unsupported block/);
  });

  it("renders embedded media only from an explicitly resolved HTTPS asset map", () => {
    const document = parseRichDocument({
      version: 1,
      type: "doc",
      content: [
        { type: "image", attrs: { media_asset_id: "asset-1", alt: "Safe product detail" } },
      ],
    });
    const { container, rerender } = render(<RichDocumentRenderer document={document} />);
    expect(container.querySelector("img")).toBeNull();

    rerender(
      <RichDocumentRenderer
        document={document}
        media={{ "asset-1": { url: "https://cdn.example.test/safe.webp" } }}
      />,
    );
    expect(screen.getByRole("img", { name: "Safe product detail" })).toBeVisible();
  });
});
