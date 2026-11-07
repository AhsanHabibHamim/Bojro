"use client";

import { FloppyDisk, Plus, Trash } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import {
  isAdminStaleWrite,
  requireAdminEtag,
  useAdminApi,
  useAdminMutation,
  useAdminQuery,
} from "@/lib/admin/context";
import type { AdminFlashSaleInput } from "@/lib/admin/types";
import { validateFlashSale } from "@/lib/admin/validation";

import { AdminField, adminInputClass, fieldErrorProps } from "../ui/form-field";
import { AdminDialog } from "../ui/dialog";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { useAdminToast } from "../ui/toast";

const EMPTY: AdminFlashSaleInput = {
  name_bn: "",
  name_en: "",
  starts_at: "",
  ends_at: "",
  is_active: true,
  items: [{ variant_id: "", sale_price_poisha: 0, quantity_limit: 1 }],
};

function localDateTime(iso: string): string {
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

export function FlashSaleEditor({ id, locale }: { id: string | null; locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const router = useRouter();
  const mutate = useAdminMutation(id ? `flash-sale:${id}` : "flash-sale-create");
  const query = useAdminQuery(
    (signal) => (id ? api.flashSale(id, signal) : Promise.resolve(null)),
    [api, id],
  );
  const [input, setInput] = useState(EMPTY);
  const [sold, setSold] = useState<Record<string, number>>({});
  const [rowIds, setRowIds] = useState(["new-0"]);
  const [pickerIndex, setPickerIndex] = useState<number | null>(null);
  const [productSearch, setProductSearch] = useState("");
  const [pickerProductId, setPickerProductId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const productResults = useAdminQuery(
    (signal) =>
      pickerIndex === null
        ? Promise.resolve(null)
        : api.products({ q: productSearch || undefined, status: "active", limit: 25 }, signal),
    [api, pickerIndex, productSearch],
  );
  const pickerProduct = useAdminQuery(
    (signal) => (pickerProductId ? api.product(pickerProductId, signal) : Promise.resolve(null)),
    [api, pickerProductId],
  );

  useEffect(() => {
    if (!query.data) return;
    const value = query.data.data;
    const next = {
      name_bn: value.name_bn,
      name_en: value.name_en,
      starts_at: localDateTime(value.starts_at),
      ends_at: localDateTime(value.ends_at),
      is_active: value.is_active,
      items: value.items.map((item) => ({
        variant_id: item.variant_id,
        sale_price_poisha: item.sale_price_poisha,
        quantity_limit: item.quantity_limit,
      })),
    };
    const nextSold = Object.fromEntries(
      value.items.map((item) => [item.variant_id, item.sold_quantity]),
    );
    queueMicrotask(() => {
      setInput(next);
      setSold(nextSold);
      setRowIds(value.items.map((item) => item.id));
    });
  }, [query.data]);

  function setItem(
    index: number,
    key: keyof AdminFlashSaleInput["items"][number],
    value: string | number,
  ) {
    setInput((current) => ({
      ...current,
      items: current.items.map((item, itemIndex) =>
        itemIndex === index ? { ...item, [key]: value } : item,
      ),
    }));
  }

  function addItem() {
    setInput((current) => ({
      ...current,
      items: [...current.items, { variant_id: "", sale_price_poisha: 0, quantity_limit: 1 }],
    }));
    setRowIds((current) => [...current, crypto.randomUUID()]);
  }

  function removeItem(index: number) {
    setInput((current) => ({
      ...current,
      items: current.items.filter((_, itemIndex) => itemIndex !== index),
    }));
    setRowIds((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }

  function chooseVariant(variantId: string, pricePoisha: number) {
    if (pickerIndex === null) return;
    setItem(pickerIndex, "variant_id", variantId);
    if (!input.items[pickerIndex]?.sale_price_poisha) {
      setItem(pickerIndex, "sale_price_poisha", pricePoisha);
    }
    setPickerIndex(null);
    setPickerProductId(null);
    setProductSearch("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = {
      ...input,
      starts_at: new Date(input.starts_at).toISOString(),
      ends_at: new Date(input.ends_at).toISOString(),
    };
    const validation = validateFlashSale(payload);
    input.items.forEach((item, index) => {
      if (item.quantity_limit < (sold[item.variant_id] ?? 0))
        validation[`items.${index}.quantity_limit`] = "QUANTITY_BELOW_SOLD";
    });
    if (Object.keys(validation).length) {
      setErrors(
        Object.fromEntries(Object.keys(validation).map((field) => [field, t("common.fieldError")])),
      );
      return;
    }
    setBusy(true);
    try {
      const result = await mutate(payload, (key) =>
        id
          ? api.updateFlashSale(id, payload, requireAdminEtag(query.data?.etag ?? null), key)
          : api.createFlashSale(payload, key),
      );
      toast.push(id ? t("toast.saved") : t("toast.created"));
      if (!id) router.replace(`/${locale}/admin/flash-sales/${result.data.id}`);
      else query.reload();
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    } finally {
      setBusy(false);
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

  return (
    <div className="grid gap-6">
      <AdminPageHeader
        actions={
          id ? (
            <button
              className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-error/20 px-4 font-black text-error"
              onClick={() =>
                void mutate({ id }, (key) =>
                  api.deleteFlashSale(id, requireAdminEtag(query.data?.etag ?? null), key),
                )
                  .then(() => {
                    toast.push(t("toast.deleted"));
                    router.replace(`/${locale}/admin/flash-sales`);
                  })
                  .catch((caught) =>
                    isAdminStaleWrite(caught)
                      ? setStale(true)
                      : toast.push(t("toast.error"), "error"),
                  )
              }
              type="button"
            >
              <Trash aria-hidden size={18} />
              {t("common.delete")}
            </button>
          ) : undefined
        }
        description={t("flashSales.description")}
        title={
          id
            ? (locale === "bn" ? input.name_bn : input.name_en) || t("common.edit")
            : t("flashSales.new")
        }
      />
      <form className="grid gap-6" onSubmit={submit}>
        <section className="grid gap-4 rounded-2xl border border-brand-purple/12 bg-white p-5 sm:grid-cols-2">
          <AdminField
            error={errors.name_bn}
            htmlFor="flash-name-bn"
            label={t("content.titleBn")}
            required
          >
            <input
              {...fieldErrorProps("flash-name-bn", errors.name_bn)}
              className={adminInputClass}
              id="flash-name-bn"
              onChange={(event) =>
                setInput((current) => ({ ...current, name_bn: event.target.value }))
              }
              required
              value={input.name_bn}
            />
          </AdminField>
          <AdminField
            error={errors.name_en}
            htmlFor="flash-name-en"
            label={t("content.titleEn")}
            required
          >
            <input
              {...fieldErrorProps("flash-name-en", errors.name_en)}
              className={adminInputClass}
              id="flash-name-en"
              onChange={(event) =>
                setInput((current) => ({ ...current, name_en: event.target.value }))
              }
              required
              value={input.name_en}
            />
          </AdminField>
          <AdminField htmlFor="flash-start" label={t("common.startsAt")} required>
            <input
              className={adminInputClass}
              id="flash-start"
              onChange={(event) =>
                setInput((current) => ({ ...current, starts_at: event.target.value }))
              }
              required
              type="datetime-local"
              value={input.starts_at}
            />
          </AdminField>
          <AdminField
            error={errors.ends_at}
            htmlFor="flash-end"
            label={t("common.endsAt")}
            required
          >
            <input
              {...fieldErrorProps("flash-end", errors.ends_at)}
              className={adminInputClass}
              id="flash-end"
              onChange={(event) =>
                setInput((current) => ({ ...current, ends_at: event.target.value }))
              }
              required
              type="datetime-local"
              value={input.ends_at}
            />
          </AdminField>
          <label className="flex min-h-12 items-center gap-3 rounded-xl border border-brand-purple/12 px-4 font-bold sm:col-span-2">
            <input
              checked={input.is_active}
              onChange={(event) =>
                setInput((current) => ({ ...current, is_active: event.target.checked }))
              }
              type="checkbox"
            />
            {t("common.active")}
          </label>
        </section>
        <section className="grid gap-4 rounded-2xl border border-brand-purple/12 bg-white p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-xl font-extrabold">{t("flashSales.items")}</h2>
            <button
              className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/15 px-4 font-black text-brand-purple"
              onClick={addItem}
              type="button"
            >
              <Plus aria-hidden size={18} />
              {t("flashSales.addItem")}
            </button>
          </div>
          {errors.items ? <p className="font-bold text-error">{errors.items}</p> : null}
          <ul className="grid gap-4">
            {input.items.map((item, index) => (
              <li
                key={rowIds[index] ?? `existing-${index}`}
                className="grid gap-3 rounded-xl bg-page-background p-4 sm:grid-cols-[1fr_10rem_10rem_auto]"
              >
                <AdminField
                  error={errors[`items.${index}.variant_id`]}
                  htmlFor={`flash-variant-${index}`}
                  label={t("flashSales.variantId")}
                  required
                >
                  <input
                    className={adminInputClass}
                    id={`flash-variant-${index}`}
                    readOnly
                    required
                    value={item.variant_id}
                  />
                  <button
                    className="mt-2 min-h-11 rounded-xl border border-brand-purple/20 px-4 font-bold text-brand-purple"
                    onClick={() => {
                      setPickerIndex(index);
                      setPickerProductId(null);
                    }}
                    type="button"
                  >
                    {t("flashSales.chooseVariant")}
                  </button>
                </AdminField>
                <AdminField
                  error={errors[`items.${index}.sale_price_poisha`]}
                  htmlFor={`flash-price-${index}`}
                  label={t("flashSales.salePrice")}
                  required
                >
                  <input
                    className={adminInputClass}
                    id={`flash-price-${index}`}
                    min={1}
                    onChange={(event) =>
                      setItem(index, "sale_price_poisha", Number(event.target.value))
                    }
                    required
                    type="number"
                    value={item.sale_price_poisha}
                  />
                </AdminField>
                <AdminField
                  error={errors[`items.${index}.quantity_limit`]}
                  hint={
                    sold[item.variant_id]
                      ? `${t("flashSales.sold")}: ${sold[item.variant_id]}`
                      : undefined
                  }
                  htmlFor={`flash-quantity-${index}`}
                  label={t("flashSales.quantityLimit")}
                  required
                >
                  <input
                    className={adminInputClass}
                    id={`flash-quantity-${index}`}
                    min={Math.max(1, sold[item.variant_id] ?? 1)}
                    onChange={(event) =>
                      setItem(index, "quantity_limit", Number(event.target.value))
                    }
                    required
                    type="number"
                    value={item.quantity_limit}
                  />
                </AdminField>
                <button
                  aria-label={t("common.delete")}
                  className="grid size-11 self-end place-items-center rounded-xl text-error hover:bg-error/10 disabled:opacity-40"
                  disabled={input.items.length === 1}
                  onClick={() => removeItem(index)}
                  type="button"
                >
                  <Trash aria-hidden size={18} />
                </button>
              </li>
            ))}
          </ul>
        </section>
        <button
          className="signature-gradient inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-6 font-black text-white disabled:opacity-45 sm:justify-self-start"
          disabled={busy}
          type="submit"
        >
          <FloppyDisk aria-hidden size={20} />
          {busy ? t("common.saving") : t("common.save")}
        </button>
      </form>
      <AdminDialog
        closeLabel={t("common.close")}
        onClose={() => {
          setPickerIndex(null);
          setPickerProductId(null);
        }}
        open={pickerIndex !== null}
        title={t("flashSales.chooseVariant")}
      >
        <div className="grid gap-4">
          <AdminField htmlFor="flash-product-search" label={t("flashSales.searchProducts")}>
            <input
              className={adminInputClass}
              id="flash-product-search"
              onChange={(event) => setProductSearch(event.target.value)}
              type="search"
              value={productSearch}
            />
          </AdminField>
          {!pickerProductId ? (
            <ul className="grid gap-2">
              {productResults.data?.items.map((product) => (
                <li key={product.id}>
                  <button
                    className="flex min-h-12 w-full items-center justify-between gap-3 rounded-xl border border-brand-purple/12 px-4 text-left font-bold hover:bg-soft-lavender"
                    onClick={() => setPickerProductId(product.id)}
                    type="button"
                  >
                    <span>{locale === "bn" ? product.name_bn : product.name_en}</span>
                    <span className="text-xs text-muted">{product.variant_count}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="grid gap-3">
              <button
                className="min-h-11 justify-self-start rounded-xl px-3 font-bold text-brand-purple"
                onClick={() => setPickerProductId(null)}
                type="button"
              >
                {t("common.back")}
              </button>
              <ul className="grid gap-2">
                {pickerProduct.data?.data.variants
                  .filter((variant) => variant.is_active)
                  .map((variant) => (
                    <li key={variant.id}>
                      <button
                        className="grid min-h-12 w-full grid-cols-[1fr_auto] gap-3 rounded-xl border border-brand-purple/12 px-4 py-3 text-left hover:bg-soft-lavender"
                        onClick={() => chooseVariant(variant.id, variant.price_poisha)}
                        type="button"
                      >
                        <span>
                          <strong>{variant.sku}</strong>
                          <span className="mt-1 block text-xs text-muted">
                            {JSON.stringify(variant.options)}
                          </span>
                        </span>
                        <span className="text-sm font-bold tabular-nums">
                          {t("products.stock")}: {variant.available_stock}
                        </span>
                      </button>
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </div>
      </AdminDialog>
      <StaleRecordDialog onClose={() => setStale(false)} onReload={query.reload} open={stale} />
    </div>
  );
}
