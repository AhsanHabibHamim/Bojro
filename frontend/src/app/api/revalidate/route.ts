import { timingSafeEqual } from "node:crypto";

import { revalidateTag } from "next/cache";
import { NextResponse } from "next/server";

import type { AppLocale } from "@/i18n/routing";
import { catalogTags } from "@/lib/api/tags";

export const runtime = "nodejs";

const MAX_BODY_BYTES = 8_192;
const VALID_EVENTS = new Set(["created", "updated", "deleted", "published"]);
const VALID_ENTITIES = new Set([
  "homepage",
  "shell",
  "product",
  "category",
  "review",
  "flash_sale",
  "shipping",
]);
const SAFE_IDENTIFIER = /^[\p{L}\p{N}][\p{L}\p{M}\p{N}_-]{0,79}$/u;

type RevalidationEvent = {
  entity: "homepage" | "shell" | "product" | "category" | "review" | "flash_sale" | "shipping";
  event: "created" | "updated" | "deleted" | "published";
  slug?: string;
  locale?: AppLocale;
};

function secretsMatch(provided: string, expected: string): boolean {
  if (!provided || !expected || provided.length > 256 || expected.length > 256) return false;
  const size = Math.max(Buffer.byteLength(provided), Buffer.byteLength(expected));
  const providedBuffer = Buffer.alloc(size);
  const expectedBuffer = Buffer.alloc(size);
  providedBuffer.write(provided);
  expectedBuffer.write(expected);
  return timingSafeEqual(providedBuffer, expectedBuffer) && provided.length === expected.length;
}

function isEvent(value: unknown): value is RevalidationEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Record<string, unknown>;
  if (
    typeof event.entity !== "string" ||
    !VALID_ENTITIES.has(event.entity) ||
    typeof event.event !== "string" ||
    !VALID_EVENTS.has(event.event)
  ) {
    return false;
  }
  if (event.locale !== undefined && event.locale !== "bn" && event.locale !== "en") return false;
  if (
    event.slug !== undefined &&
    (typeof event.slug !== "string" || !SAFE_IDENTIFIER.test(event.slug.normalize("NFC")))
  ) {
    return false;
  }
  return true;
}

function tagsForEvent(event: RevalidationEvent): string[] | null {
  const locales: AppLocale[] = event.locale ? [event.locale] : ["bn", "en"];
  switch (event.entity) {
    case "homepage":
      return locales.map(catalogTags.home);
    case "shell":
      return locales.map(catalogTags.shell);
    case "product":
      return event.slug
        ? [
            catalogTags.catalog,
            catalogTags.products,
            catalogTags.categories,
            catalogTags.filters,
            catalogTags.product(event.slug),
            ...locales.map(catalogTags.home),
          ]
        : null;
    case "category":
      return event.slug
        ? [
            catalogTags.catalog,
            catalogTags.categories,
            catalogTags.filters,
            catalogTags.products,
            catalogTags.category(event.slug),
            ...locales.flatMap((locale) => [catalogTags.home(locale), catalogTags.shell(locale)]),
          ]
        : null;
    case "review":
      return event.slug
        ? [
            catalogTags.product(event.slug),
            catalogTags.reviews(event.slug),
            ...locales.map(catalogTags.home),
          ]
        : null;
    case "flash_sale":
      return [catalogTags.products, catalogTags.filters, ...locales.map(catalogTags.home)];
    case "shipping":
      return [
        catalogTags.shipping,
        ...locales.flatMap((locale) => [catalogTags.shell(locale), catalogTags.home(locale)]),
      ];
  }
}

export async function POST(request: Request) {
  const expectedSecret = process.env.REVALIDATION_SECRET ?? "";
  const providedSecret =
    request.headers.get("x-revalidation-secret") ??
    request.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ??
    "";

  if (!secretsMatch(providedSecret, expectedSecret)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const declaredLength = Number(request.headers.get("content-length") ?? 0);
  if (declaredLength > MAX_BODY_BYTES) {
    return NextResponse.json({ error: "Request body is too large" }, { status: 413 });
  }

  const body = await request.text();
  if (Buffer.byteLength(body) > MAX_BODY_BYTES) {
    return NextResponse.json({ error: "Request body is too large" }, { status: 413 });
  }

  let event: unknown;
  try {
    event = JSON.parse(body);
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!isEvent(event)) {
    return NextResponse.json({ error: "Unsupported revalidation event" }, { status: 400 });
  }

  const tags = tagsForEvent(event);
  if (!tags) {
    return NextResponse.json(
      { error: "A valid slug is required for this entity" },
      { status: 400 },
    );
  }

  const uniqueTags = [...new Set(tags)].slice(0, 16);
  uniqueTags.forEach((tag) => revalidateTag(tag, "max"));
  return NextResponse.json({ revalidated: true, tags: uniqueTags });
}
