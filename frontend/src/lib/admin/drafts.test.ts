import { describe, expect, it } from "vitest";

import { EMPTY_RICH_DOCUMENT } from "./rich-document";
import { blogDraft, brandDraft, categoryDraft, pageDraft } from "./drafts";

describe("admin edit drafts", () => {
  it("preserves existing taxonomy media until explicit removal", () => {
    expect(
      categoryDraft({
        id: "category-1",
        slug: "category",
        parent_id: null,
        name_bn: "ক্যাটাগরি",
        name_en: "Category",
        icon: null,
        image_asset_id: "category-media",
        sort_order: 1,
        is_active: true,
        depth: 0,
        revision: 1,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      }).image_asset_id,
    ).toBe("category-media");
    expect(
      brandDraft({
        id: "brand-1",
        slug: "brand",
        name: "Brand",
        is_active: true,
        logo_asset_id: "brand-media",
        revision: 1,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      }).logo_asset_id,
    ).toBe("brand-media");
  });

  it("preserves page and blog covers", () => {
    const base = {
      id: "content-1",
      slug: "story",
      title_bn: "গল্প",
      title_en: "Story",
      document_bn: EMPTY_RICH_DOCUMENT,
      document_en: EMPTY_RICH_DOCUMENT,
      cover_asset_id: "cover-media",
      is_published: false,
      published_at: null,
      revision: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    expect(pageDraft({ ...base, is_system: false }).cover_asset_id).toBe("cover-media");
    expect(
      blogDraft({ ...base, excerpt_bn: null, excerpt_en: null, tags: [] }).cover_asset_id,
    ).toBe("cover-media");
  });
});
