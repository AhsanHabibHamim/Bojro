import type { RichDocument, RichNode, RichTextMark } from "./types";

const SAFE_LINK_PROTOCOLS = new Set(["http:", "https:", "mailto:", "tel:"]);
const MAX_NODES = 2_000;
const MAX_TEXT = 100_000;

export class RichDocumentError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RichDocumentError";
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function safeHref(value: unknown): string {
  if (typeof value !== "string" || value.length > 2_048)
    throw new RichDocumentError("Invalid link");
  if ((value.startsWith("/") && !value.startsWith("//")) || value.startsWith("#")) return value;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new RichDocumentError("Invalid link");
  }
  if (!SAFE_LINK_PROTOCOLS.has(url.protocol)) throw new RichDocumentError("Unsafe link");
  return value;
}

function parseMark(value: unknown): RichTextMark {
  if (
    !record(value) ||
    !["bold", "italic", "strike", "code", "link"].includes(String(value.type))
  ) {
    throw new RichDocumentError("Unsupported text mark");
  }
  if (value.type === "link") {
    const attrs = record(value.attrs) ? value.attrs : {};
    return { type: "link", attrs: { href: safeHref(attrs.href) } };
  }
  return { type: value.type as "bold" | "italic" | "strike" | "code" };
}

function parseNode(
  value: unknown,
  depth: number,
  counts: { nodes: number; text: number },
): RichNode {
  if (!record(value) || typeof value.type !== "string" || depth > 12) {
    throw new RichDocumentError("Invalid document node");
  }
  counts.nodes += 1;
  if (counts.nodes > MAX_NODES) throw new RichDocumentError("Document has too many nodes");
  if (value.type === "text") {
    if (typeof value.text !== "string") throw new RichDocumentError("Invalid text node");
    counts.text += value.text.length;
    if (counts.text > MAX_TEXT) throw new RichDocumentError("Document is too long");
    return {
      type: "text",
      text: value.text,
      ...(Array.isArray(value.marks) ? { marks: value.marks.map(parseMark) } : {}),
    };
  }
  if (value.type === "hardBreak") return { type: "hardBreak" };
  if (value.type === "image") {
    const attrs = record(value.attrs) ? value.attrs : {};
    if (typeof attrs.media_asset_id !== "string" || typeof attrs.alt !== "string") {
      throw new RichDocumentError("Invalid image");
    }
    return { type: "image", attrs: { media_asset_id: attrs.media_asset_id, alt: attrs.alt } };
  }
  const content = Array.isArray(value.content)
    ? value.content.map((node) => parseNode(node, depth + 1, counts))
    : [];
  if (value.type === "heading") {
    const attrs = record(value.attrs) ? value.attrs : {};
    if (attrs.level !== 2 && attrs.level !== 3 && attrs.level !== 4) {
      throw new RichDocumentError("Invalid heading level");
    }
    return { type: "heading", attrs: { level: attrs.level }, content };
  }
  if (["paragraph", "blockquote", "bulletList", "orderedList", "listItem"].includes(value.type)) {
    return {
      type: value.type as "paragraph" | "blockquote" | "bulletList" | "orderedList" | "listItem",
      content,
    };
  }
  throw new RichDocumentError("Unsupported block type");
}

export function parseRichDocument(value: unknown): RichDocument {
  if (
    !record(value) ||
    value.version !== 1 ||
    value.type !== "doc" ||
    !Array.isArray(value.content)
  ) {
    throw new RichDocumentError("Invalid document root");
  }
  const counts = { nodes: 1, text: 0 };
  return {
    type: "doc",
    version: 1,
    content: value.content.map((node) => parseNode(node, 1, counts)),
  };
}

export function parseRichDocumentSource(source: string): RichDocument {
  let value: unknown;
  try {
    value = JSON.parse(source) as unknown;
  } catch {
    throw new RichDocumentError("Document source is not valid JSON");
  }
  return parseRichDocument(value);
}

export const EMPTY_RICH_DOCUMENT: RichDocument = {
  type: "doc",
  version: 1,
  content: [{ type: "paragraph", content: [] }],
};
