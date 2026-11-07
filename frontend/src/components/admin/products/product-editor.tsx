"use client";

import { FloppyDisk, Plus, Trash } from "@phosphor-icons/react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { AdminApiError } from "@/lib/admin/client";
import {
  isAdminStaleWrite,
  requireAdminEtag,
  useAdminApi,
  useAdminMutation,
  useAdminQuery,
} from "@/lib/admin/context";
import type {
  AdminMediaAsset,
  AdminProductImage,
  AdminProductInput,
  AdminProductVariant,
  AdminProductVariantInput,
} from "@/lib/admin/types";

import { MediaUploader } from "../media/media-uploader";
import { AdminField, adminInputClass, adminTextareaClass, fieldErrorProps } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { KeyboardSortableList } from "../ui/sortable-grid";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { AdminStatusBadge } from "../ui/status-badge";
import { useAdminToast } from "../ui/toast";

const EMPTY_VARIANT: AdminProductVariantInput = {
  sku: "",
  options: {},
  price_poisha: 0,
  compare_at_price_poisha: null,
  stock_on_hand: 0,
  weight_g: 100,
  is_active: true,
};

const EMPTY_PRODUCT: AdminProductInput = {
  slug: "",
  name_bn: "",
  name_en: "",
  description_bn: "",
  description_en: "",
  category_id: "",
  brand_id: null,
  status: "draft",
  is_featured: false,
  seo_title_bn: null,
  seo_title_en: null,
  seo_description_bn: null,
  seo_description_en: null,
  variants: [{ ...EMPTY_VARIANT }],
  images: [],
};

type FieldErrors = Record<string, string>;

function mapErrors(error: AdminApiError, fallback: string): FieldErrors {
  return Object.fromEntries(error.fieldErrors.map((item) => [item.field, fallback]));
}

export function ProductEditor({ id, locale }: { id: string | null; locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const router = useRouter();
  const mutation = useAdminMutation(id ? `product-update:${id}` : "product-create");
  const [input, setInput] = useState<AdminProductInput>(EMPTY_PRODUCT);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);
  const [stale, setStale] = useState(false);
  const [images, setImages] = useState<AdminProductImage[]>([]);
  const [assetId, setAssetId] = useState("");
  const [imageVariantId, setImageVariantId] = useState("");
  const [altBn, setAltBn] = useState("");
  const [altEn, setAltEn] = useState("");
  const [newVariant, setNewVariant] = useState<AdminProductVariantInput>(EMPTY_VARIANT);
  const [optionsSource, setOptionsSource] = useState("{}");
  const [stockDrafts, setStockDrafts] = useState<
    Record<string, { quantity: string; reason: string }>
  >({});
  const [variantDrafts, setVariantDrafts] = useState<Record<string, AdminProductVariantInput>>({});
  const [variantOptionsSources, setVariantOptionsSources] = useState<Record<string, string>>({});

  const detail = useAdminQuery(
    (signal) => (id ? api.product(id, signal) : Promise.resolve(null)),
    [api, id],
  );
  const taxonomy = useAdminQuery(
    async (signal) => {
      const [categories, brands] = await Promise.all([
        api.categories({ limit: 100 }, signal),
        api.brands({ limit: 100 }, signal),
      ]);
      return { categories: categories.items, brands: brands.items };
    },
    [api],
  );

  useEffect(() => {
    if (!detail.data) return;
    const product = detail.data.data;
    const nextImages = [...product.images].sort(
      (left, right) => left.sort_order - right.sort_order,
    );
    const nextVariants = Object.fromEntries(
      product.variants.map((variant) => [
        variant.id,
        {
          sku: variant.sku,
          options: Object.fromEntries(
            Object.entries(variant.options).map(([key, value]) => [key, String(value)]),
          ),
          price_poisha: variant.price_poisha,
          compare_at_price_poisha: variant.compare_at_price_poisha,
          stock_on_hand: variant.stock_on_hand,
          weight_g: variant.weight_g,
          is_active: variant.is_active,
        },
      ]),
    );
    const nextOptionSources = Object.fromEntries(
      product.variants.map((variant) => [variant.id, JSON.stringify(variant.options, null, 2)]),
    );
    queueMicrotask(() => {
      setInput({
        name_bn: product.name_bn,
        name_en: product.name_en,
        description_bn: product.description_bn,
        description_en: product.description_en,
        category_id: product.category_id,
        brand_id: product.brand_id,
        status: product.status,
        is_featured: product.is_featured,
        seo_title_bn: product.seo_title_bn,
        seo_title_en: product.seo_title_en,
        seo_description_bn: product.seo_description_bn,
        seo_description_en: product.seo_description_en,
      });
      setImages(nextImages);
      setVariantDrafts(nextVariants);
      setVariantOptionsSources(nextOptionSources);
    });
  }, [detail.data]);

  function set<K extends keyof AdminProductInput>(key: K, value: AdminProductInput[K]) {
    setInput((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: "" }));
  }

  function validate(): FieldErrors {
    const next: FieldErrors = {};
    if (!input.name_bn.trim()) next.name_bn = t("common.required");
    if (!input.name_en.trim()) next.name_en = t("common.required");
    if (!input.description_bn.trim()) next.description_bn = t("common.required");
    if (!input.description_en.trim()) next.description_en = t("common.required");
    if (!input.category_id) next.category_id = t("common.required");
    if (!id && !input.slug?.trim()) next.slug = t("common.required");
    if (!id && !input.variants?.length) next.variants = t("common.required");
    if (input.status === "active" && !images.length && !input.images?.length) {
      next.images = t("products.activationHint");
    }
    return next;
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validation = validate();
    if (Object.keys(validation).length) {
      setErrors(validation);
      return;
    }
    setSaving(true);
    setErrors({});
    try {
      const result = await mutation(input, (key) =>
        id
          ? api.updateProduct(id, input, requireAdminEtag(detail.data?.etag ?? null), key)
          : api.createProduct(input, key),
      );
      toast.push(id ? t("toast.saved") : t("toast.created"));
      if (!id) router.replace(`/${locale}/admin/products/${result.data.id}`);
      else detail.reload();
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else if (caught instanceof AdminApiError) {
        setErrors(mapErrors(caught, t("common.fieldError")));
        toast.push(t("toast.error"), "error");
      }
    } finally {
      setSaving(false);
    }
  }

  async function addVariant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!id) return;
    let options: Record<string, string>;
    try {
      options = JSON.parse(optionsSource) as Record<string, string>;
    } catch {
      setErrors((current) => ({ ...current, variant_options: t("common.fieldError") }));
      return;
    }
    const payload = { ...newVariant, options };
    try {
      await mutation(payload, (key) =>
        api.createVariant(id, payload, requireAdminEtag(detail.data?.etag ?? null), key),
      );
      setNewVariant(EMPTY_VARIANT);
      setOptionsSource("{}");
      detail.reload();
      toast.push(t("toast.created"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  async function adjustStock(variant: AdminProductVariant) {
    if (!id) return;
    const draft = stockDrafts[variant.id];
    const quantity = Number(draft?.quantity);
    if (!draft?.reason.trim() || !Number.isSafeInteger(quantity) || quantity === 0) return;
    const payload = { delta: quantity, reason: draft.reason.trim() };
    try {
      await mutation(payload, (key) =>
        api.adjustStock(id, variant.id, payload, requireAdminEtag(detail.data?.etag ?? null), key),
      );
      setStockDrafts((current) => ({ ...current, [variant.id]: { quantity: "", reason: "" } }));
      detail.reload();
      toast.push(t("toast.saved"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  async function saveVariant(variant: AdminProductVariant) {
    if (!id) return;
    const payload = variantDrafts[variant.id];
    if (!payload) return;
    try {
      await mutation(payload, (key) =>
        api.updateVariant(
          id,
          variant.id,
          payload,
          requireAdminEtag(detail.data?.etag ?? null),
          key,
        ),
      );
      detail.reload();
      toast.push(t("toast.saved"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  async function archiveVariant(variant: AdminProductVariant) {
    if (!id) return;
    try {
      await mutation({ variant: variant.id }, (key) =>
        api.deleteVariant(id, variant.id, requireAdminEtag(detail.data?.etag ?? null), key),
      );
      detail.reload();
      toast.push(t("toast.deleted"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  async function attachImage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!assetId || !altBn.trim() || !altEn.trim()) return;
    if (!id) {
      set("images", [
        ...(input.images ?? []),
        {
          media_asset_id: assetId,
          variant_id: imageVariantId || null,
          alt_bn: altBn.trim(),
          alt_en: altEn.trim(),
        },
      ]);
      setAssetId("");
      setAltBn("");
      setAltEn("");
      setImageVariantId("");
      return;
    }
    const payload = {
      media_asset_id: assetId,
      variant_id: imageVariantId || null,
      alt_bn: altBn.trim(),
      alt_en: altEn.trim(),
    };
    try {
      await mutation(payload, (key) =>
        api.attachProductImage(id, payload, requireAdminEtag(detail.data?.etag ?? null), key),
      );
      setAssetId("");
      setAltBn("");
      setAltEn("");
      setImageVariantId("");
      detail.reload();
      toast.push(t("toast.saved"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  async function saveImageOrder() {
    if (!id) return;
    try {
      await mutation({ image_ids: images.map((image) => image.id) }, (key) =>
        api.reorderProductImages(
          id,
          images.map((image) => image.id),
          requireAdminEtag(detail.data?.etag ?? null),
          key,
        ),
      );
      detail.reload();
      toast.push(t("toast.saved"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  async function saveImageAlt(image: AdminProductImage) {
    if (!id) return;
    try {
      await mutation(
        {
          image: image.id,
          alt_bn: image.alt_bn,
          alt_en: image.alt_en,
          variant_id: image.variant_id,
        },
        (key) =>
          api.updateProductImage(
            id,
            image.id,
            { alt_bn: image.alt_bn, alt_en: image.alt_en, variant_id: image.variant_id },
            requireAdminEtag(detail.data?.etag ?? null),
            key,
          ),
      );
      detail.reload();
      toast.push(t("toast.saved"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  if (id && detail.loading) return <AdminLoading label={t("common.loading")} />;
  if (id && detail.error)
    return (
      <AdminLoadError
        error={detail.error}
        onRetry={detail.reload}
        retryLabel={t("common.retry")}
        title={t("common.loadError")}
      />
    );

  const product = detail.data?.data ?? null;
  const variants = product?.variants ?? [];
  const inputProps = (name: keyof AdminProductInput) =>
    fieldErrorProps(String(name), errors[String(name)]);

  return (
    <div className="grid gap-7">
      <AdminPageHeader
        description={t("products.activationHint")}
        eyebrow={product?.slug ?? t("products.new")}
        title={id ? t("products.detail") : t("products.new")}
      />
      <form className="grid gap-6" onSubmit={save}>
        <section className="grid gap-5 rounded-2xl border border-brand-purple/12 bg-white p-5 sm:grid-cols-2">
          {!id ? (
            <AdminField error={errors.slug} htmlFor="slug" label={t("common.slug")} required>
              <input
                {...inputProps("slug")}
                className={adminInputClass}
                id="slug"
                onChange={(event) => set("slug", event.target.value)}
                required
                value={input.slug ?? ""}
              />
            </AdminField>
          ) : null}
          <AdminField
            error={errors.category_id}
            htmlFor="category_id"
            label={t("products.category")}
            required
          >
            <select
              {...inputProps("category_id")}
              className={adminInputClass}
              id="category_id"
              onChange={(event) => set("category_id", event.target.value)}
              required
              value={input.category_id}
            >
              <option value="">—</option>
              {taxonomy.data?.categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {locale === "bn" ? category.name_bn : category.name_en}
                </option>
              ))}
            </select>
          </AdminField>
          <AdminField htmlFor="brand_id" label={t("products.brand")}>
            <select
              className={adminInputClass}
              id="brand_id"
              onChange={(event) => set("brand_id", event.target.value || null)}
              value={input.brand_id ?? ""}
            >
              <option value="">—</option>
              {taxonomy.data?.brands.map((brand) => (
                <option key={brand.id} value={brand.id}>
                  {brand.name}
                </option>
              ))}
            </select>
          </AdminField>
          <AdminField htmlFor="product_status" label={t("common.status")} required>
            <select
              className={adminInputClass}
              id="product_status"
              onChange={(event) => set("status", event.target.value as AdminProductInput["status"])}
              value={input.status}
            >
              <option value="draft">{t("common.draft")}</option>
              <option value="active">{t("common.active")}</option>
              <option value="archived">{t("common.archive")}</option>
            </select>
          </AdminField>
          <AdminField
            error={errors.name_bn}
            htmlFor="name_bn"
            label={t("content.titleBn")}
            required
          >
            <input
              {...inputProps("name_bn")}
              className={adminInputClass}
              id="name_bn"
              onChange={(event) => set("name_bn", event.target.value)}
              value={input.name_bn}
            />
          </AdminField>
          <AdminField
            error={errors.name_en}
            htmlFor="name_en"
            label={t("content.titleEn")}
            required
          >
            <input
              {...inputProps("name_en")}
              className={adminInputClass}
              id="name_en"
              onChange={(event) => set("name_en", event.target.value)}
              value={input.name_en}
            />
          </AdminField>
          <AdminField
            error={errors.description_bn}
            htmlFor="description_bn"
            label={`${t("common.description")} · ${t("common.bengali")}`}
            required
          >
            <textarea
              {...inputProps("description_bn")}
              className={adminTextareaClass}
              id="description_bn"
              onChange={(event) => set("description_bn", event.target.value)}
              value={input.description_bn}
            />
          </AdminField>
          <AdminField
            error={errors.description_en}
            htmlFor="description_en"
            label={`${t("common.description")} · ${t("common.english")}`}
            required
          >
            <textarea
              {...inputProps("description_en")}
              className={adminTextareaClass}
              id="description_en"
              onChange={(event) => set("description_en", event.target.value)}
              value={input.description_en}
            />
          </AdminField>
          <label className="flex min-h-12 items-center gap-3 rounded-xl border border-brand-purple/12 px-4 font-bold sm:col-span-2">
            <input
              checked={input.is_featured}
              onChange={(event) => set("is_featured", event.target.checked)}
              type="checkbox"
            />
            {t("products.featured")}
          </label>
        </section>
        <details className="rounded-2xl border border-brand-purple/12 bg-white p-5">
          <summary className="cursor-pointer font-black text-deep-indigo">
            {t("products.seo")}
          </summary>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {(
              ["seo_title_bn", "seo_title_en", "seo_description_bn", "seo_description_en"] as const
            ).map((key) => (
              <AdminField key={key} htmlFor={key} label={key.replaceAll("_", " ")}>
                <textarea
                  className={adminTextareaClass}
                  id={key}
                  onChange={(event) => set(key, event.target.value || null)}
                  value={input[key] ?? ""}
                />
              </AdminField>
            ))}
          </div>
        </details>
        {!id ? (
          <section className="grid gap-4 rounded-2xl border border-brand-purple/12 bg-white p-5 sm:grid-cols-3">
            <h2 className="text-xl font-extrabold sm:col-span-3">{t("products.variants")}</h2>
            <VariantFields
              optionsSource={JSON.stringify(input.variants?.[0]?.options ?? {})}
              setOptionsSource={(source) => {
                try {
                  const options = JSON.parse(source) as Record<string, string>;
                  set("variants", [{ ...(input.variants?.[0] ?? EMPTY_VARIANT), options }]);
                } catch {}
              }}
              setVariant={(variant) => set("variants", [variant])}
              t={t}
              variant={input.variants?.[0] ?? EMPTY_VARIANT}
            />
          </section>
        ) : null}
        <button
          className="signature-gradient inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-6 font-black text-white disabled:opacity-50 sm:justify-self-start"
          disabled={saving}
          type="submit"
        >
          <FloppyDisk aria-hidden size={20} /> {saving ? t("common.saving") : t("common.save")}
        </button>
      </form>

      {id && product ? (
        <section className="grid gap-5 rounded-2xl border border-brand-purple/12 bg-white p-5">
          <h2 className="text-2xl font-extrabold">{t("products.variants")}</h2>
          <ul className="grid gap-4">
            {variants.map((variant) => {
              const draft = stockDrafts[variant.id] ?? { quantity: "", reason: "" };
              const variantDraft = variantDrafts[variant.id];
              return (
                <li
                  key={variant.id}
                  className="grid gap-4 rounded-2xl bg-page-background p-4 lg:grid-cols-[1fr_auto]"
                >
                  <div className="grid gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong className="text-deep-indigo">{variant.sku}</strong>
                      <AdminStatusBadge status={variant.is_active ? "active" : "inactive"} />
                    </div>
                    <p className="mt-1 text-sm text-muted">{JSON.stringify(variant.options)}</p>
                    <p className="mt-2 text-sm font-bold">
                      {t("products.stockOnHand")}: {variant.stock_on_hand} ·{" "}
                      {t("products.stockReserved")}: {variant.stock_reserved}
                    </p>
                    {variantDraft ? (
                      <div className="grid gap-2 sm:grid-cols-3">
                        <input
                          aria-label={t("products.sku")}
                          className={adminInputClass}
                          disabled
                          value={variantDraft.sku}
                        />
                        <input
                          aria-label={t("products.price")}
                          className={adminInputClass}
                          min={1}
                          onChange={(event) =>
                            setVariantDrafts((current) => ({
                              ...current,
                              [variant.id]: {
                                ...variantDraft,
                                price_poisha: Number(event.target.value),
                              },
                            }))
                          }
                          type="number"
                          value={variantDraft.price_poisha}
                        />
                        <input
                          aria-label={t("products.comparePrice")}
                          className={adminInputClass}
                          min={0}
                          onChange={(event) =>
                            setVariantDrafts((current) => ({
                              ...current,
                              [variant.id]: {
                                ...variantDraft,
                                compare_at_price_poisha: event.target.value
                                  ? Number(event.target.value)
                                  : null,
                              },
                            }))
                          }
                          type="number"
                          value={variantDraft.compare_at_price_poisha ?? ""}
                        />
                        <input
                          aria-label={t("products.weight")}
                          className={adminInputClass}
                          min={1}
                          onChange={(event) =>
                            setVariantDrafts((current) => ({
                              ...current,
                              [variant.id]: {
                                ...variantDraft,
                                weight_g: Number(event.target.value),
                              },
                            }))
                          }
                          type="number"
                          value={variantDraft.weight_g}
                        />
                        <AdminField
                          error={errors[`variant_options_${variant.id}`]}
                          htmlFor={`variant-options-${variant.id}`}
                          label={t("products.options")}
                        >
                          <textarea
                            className={`${adminTextareaClass} min-h-24 font-mono text-xs`}
                            id={`variant-options-${variant.id}`}
                            onChange={(event) => {
                              const source = event.target.value;
                              setVariantOptionsSources((current) => ({
                                ...current,
                                [variant.id]: source,
                              }));
                              try {
                                const options = JSON.parse(source) as Record<string, string>;
                                setVariantDrafts((current) => ({
                                  ...current,
                                  [variant.id]: { ...variantDraft, options },
                                }));
                                setErrors((current) => ({
                                  ...current,
                                  [`variant_options_${variant.id}`]: "",
                                }));
                              } catch {
                                setErrors((current) => ({
                                  ...current,
                                  [`variant_options_${variant.id}`]: t("common.fieldError"),
                                }));
                              }
                            }}
                            value={variantOptionsSources[variant.id] ?? "{}"}
                          />
                        </AdminField>
                        <label className="flex min-h-11 items-center gap-2 font-bold">
                          <input
                            checked={variantDraft.is_active}
                            onChange={(event) =>
                              setVariantDrafts((current) => ({
                                ...current,
                                [variant.id]: { ...variantDraft, is_active: event.target.checked },
                              }))
                            }
                            type="checkbox"
                          />
                          {t("products.variantActive")}
                        </label>
                        <button
                          className="min-h-11 rounded-xl border border-brand-purple/20 px-4 font-black text-brand-purple"
                          disabled={Boolean(errors[`variant_options_${variant.id}`])}
                          onClick={() => void saveVariant(variant)}
                          type="button"
                        >
                          {t("common.save")}
                        </button>
                        <button
                          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-error/20 px-4 font-black text-error"
                          disabled={!variant.is_active}
                          onClick={() => void archiveVariant(variant)}
                          type="button"
                        >
                          <Trash aria-hidden size={18} />
                          {t("common.archive")}
                        </button>
                      </div>
                    ) : null}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-[7rem_minmax(10rem,1fr)_auto]">
                    <input
                      aria-label={t("products.quantityDelta")}
                      className={adminInputClass}
                      onChange={(event) =>
                        setStockDrafts((current) => ({
                          ...current,
                          [variant.id]: { ...draft, quantity: event.target.value },
                        }))
                      }
                      placeholder="+5 / -2"
                      type="number"
                      value={draft.quantity}
                    />
                    <input
                      aria-label={t("common.reason")}
                      className={adminInputClass}
                      onChange={(event) =>
                        setStockDrafts((current) => ({
                          ...current,
                          [variant.id]: { ...draft, reason: event.target.value },
                        }))
                      }
                      placeholder={t("common.reason")}
                      value={draft.reason}
                    />
                    <button
                      className="min-h-11 rounded-xl bg-deep-indigo px-4 font-black text-white disabled:opacity-45"
                      disabled={!draft.quantity || !draft.reason.trim()}
                      onClick={() => void adjustStock(variant)}
                      type="button"
                    >
                      {t("products.adjustStock")}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          <form
            className="grid gap-4 rounded-2xl border border-dashed border-brand-purple/25 p-4 sm:grid-cols-3"
            onSubmit={addVariant}
          >
            <h3 className="text-xl font-extrabold sm:col-span-3">{t("products.addVariant")}</h3>
            <VariantFields
              optionsSource={optionsSource}
              setOptionsSource={setOptionsSource}
              setVariant={setNewVariant}
              t={t}
              variant={newVariant}
            />
            <button
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-deep-indigo px-4 font-black text-white sm:col-span-3 sm:justify-self-start"
              type="submit"
            >
              <Plus aria-hidden size={18} /> {t("products.addVariant")}
            </button>
          </form>
        </section>
      ) : null}

      <section className="grid gap-5 rounded-2xl border border-brand-purple/12 bg-white p-5">
        <h2 className="text-2xl font-extrabold">{t("products.images")}</h2>
        {errors.images ? (
          <p className="font-bold text-error" role="alert">
            {errors.images}
          </p>
        ) : null}
        <MediaUploader
          onUploaded={(asset: AdminMediaAsset) => setAssetId(asset.id)}
          purpose="product"
        />
        {assetId ? (
          <p className="rounded-xl bg-success/10 p-3 font-mono text-xs text-success">{assetId}</p>
        ) : null}
        <form className="grid gap-4 sm:grid-cols-3" onSubmit={attachImage}>
          <AdminField htmlFor="image-asset-id" label={t("common.assetId")} required>
            <input
              className={adminInputClass}
              id="image-asset-id"
              onChange={(event) => setAssetId(event.target.value)}
              required
              value={assetId}
            />
          </AdminField>
          <AdminField htmlFor="image-alt-bn" label={t("products.altBn")} required>
            <input
              className={adminInputClass}
              id="image-alt-bn"
              onChange={(event) => setAltBn(event.target.value)}
              required
              value={altBn}
            />
          </AdminField>
          <AdminField htmlFor="image-alt-en" label={t("products.altEn")} required>
            <input
              className={adminInputClass}
              id="image-alt-en"
              onChange={(event) => setAltEn(event.target.value)}
              required
              value={altEn}
            />
          </AdminField>
          {id ? (
            <AdminField htmlFor="image-variant" label={t("products.imageVariant")}>
              <select
                className={adminInputClass}
                id="image-variant"
                onChange={(event) => setImageVariantId(event.target.value)}
                value={imageVariantId}
              >
                <option value="">{t("products.allVariants")}</option>
                {variants.map((variant) => (
                  <option key={variant.id} value={variant.id}>
                    {variant.sku}
                  </option>
                ))}
              </select>
            </AdminField>
          ) : null}
          <button
            className="min-h-11 rounded-xl bg-deep-indigo px-4 font-black text-white sm:col-span-3 sm:justify-self-start"
            type="submit"
          >
            {id ? t("products.addImage") : t("common.save")}
          </button>
        </form>
        {images.length ? (
          <>
            <KeyboardSortableList
              itemKey={(image) => image.id}
              items={images}
              labels={{
                moveUp: t("common.moveUp"),
                moveDown: t("common.moveDown"),
                drag: t("common.dragToReorder"),
                moved: t("common.movedToPosition"),
              }}
              onReorder={setImages}
              render={(image) => (
                <div className="flex items-center gap-3">
                  <Image
                    alt={locale === "bn" ? image.alt_bn : image.alt_en}
                    className="size-20 rounded-xl object-cover"
                    height={80}
                    src={image.url}
                    unoptimized
                    width={80}
                  />
                  <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-2">
                    <input
                      aria-label={t("products.altBn")}
                      className={adminInputClass}
                      onChange={(event) =>
                        setImages((current) =>
                          current.map((item) =>
                            item.id === image.id ? { ...item, alt_bn: event.target.value } : item,
                          ),
                        )
                      }
                      value={image.alt_bn}
                    />
                    <input
                      aria-label={t("products.altEn")}
                      className={adminInputClass}
                      onChange={(event) =>
                        setImages((current) =>
                          current.map((item) =>
                            item.id === image.id ? { ...item, alt_en: event.target.value } : item,
                          ),
                        )
                      }
                      value={image.alt_en}
                    />
                    <p className="font-mono text-xs text-muted sm:col-span-2">{image.id}</p>
                    <select
                      aria-label={t("products.imageVariant")}
                      className={`${adminInputClass} sm:col-span-2`}
                      onChange={(event) =>
                        setImages((current) =>
                          current.map((item) =>
                            item.id === image.id
                              ? { ...item, variant_id: event.target.value || null }
                              : item,
                          ),
                        )
                      }
                      value={image.variant_id ?? ""}
                    >
                      <option value="">{t("products.allVariants")}</option>
                      {variants.map((variant) => (
                        <option key={variant.id} value={variant.id}>
                          {variant.sku}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    className="min-h-11 rounded-xl border border-brand-purple/15 px-3 font-black text-brand-purple"
                    onClick={() => void saveImageAlt(image)}
                    type="button"
                  >
                    {t("common.save")}
                  </button>
                  <button
                    aria-label={t("common.delete")}
                    className="grid size-11 place-items-center rounded-xl text-error hover:bg-error/10"
                    onClick={() =>
                      void mutation({ image: image.id }, (key) =>
                        api.deleteProductImage(
                          id!,
                          image.id,
                          requireAdminEtag(detail.data?.etag ?? null),
                          key,
                        ),
                      )
                        .then(() => detail.reload())
                        .catch((caught) =>
                          isAdminStaleWrite(caught)
                            ? setStale(true)
                            : toast.push(t("toast.error"), "error"),
                        )
                    }
                    type="button"
                  >
                    <Trash aria-hidden size={19} />
                  </button>
                </div>
              )}
            />
            <button
              className="min-h-11 rounded-xl border border-brand-purple/20 px-4 font-black text-deep-indigo sm:justify-self-start"
              onClick={() => void saveImageOrder()}
              type="button"
            >
              {t("common.save")}
            </button>
          </>
        ) : null}
      </section>
      <StaleRecordDialog onClose={() => setStale(false)} onReload={detail.reload} open={stale} />
    </div>
  );
}

function VariantFields({
  variant,
  setVariant,
  optionsSource,
  setOptionsSource,
  t,
}: {
  variant: AdminProductVariantInput;
  setVariant: (variant: AdminProductVariantInput) => void;
  optionsSource: string;
  setOptionsSource: (source: string) => void;
  t: ReturnType<typeof useTranslations<"admin">>;
}) {
  return (
    <>
      <AdminField htmlFor={`sku-${variant.sku}`} label={t("products.sku")} required>
        <input
          className={adminInputClass}
          id={`sku-${variant.sku}`}
          onChange={(event) => setVariant({ ...variant, sku: event.target.value })}
          required
          value={variant.sku}
        />
      </AdminField>
      <AdminField htmlFor={`options-${variant.sku}`} label={t("products.options")} required>
        <input
          className={`${adminInputClass} font-mono text-xs`}
          id={`options-${variant.sku}`}
          onChange={(event) => setOptionsSource(event.target.value)}
          required
          value={optionsSource}
        />
      </AdminField>
      <AdminField
        htmlFor={`price-${variant.sku}`}
        label={`${t("products.price")} (poisha)`}
        required
      >
        <input
          className={adminInputClass}
          id={`price-${variant.sku}`}
          min={1}
          onChange={(event) => setVariant({ ...variant, price_poisha: Number(event.target.value) })}
          required
          type="number"
          value={variant.price_poisha}
        />
      </AdminField>
      <AdminField htmlFor={`compare-${variant.sku}`} label={t("products.comparePrice")}>
        <input
          className={adminInputClass}
          id={`compare-${variant.sku}`}
          min={0}
          onChange={(event) =>
            setVariant({
              ...variant,
              compare_at_price_poisha: event.target.value ? Number(event.target.value) : null,
            })
          }
          type="number"
          value={variant.compare_at_price_poisha ?? ""}
        />
      </AdminField>
      <AdminField htmlFor={`stock-${variant.sku}`} label={t("products.stockOnHand")} required>
        <input
          className={adminInputClass}
          id={`stock-${variant.sku}`}
          min={0}
          onChange={(event) =>
            setVariant({ ...variant, stock_on_hand: Number(event.target.value) })
          }
          required
          type="number"
          value={variant.stock_on_hand ?? 0}
        />
      </AdminField>
      <AdminField htmlFor={`weight-${variant.sku}`} label={t("products.weight")} required>
        <input
          className={adminInputClass}
          id={`weight-${variant.sku}`}
          min={1}
          onChange={(event) => setVariant({ ...variant, weight_g: Number(event.target.value) })}
          required
          type="number"
          value={variant.weight_g}
        />
      </AdminField>
    </>
  );
}
