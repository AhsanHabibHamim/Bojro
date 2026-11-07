"use client";

import { PencilSimple, Plus, Trash } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { type FormEvent, useEffect, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import {
  isAdminStaleWrite,
  requireAdminEtag,
  useAdminApi,
  useAdminMutation,
  useAdminQuery,
} from "@/lib/admin/context";
import type {
  AdminBanner,
  AdminBannerInput,
  AdminHomepageSection,
  AdminHomepageSectionInput,
} from "@/lib/admin/types";

import { MediaUploader } from "../media/media-uploader";
import { AdminDialog } from "../ui/dialog";
import { AdminField, adminInputClass, adminTextareaClass } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { KeyboardSortableList } from "../ui/sortable-grid";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { AdminStatusBadge } from "../ui/status-badge";
import { useAdminToast } from "../ui/toast";
import { HomepageContentEditor } from "./homepage-content-editor";

const EMPTY_BANNER: AdminBannerInput = {
  slug: "",
  placement: "home_hero",
  title_bn: "",
  title_en: "",
  subtitle_bn: null,
  subtitle_en: null,
  image_bn_asset_id: "",
  image_en_asset_id: "",
  href: "/shop",
  is_visible: false,
  starts_at: null,
  ends_at: null,
};

function localDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function isoOrNull(value: string | null | undefined): string | null {
  return value ? new Date(value).toISOString() : null;
}

export function HomepageManager({ locale }: { locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const mutate = useAdminMutation("homepage-manager");
  const sectionsQuery = useAdminQuery((signal) => api.homepageSections(signal), [api]);
  const bannersQuery = useAdminQuery(
    (signal) => api.homepageBannerCollection({ limit: 100 }, signal),
    [api],
  );
  const [sections, setSections] = useState<AdminHomepageSection[]>([]);
  const [banners, setBanners] = useState<AdminBanner[]>([]);
  const [section, setSection] = useState<AdminHomepageSection | null>(null);
  const [sectionInput, setSectionInput] = useState<AdminHomepageSectionInput | null>(null);
  const [bannerOpen, setBannerOpen] = useState(false);
  const [editingBanner, setEditingBanner] = useState<AdminBanner | null>(null);
  const [editingBannerEtag, setEditingBannerEtag] = useState<string | null>(null);
  const [bannerInput, setBannerInput] = useState(EMPTY_BANNER);
  const [stale, setStale] = useState(false);
  const sectionLabel = (type: string) =>
    t.has(`homepageTypes.${type}` as never)
      ? t(`homepageTypes.${type}` as never)
      : type.replaceAll("_", " ");

  useEffect(() => {
    if (sectionsQuery.data) {
      const next = [...sectionsQuery.data.data.items].sort((a, b) => a.order - b.order);
      queueMicrotask(() => setSections(next));
    }
  }, [sectionsQuery.data]);
  useEffect(() => {
    if (bannersQuery.data) {
      const next = [...bannersQuery.data.data.items].sort((a, b) => a.order - b.order);
      queueMicrotask(() => setBanners(next));
    }
  }, [bannersQuery.data]);

  function editSection(value: AdminHomepageSection) {
    setSection(value);
    setSectionInput({
      is_visible: value.is_visible,
      content_bn: value.content_bn,
      content_en: value.content_en,
    });
  }

  async function submitSection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!section || !sectionInput) return;
    const payload = sectionInput;
    try {
      await mutate(payload, (key) =>
        api.updateHomepageSection(section.id, payload, section.etag, key),
      );
      setSection(null);
      sectionsQuery.reload();
      toast.push(t("toast.saved"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  function newBanner() {
    setEditingBanner(null);
    setEditingBannerEtag(null);
    setBannerInput(EMPTY_BANNER);
    setBannerOpen(true);
  }

  async function editBanner(value: AdminBanner) {
    const detail = await api.homepageBanner(value.id);
    const current = detail.data;
    setEditingBanner(current);
    setEditingBannerEtag(detail.etag);
    setBannerInput({
      slug: current.slug,
      placement: current.placement,
      title_bn: current.title_bn,
      title_en: current.title_en,
      subtitle_bn: current.subtitle_bn,
      subtitle_en: current.subtitle_en,
      image_bn_asset_id: current.image_bn_asset_id ?? "",
      image_en_asset_id: current.image_en_asset_id ?? "",
      href: current.href,
      is_visible: current.is_visible,
      starts_at: localDateTime(current.starts_at),
      ends_at: localDateTime(current.ends_at),
    });
    setBannerOpen(true);
  }

  async function submitBanner(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = {
      ...bannerInput,
      starts_at: isoOrNull(bannerInput.starts_at),
      ends_at: isoOrNull(bannerInput.ends_at),
    };
    if (payload.starts_at && payload.ends_at && payload.starts_at >= payload.ends_at) {
      toast.push(t("errors.VALIDATION_ERROR"), "error");
      return;
    }
    try {
      await mutate(payload, (key) =>
        editingBanner
          ? api.updateHomepageBanner(
              editingBanner.id,
              payload,
              requireAdminEtag(editingBannerEtag),
              key,
            )
          : api.createHomepageBanner(payload, key),
      );
      setBannerOpen(false);
      bannersQuery.reload();
      toast.push(editingBanner ? t("toast.saved") : t("toast.created"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  async function reloadActiveEditor() {
    sectionsQuery.reload();
    bannersQuery.reload();
    if (section) {
      const latest = await api.homepageSections();
      const active = latest.data.items.find((item) => item.id === section.id);
      if (active) editSection(active);
    }
    if (editingBanner) await editBanner(editingBanner);
  }

  if (sectionsQuery.loading || bannersQuery.loading)
    return <AdminLoading label={t("common.loading")} />;
  const loadError = sectionsQuery.error ?? bannersQuery.error;
  if (loadError)
    return (
      <AdminLoadError
        error={loadError}
        onRetry={() => {
          sectionsQuery.reload();
          bannersQuery.reload();
        }}
        retryLabel={t("common.retry")}
        title={t("common.loadError")}
      />
    );

  return (
    <div className="grid gap-7">
      <AdminPageHeader description={t("homepage.description")} title={t("homepage.title")} />
      <section className="grid gap-4 rounded-2xl border border-brand-purple/12 bg-white p-5">
        <h2 className="text-2xl font-extrabold">{t("homepage.sections")}</h2>
        <KeyboardSortableList
          itemKey={(item) => item.id}
          items={sections}
          labels={{
            moveDown: t("common.moveDown"),
            moveUp: t("common.moveUp"),
            drag: t("common.dragToReorder"),
            moved: t("common.movedToPosition"),
          }}
          onReorder={setSections}
          render={(item, index) => (
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-xl bg-soft-lavender font-black text-brand-purple">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <strong>{sectionLabel(item.type)}</strong>
                <div className="mt-1">
                  <AdminStatusBadge status={item.is_visible ? "active" : "inactive"} />
                </div>
              </div>
              <button
                aria-label={t("common.edit")}
                className="grid size-11 place-items-center rounded-xl text-brand-purple hover:bg-soft-lavender"
                onClick={() => editSection(item)}
                type="button"
              >
                <PencilSimple aria-hidden size={19} />
              </button>
            </div>
          )}
        />
        <button
          className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white sm:justify-self-start"
          onClick={() =>
            void mutate({ ids: sections.map((item) => item.id) }, (key) =>
              api.reorderHomepageSections(
                sections.map((item) => item.id),
                requireAdminEtag(sectionsQuery.data?.etag ?? null),
                key,
              ),
            )
              .then(() => {
                toast.push(t("toast.saved"));
                sectionsQuery.reload();
              })
              .catch((caught) =>
                isAdminStaleWrite(caught) ? setStale(true) : toast.push(t("toast.error"), "error"),
              )
          }
          type="button"
        >
          {t("common.save")}
        </button>
      </section>

      <section className="grid gap-4 rounded-2xl border border-brand-purple/12 bg-white p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-2xl font-extrabold">{t("homepage.banners")}</h2>
          <button
            className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-deep-indigo px-4 font-black text-white"
            onClick={newBanner}
            type="button"
          >
            <Plus aria-hidden size={18} /> {t("homepage.newBanner")}
          </button>
        </div>
        <KeyboardSortableList
          itemKey={(item) => item.id}
          items={banners}
          labels={{
            moveDown: t("common.moveDown"),
            moveUp: t("common.moveUp"),
            drag: t("common.dragToReorder"),
            moved: t("common.movedToPosition"),
          }}
          onReorder={setBanners}
          render={(item) => (
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <strong>{locale === "bn" ? item.title_bn : item.title_en}</strong>
                <p className="truncate text-xs text-muted">
                  {item.slug} · {item.placement}
                </p>
              </div>
              <AdminStatusBadge status={item.is_visible ? "active" : "inactive"} />
              <button
                aria-label={t("common.edit")}
                className="grid size-11 place-items-center rounded-xl text-brand-purple"
                onClick={() =>
                  void editBanner(item).catch(() => toast.push(t("toast.error"), "error"))
                }
                type="button"
              >
                <PencilSimple aria-hidden size={19} />
              </button>
              <button
                aria-label={t("common.delete")}
                className="grid size-11 place-items-center rounded-xl text-error"
                onClick={() =>
                  void api
                    .homepageBanner(item.id)
                    .then((detail) =>
                      mutate({ id: item.id }, (key) =>
                        api.deleteHomepageBanner(item.id, requireAdminEtag(detail.etag), key),
                      ),
                    )
                    .then(() => bannersQuery.reload())
                    .catch(() => toast.push(t("toast.error"), "error"))
                }
                type="button"
              >
                <Trash aria-hidden size={18} />
              </button>
            </div>
          )}
        />
        <button
          className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white sm:justify-self-start"
          onClick={() =>
            void mutate({ ids: banners.map((item) => item.id) }, (key) =>
              api.reorderHomepageBanners(
                banners.map((item) => item.id),
                requireAdminEtag(bannersQuery.data?.etag ?? null),
                key,
              ),
            )
              .then(() => {
                toast.push(t("toast.saved"));
                bannersQuery.reload();
              })
              .catch((caught) =>
                isAdminStaleWrite(caught) ? setStale(true) : toast.push(t("toast.error"), "error"),
              )
          }
          type="button"
        >
          {t("common.save")}
        </button>
      </section>

      <AdminDialog
        closeLabel={t("common.close")}
        footer={
          <button
            className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white"
            form="homepage-section-form"
            type="submit"
          >
            {t("common.save")}
          </button>
        }
        onClose={() => setSection(null)}
        open={Boolean(section)}
        title={section ? sectionLabel(section.type) : t("homepage.sections")}
      >
        {sectionInput ? (
          <form className="grid gap-4" id="homepage-section-form" onSubmit={submitSection}>
            <fieldset className="grid gap-4 rounded-xl border border-brand-purple/12 p-4">
              <legend className="px-2 font-extrabold">{t("common.bengali")}</legend>
              <HomepageContentEditor
                content={(sectionInput.content_bn ?? {}) as Record<string, unknown>}
                id="section-content-bn"
                onChange={(content_bn) =>
                  setSectionInput((current) => (current ? { ...current, content_bn } : current))
                }
                sectionType={section!.type}
              />
            </fieldset>
            <fieldset className="grid gap-4 rounded-xl border border-brand-purple/12 p-4">
              <legend className="px-2 font-extrabold">{t("common.english")}</legend>
              <HomepageContentEditor
                content={(sectionInput.content_en ?? {}) as Record<string, unknown>}
                id="section-content-en"
                onChange={(content_en) =>
                  setSectionInput((current) => (current ? { ...current, content_en } : current))
                }
                sectionType={section!.type}
              />
            </fieldset>
            <label className="flex min-h-12 items-center gap-3 rounded-xl border border-brand-purple/12 px-4 font-bold">
              <input
                checked={Boolean(sectionInput.is_visible)}
                onChange={(event) =>
                  setSectionInput((current) =>
                    current ? { ...current, is_visible: event.target.checked } : current,
                  )
                }
                type="checkbox"
              />
              {t("homepage.visible")}
            </label>
          </form>
        ) : null}
      </AdminDialog>

      <AdminDialog
        closeLabel={t("common.close")}
        footer={
          <button
            className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white"
            form="banner-form"
            type="submit"
          >
            {t("common.save")}
          </button>
        }
        onClose={() => setBannerOpen(false)}
        open={bannerOpen}
        title={editingBanner ? t("common.edit") : t("homepage.newBanner")}
      >
        <form className="grid gap-4 sm:grid-cols-2" id="banner-form" onSubmit={submitBanner}>
          {!editingBanner ? (
            <AdminField htmlFor="banner-slug" label={t("common.slug")} required>
              <input
                className={adminInputClass}
                id="banner-slug"
                onChange={(event) =>
                  setBannerInput((current) => ({ ...current, slug: event.target.value }))
                }
                required
                value={bannerInput.slug ?? ""}
              />
            </AdminField>
          ) : null}
          <AdminField htmlFor="banner-placement" label={t("common.position")} required>
            <input
              className={adminInputClass}
              id="banner-placement"
              onChange={(event) =>
                setBannerInput((current) => ({ ...current, placement: event.target.value }))
              }
              required
              value={bannerInput.placement}
            />
          </AdminField>
          <AdminField htmlFor="banner-title-bn" label={t("content.titleBn")} required>
            <input
              className={adminInputClass}
              id="banner-title-bn"
              onChange={(event) =>
                setBannerInput((current) => ({ ...current, title_bn: event.target.value }))
              }
              required
              value={bannerInput.title_bn}
            />
          </AdminField>
          <AdminField htmlFor="banner-title-en" label={t("content.titleEn")} required>
            <input
              className={adminInputClass}
              id="banner-title-en"
              onChange={(event) =>
                setBannerInput((current) => ({ ...current, title_en: event.target.value }))
              }
              required
              value={bannerInput.title_en}
            />
          </AdminField>
          <AdminField htmlFor="banner-subtitle-bn" label={t("content.summaryBn")}>
            <textarea
              className={adminTextareaClass}
              id="banner-subtitle-bn"
              onChange={(event) =>
                setBannerInput((current) => ({
                  ...current,
                  subtitle_bn: event.target.value || null,
                }))
              }
              value={bannerInput.subtitle_bn ?? ""}
            />
          </AdminField>
          <AdminField htmlFor="banner-subtitle-en" label={t("content.summaryEn")}>
            <textarea
              className={adminTextareaClass}
              id="banner-subtitle-en"
              onChange={(event) =>
                setBannerInput((current) => ({
                  ...current,
                  subtitle_en: event.target.value || null,
                }))
              }
              value={bannerInput.subtitle_en ?? ""}
            />
          </AdminField>
          <AdminField htmlFor="banner-href" label={t("homepage.href")}>
            <input
              className={adminInputClass}
              id="banner-href"
              onChange={(event) =>
                setBannerInput((current) => ({ ...current, href: event.target.value || null }))
              }
              value={bannerInput.href ?? ""}
            />
          </AdminField>
          <label className="flex min-h-12 items-center gap-3 rounded-xl border border-brand-purple/12 px-4 font-bold">
            <input
              checked={bannerInput.is_visible}
              onChange={(event) =>
                setBannerInput((current) => ({ ...current, is_visible: event.target.checked }))
              }
              type="checkbox"
            />
            {t("homepage.visible")}
          </label>
          <AdminField htmlFor="banner-start" label={t("common.startsAt")}>
            <input
              className={adminInputClass}
              id="banner-start"
              onChange={(event) =>
                setBannerInput((current) => ({
                  ...current,
                  starts_at: event.target.value || null,
                }))
              }
              type="datetime-local"
              value={bannerInput.starts_at ?? ""}
            />
          </AdminField>
          <AdminField htmlFor="banner-end" label={t("common.endsAt")}>
            <input
              className={adminInputClass}
              id="banner-end"
              onChange={(event) =>
                setBannerInput((current) => ({
                  ...current,
                  ends_at: event.target.value || null,
                }))
              }
              type="datetime-local"
              value={bannerInput.ends_at ?? ""}
            />
          </AdminField>
          <div className="sm:col-span-2">
            <MediaUploader
              onUploaded={(asset) =>
                setBannerInput((current) => ({
                  ...current,
                  image_bn_asset_id: asset.id,
                  image_en_asset_id: current.image_en_asset_id || asset.id,
                }))
              }
              purpose="banner"
            />
          </div>
          <AdminField
            htmlFor="banner-image-bn"
            label={`${t("homepage.image")} · ${t("common.bengali")}`}
            required
          >
            <input
              className={adminInputClass}
              id="banner-image-bn"
              onChange={(event) =>
                setBannerInput((current) => ({ ...current, image_bn_asset_id: event.target.value }))
              }
              required
              value={bannerInput.image_bn_asset_id}
            />
          </AdminField>
          <AdminField
            htmlFor="banner-image-en"
            label={`${t("homepage.image")} · ${t("common.english")}`}
            required
          >
            <input
              className={adminInputClass}
              id="banner-image-en"
              onChange={(event) =>
                setBannerInput((current) => ({ ...current, image_en_asset_id: event.target.value }))
              }
              required
              value={bannerInput.image_en_asset_id}
            />
          </AdminField>
        </form>
      </AdminDialog>
      <StaleRecordDialog
        onClose={() => setStale(false)}
        onReload={() => void reloadActiveEditor()}
        open={stale}
      />
    </div>
  );
}
