import Image from "next/image";
import type { ReactNode } from "react";

import { parseRichDocument } from "@/lib/admin/rich-document";
import type { RichDocument, RichNode, RichTextNode } from "@/lib/admin/types";

function safeLink(href: string | undefined): string | null {
  if (!href) return null;
  if ((href.startsWith("/") && !href.startsWith("//")) || href.startsWith("#")) return href;
  try {
    const url = new URL(href);
    return ["http:", "https:", "mailto:", "tel:"].includes(url.protocol) ? href : null;
  } catch {
    return null;
  }
}

function renderText(node: RichTextNode, key: string): ReactNode {
  let content: ReactNode = node.text;
  [...(node.marks ?? [])].reverse().forEach((mark, index) => {
    if (mark.type === "bold") content = <strong key={`${key}-bold-${index}`}>{content}</strong>;
    if (mark.type === "italic") content = <em key={`${key}-italic-${index}`}>{content}</em>;
    if (mark.type === "strike") content = <s key={`${key}-strike-${index}`}>{content}</s>;
    if (mark.type === "code") content = <code key={`${key}-code-${index}`}>{content}</code>;
    if (mark.type === "link") {
      const href = safeLink(mark.attrs?.href);
      if (href) {
        content = (
          <a
            key={`${key}-link-${index}`}
            className="font-bold text-brand-purple underline decoration-brand-purple/35 underline-offset-4"
            href={href}
            rel={href.startsWith("http") ? "noopener noreferrer" : undefined}
          >
            {content}
          </a>
        );
      }
    }
  });
  return <span key={key}>{content}</span>;
}

export type ResolvedRichMedia = Record<string, { url: string; width?: number; height?: number }>;

function nodes(
  content: RichNode[] | undefined,
  prefix: string,
  media: ResolvedRichMedia,
): ReactNode[] {
  return (content ?? []).map((node, index) => renderNode(node, `${prefix}-${index}`, media));
}

function renderNode(node: RichNode, key: string, media: ResolvedRichMedia): ReactNode {
  if (node.type === "text") return renderText(node, key);
  if (node.type === "hardBreak") return <br key={key} />;
  if (node.type === "paragraph") return <p key={key}>{nodes(node.content, key, media)}</p>;
  if (node.type === "heading") {
    if (node.attrs.level === 2) return <h2 key={key}>{nodes(node.content, key, media)}</h2>;
    if (node.attrs.level === 3) return <h3 key={key}>{nodes(node.content, key, media)}</h3>;
    return <h4 key={key}>{nodes(node.content, key, media)}</h4>;
  }
  if (node.type === "blockquote") {
    return (
      <blockquote key={key} className="border-l-4 border-brand-purple pl-5 text-muted italic">
        {nodes(node.content, key, media)}
      </blockquote>
    );
  }
  if (node.type === "bulletList") {
    return <ul key={key}>{nodes(node.content, key, media)}</ul>;
  }
  if (node.type === "orderedList") {
    return <ol key={key}>{nodes(node.content, key, media)}</ol>;
  }
  if (node.type === "listItem") return <li key={key}>{nodes(node.content, key, media)}</li>;
  const resolved = media[node.attrs.media_asset_id];
  if (resolved && /^https:\/\//.test(resolved.url)) {
    return (
      <figure key={key} className="my-7">
        <Image
          alt={node.attrs.alt}
          className="h-auto w-full rounded-2xl object-cover"
          height={resolved.height ?? 675}
          sizes="(max-width: 768px) 100vw, 768px"
          src={resolved.url}
          unoptimized
          width={resolved.width ?? 1200}
        />
      </figure>
    );
  }
  return (
    <figure
      key={key}
      className="my-7 rounded-2xl border border-brand-purple/10 bg-page-background p-6 text-center"
      data-media-asset={node.attrs.media_asset_id}
    >
      <figcaption className="text-sm text-muted">{node.attrs.alt}</figcaption>
    </figure>
  );
}

export function RichDocumentRenderer({
  document,
  className = "",
  media = {},
}: {
  document: RichDocument;
  className?: string;
  media?: ResolvedRichMedia;
}) {
  const safeDocument = parseRichDocument(document);
  return (
    <article
      className={`space-y-5 text-[1.02rem] leading-8 text-ink [&_h2]:mt-10 [&_h2]:text-3xl [&_h2]:font-extrabold [&_h3]:mt-8 [&_h3]:text-2xl [&_h3]:font-extrabold [&_h4]:mt-7 [&_h4]:text-xl [&_h4]:font-extrabold [&_li]:ml-6 [&_li]:pl-1 ${className}`}
    >
      {nodes(safeDocument.content, "document", media)}
    </article>
  );
}
