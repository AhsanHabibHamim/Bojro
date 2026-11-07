"use client";

import { EyeSlash, FloppyDisk, PaperPlaneTilt, Trash } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { EMPTY_RICH_DOCUMENT } from "@/lib/admin/rich-document";
import {
  isAdminStaleWrite,
  requireAdminEtag,
  useAdminApi,
  useAdminMutation,
  useAdminQuery,
} from "@/lib/admin/context";
import { blogDraft, pageDraft } from "@/lib/admin/drafts";
import type {
  AdminBlogPost,
  AdminBlogPostInput,
  AdminStaticPage,
  AdminStaticPageInput,
  Versioned,
} from "@/lib/admin/types";

import { MediaUploader } from "../media/media-uploader";
import { AdminField, adminInputClass, adminTextareaClass } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { useAdminToast } from "../ui/toast";
import { RichDocumentEditor } from "./rich-document-editor";

type Kind = "page" | "blog";

const EMPTY_PAGE: AdminStaticPageInput = {
  slug: "",
  title_bn: "",
  title_en: "",
  document_bn: EMPTY_RICH_DOCUMENT,
  document_en: EMPTY_RICH_DOCUMENT,
  cover_asset_id: null,
  is_system: false,
};

const EMPTY_BLOG: AdminBlogPostInput = {
  slug: "",
  title_bn: "",
  title_en: "",
  excerpt_bn: null,
  excerpt_en: null,
  document_bn: EMPTY_RICH_DOCUMENT,
  document_en: EMPTY_RICH_DOCUMENT,
  cover_asset_id: null,
  tags: [],
};

export function ContentEditor({
  kind,
  id,
  locale,
}: {
  kind: Kind;
  id: string | null;
  locale: AppLocale;
}) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const router = useRouter();
  const mutate = useAdminMutation(`${kind}:${id ?? "create"}`);
  const query = useAdminQuery<Versioned<AdminStaticPage | AdminBlogPost> | null>(
    async (signal) => {
      if (!id) return null;
      return kind === "page" ? api.page(id, signal) : api.blogPost(id, signal);
    },
    [api, id, kind],
  );
  const [page, setPage] = useState(EMPTY_PAGE);
  const [blog, setBlog] = useState(EMPTY_BLOG);
  const [tags, setTags] = useState("");
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [documentValid, setDocumentValid] = useState({ bn: true, en: true });
  const setBnValidity = useCallback(
    (valid: boolean) => setDocumentValid((current) => ({ ...current, bn: valid })),
    [],
  );
  const setEnValidity = useCallback(
    (valid: boolean) => setDocumentValid((current) => ({ ...current, en: valid })),
    [],
  );

  useEffect(() => {
    if (!query.data) return;
    const value = query.data.data;
    queueMicrotask(() => {
      if (kind === "page" && "is_system" in value) {
        setPage(pageDraft(value));
      } else if (kind === "blog" && "excerpt_bn" in value) {
        setBlog(blogDraft(value));
        setTags(value.tags.join(", "));
      }
    });
  }, [kind, query.data]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!documentValid.bn || !documentValid.en) {
      toast.push(t("content.documentInvalid"), "error");
      return;
    }
    const payload =
      kind === "page"
        ? page
        : {
            ...blog,
            tags: tags
              .split(",")
              .map((tag) => tag.trim().toLowerCase())
              .filter(Boolean)
              .slice(0, 20),
          };
    setBusy(true);
    try {
      const result = await mutate<Versioned<AdminStaticPage | AdminBlogPost>>(payload, (key) => {
        if (kind === "page") {
          return id
            ? api.updatePage(
                id,
                payload as AdminStaticPageInput,
                requireAdminEtag(query.data?.etag ?? null),
                key,
              )
            : api.createPage(payload as AdminStaticPageInput, key);
        }
        return id
          ? api.updateBlogPost(
              id,
              payload as AdminBlogPostInput,
              requireAdminEtag(query.data?.etag ?? null),
              key,
            )
          : api.createBlogPost(payload as AdminBlogPostInput, key);
      });
      toast.push(id ? t("toast.saved") : t("toast.created"));
      if (!id)
        router.replace(
          `/${locale}/admin/content/${kind === "page" ? "pages" : "blog"}/${result.data.id}`,
        );
      else query.reload();
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    } finally {
      setBusy(false);
    }
  }

  async function publish(published: boolean) {
    if (!id) return;
    try {
      await mutate<unknown>({ published }, (key) =>
        kind === "page"
          ? api.publishPage(id, published, requireAdminEtag(query.data?.etag ?? null), key)
          : api.publishBlogPost(id, published, requireAdminEtag(query.data?.etag ?? null), key),
      );
      query.reload();
      toast.push(published ? t("toast.published") : t("toast.unpublished"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  async function remove() {
    if (!id) return;
    try {
      await mutate<unknown>({ id }, (key) =>
        kind === "page"
          ? api.deletePage(id, requireAdminEtag(query.data?.etag ?? null), key)
          : api.deleteBlogPost(id, requireAdminEtag(query.data?.etag ?? null), key),
      );
      toast.push(t("toast.deleted"));
      router.replace(`/${locale}/admin/content/${kind === "page" ? "pages" : "blog"}`);
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  if (id && query.loading) return <AdminLoading label={t("common.loading")} />;
  if (id && query.error)
    return (
      <AdminLoadError
        error={query.error}
        onRetry={query.reload}
        retryLabel={t("common.retry")}
        title={t("common.loadError")}
      />
    );
  const published = query.data?.data.is_published ?? false;
  const status = published ? "published" : "draft";
  const title =
    kind === "page" ? page.title_en || t("content.newPage") : blog.title_en || t("content.newPost");

  return (
    <div className="grid gap-6">
      <AdminPageHeader
        actions={
          id ? (
            <>
              <button
                className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/15 px-4 font-black text-deep-indigo"
                onClick={() => void publish(!published)}
                type="button"
              >
                {published ? (
                  <EyeSlash aria-hidden size={18} />
                ) : (
                  <PaperPlaneTilt aria-hidden size={18} />
                )}
                {published ? t("content.unpublish") : t("content.publish")}
              </button>
              <button
                className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-error/20 px-4 font-black text-error"
                onClick={() => void remove()}
                type="button"
              >
                <Trash aria-hidden size={18} />
                {t("common.delete")}
              </button>
            </>
          ) : undefined
        }
        description={kind === "page" ? t("content.pagesDescription") : t("content.blogDescription")}
        eyebrow={status}
        title={title}
      />
      <form className="grid gap-6" onSubmit={save}>
        <section className="grid gap-4 rounded-2xl border border-brand-purple/12 bg-white p-5 sm:grid-cols-2">
          <AdminField htmlFor="content-slug" label={t("common.slug")} required>
            <input
              className={adminInputClass}
              disabled={Boolean(id)}
              id="content-slug"
              onChange={(event) =>
                kind === "page"
                  ? setPage((current) => ({ ...current, slug: event.target.value }))
                  : setBlog((current) => ({ ...current, slug: event.target.value }))
              }
              pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
              required
              value={kind === "page" ? page.slug : blog.slug}
            />
          </AdminField>
          <div />
          <AdminField htmlFor="content-title-bn" label={t("content.titleBn")} required>
            <input
              className={adminInputClass}
              id="content-title-bn"
              onChange={(event) =>
                kind === "page"
                  ? setPage((current) => ({ ...current, title_bn: event.target.value }))
                  : setBlog((current) => ({ ...current, title_bn: event.target.value }))
              }
              required
              value={kind === "page" ? page.title_bn : blog.title_bn}
            />
          </AdminField>
          <AdminField htmlFor="content-title-en" label={t("content.titleEn")} required>
            <input
              className={adminInputClass}
              id="content-title-en"
              onChange={(event) =>
                kind === "page"
                  ? setPage((current) => ({ ...current, title_en: event.target.value }))
                  : setBlog((current) => ({ ...current, title_en: event.target.value }))
              }
              required
              value={kind === "page" ? page.title_en : blog.title_en}
            />
          </AdminField>
          {kind === "blog" ? (
            <>
              <AdminField htmlFor="content-summary-bn" label={t("content.excerptBn")}>
                <textarea
                  className={adminTextareaClass}
                  id="content-summary-bn"
                  onChange={(event) =>
                    setBlog((current) => ({
                      ...current,
                      excerpt_bn: event.target.value || null,
                    }))
                  }
                  value={blog.excerpt_bn ?? ""}
                />
              </AdminField>
              <AdminField htmlFor="content-summary-en" label={t("content.excerptEn")}>
                <textarea
                  className={adminTextareaClass}
                  id="content-summary-en"
                  onChange={(event) =>
                    setBlog((current) => ({
                      ...current,
                      excerpt_en: event.target.value || null,
                    }))
                  }
                  value={blog.excerpt_en ?? ""}
                />
              </AdminField>
            </>
          ) : (
            <>
              <AdminField htmlFor="page-cover" label={t("content.cover")}>
                <input
                  className={adminInputClass}
                  id="page-cover"
                  onChange={(event) =>
                    setPage((current) => ({
                      ...current,
                      cover_asset_id: event.target.value || null,
                    }))
                  }
                  value={page.cover_asset_id ?? ""}
                />
              </AdminField>
              <div className="sm:col-span-2">
                <MediaUploader
                  onUploaded={(asset) =>
                    setPage((current) => ({ ...current, cover_asset_id: asset.id }))
                  }
                  purpose="page"
                />
                {page.cover_asset_id ? (
                  <button
                    className="mt-3 min-h-11 rounded-xl border border-error/20 px-4 font-bold text-error"
                    onClick={() => setPage((current) => ({ ...current, cover_asset_id: null }))}
                    type="button"
                  >
                    {t("common.removeMedia")}
                  </button>
                ) : null}
              </div>
            </>
          )}
          {kind === "blog" ? (
            <>
              <AdminField htmlFor="content-tags" label={t("content.tags")}>
                <input
                  className={adminInputClass}
                  id="content-tags"
                  onChange={(event) => setTags(event.target.value)}
                  value={tags}
                />
              </AdminField>
              <AdminField htmlFor="content-cover" label={t("content.cover")}>
                <input
                  className={adminInputClass}
                  id="content-cover"
                  onChange={(event) =>
                    setBlog((current) => ({
                      ...current,
                      cover_asset_id: event.target.value || null,
                    }))
                  }
                  value={blog.cover_asset_id ?? ""}
                />
              </AdminField>
              <div className="sm:col-span-2">
                <MediaUploader
                  onUploaded={(asset) =>
                    setBlog((current) => ({ ...current, cover_asset_id: asset.id }))
                  }
                  purpose="blog"
                />
                {blog.cover_asset_id ? (
                  <button
                    className="mt-3 min-h-11 rounded-xl border border-error/20 px-4 font-bold text-error"
                    onClick={() => setBlog((current) => ({ ...current, cover_asset_id: null }))}
                    type="button"
                  >
                    {t("common.removeMedia")}
                  </button>
                ) : null}
              </div>
            </>
          ) : null}
        </section>
        <section className="grid gap-6 rounded-2xl border border-brand-purple/12 bg-white p-5">
          <RichDocumentEditor
            help={t("content.documentHelp")}
            id="document-bn"
            invalidMessage={t("content.documentInvalid")}
            label={t("content.documentBn")}
            onChange={(document_bn) =>
              kind === "page"
                ? setPage((current) => ({ ...current, document_bn }))
                : setBlog((current) => ({ ...current, document_bn }))
            }
            onValidityChange={setBnValidity}
            previewLabel={t("content.preview")}
            value={kind === "page" ? page.document_bn : blog.document_bn}
          />
          <RichDocumentEditor
            help={t("content.documentHelp")}
            id="document-en"
            invalidMessage={t("content.documentInvalid")}
            label={t("content.documentEn")}
            onChange={(document_en) =>
              kind === "page"
                ? setPage((current) => ({ ...current, document_en }))
                : setBlog((current) => ({ ...current, document_en }))
            }
            onValidityChange={setEnValidity}
            previewLabel={t("content.preview")}
            value={kind === "page" ? page.document_en : blog.document_en}
          />
        </section>
        <button
          className="signature-gradient inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-6 font-black text-white disabled:opacity-45 sm:justify-self-start"
          disabled={busy || !documentValid.bn || !documentValid.en}
          type="submit"
        >
          <FloppyDisk aria-hidden size={20} />
          {busy ? t("common.saving") : t("common.save")}
        </button>
      </form>
      <StaleRecordDialog onClose={() => setStale(false)} onReload={query.reload} open={stale} />
    </div>
  );
}
