import type {
  AdminBlogPost,
  AdminBlogPostInput,
  AdminBrand,
  AdminBrandInput,
  AdminCategory,
  AdminCategoryInput,
  AdminStaticPage,
  AdminStaticPageInput,
} from "./types";

export function categoryDraft(value: AdminCategory): AdminCategoryInput {
  return {
    name_bn: value.name_bn,
    name_en: value.name_en,
    parent_id: value.parent_id,
    icon: value.icon,
    is_active: value.is_active,
    image_asset_id: value.image_asset_id,
  };
}

export function brandDraft(value: AdminBrand): AdminBrandInput {
  return {
    name: value.name,
    logo_asset_id: value.logo_asset_id,
    is_active: value.is_active,
  };
}

export function pageDraft(value: AdminStaticPage): AdminStaticPageInput {
  return {
    slug: value.slug,
    title_bn: value.title_bn,
    title_en: value.title_en,
    document_bn: value.document_bn,
    document_en: value.document_en,
    cover_asset_id: value.cover_asset_id,
    is_system: value.is_system,
  };
}

export function blogDraft(value: AdminBlogPost): AdminBlogPostInput {
  return {
    slug: value.slug,
    title_bn: value.title_bn,
    title_en: value.title_en,
    excerpt_bn: value.excerpt_bn,
    excerpt_en: value.excerpt_en,
    document_bn: value.document_bn,
    document_en: value.document_en,
    cover_asset_id: value.cover_asset_id,
    tags: value.tags,
  };
}
