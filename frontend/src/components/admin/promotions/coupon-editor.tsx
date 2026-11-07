"use client";

import { FloppyDisk, Trash } from "@phosphor-icons/react";
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
import type { AdminCouponInput } from "@/lib/admin/types";
import { validateCoupon } from "@/lib/admin/validation";

import { AdminField, adminInputClass, fieldErrorProps } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { useAdminToast } from "../ui/toast";

type CouponDraft = Omit<AdminCouponInput, "starts_at" | "ends_at"> & {
  starts_at: string;
  ends_at: string;
};

const EMPTY: CouponDraft = {
  code: "",
  type: "percent",
  value: 10,
  min_subtotal_poisha: 0,
  max_discount_poisha: null,
  usage_limit: null,
  per_user_limit: 1,
  starts_at: "",
  ends_at: "",
  is_active: true,
  is_discoverable: false,
};

function localDateTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function CouponEditor({ id, locale }: { id: string | null; locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const router = useRouter();
  const mutate = useAdminMutation(id ? `coupon:${id}` : "coupon-create");
  const query = useAdminQuery(
    (signal) => (id ? api.coupon(id, signal) : Promise.resolve(null)),
    [api, id],
  );
  const [input, setInput] = useState<CouponDraft>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    if (!query.data) return;
    const coupon = query.data.data;
    const value: CouponDraft = {
      code: coupon.code,
      type: coupon.type,
      value: coupon.value,
      min_subtotal_poisha: coupon.min_subtotal_poisha,
      max_discount_poisha: coupon.max_discount_poisha,
      usage_limit: coupon.usage_limit,
      per_user_limit: coupon.per_user_limit,
      starts_at: localDateTime(coupon.starts_at),
      ends_at: localDateTime(coupon.ends_at),
      is_active: coupon.is_active,
      is_discoverable: coupon.is_discoverable,
    };
    queueMicrotask(() => setInput(value));
  }, [query.data]);

  function set<K extends keyof CouponDraft>(key: K, value: CouponDraft[K]) {
    setInput((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: "" }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload: AdminCouponInput = {
      ...input,
      code: input.code.trim().toUpperCase(),
      starts_at: input.starts_at ? new Date(input.starts_at).toISOString() : null,
      ends_at: input.ends_at ? new Date(input.ends_at).toISOString() : null,
    };
    const validation = validateCoupon(payload);
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
          ? api.updateCoupon(id, payload, requireAdminEtag(query.data?.etag ?? null), key)
          : api.createCoupon(payload, key),
      );
      toast.push(id ? t("toast.saved") : t("toast.created"));
      if (!id) router.replace(`/${locale}/admin/coupons/${result.data.id}`);
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
                  api.deleteCoupon(id, requireAdminEtag(query.data?.etag ?? null), key),
                )
                  .then(() => {
                    toast.push(t("toast.deleted"));
                    router.replace(`/${locale}/admin/coupons`);
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
        description={t("coupons.description")}
        title={id ? input.code || t("common.edit") : t("coupons.new")}
      />
      <form
        className="grid gap-5 rounded-2xl border border-brand-purple/12 bg-white p-5 sm:grid-cols-2"
        onSubmit={submit}
      >
        <AdminField error={errors.code} htmlFor="coupon-code" label={t("coupons.code")} required>
          <input
            {...fieldErrorProps("coupon-code", errors.code)}
            autoCapitalize="characters"
            className={adminInputClass}
            disabled={Boolean(id)}
            id="coupon-code"
            onChange={(event) => set("code", event.target.value.toUpperCase())}
            required
            value={input.code}
          />
        </AdminField>
        <AdminField htmlFor="coupon-type" label={t("coupons.type")} required>
          <select
            className={adminInputClass}
            disabled={Boolean(id)}
            id="coupon-type"
            onChange={(event) => set("type", event.target.value as AdminCouponInput["type"])}
            value={input.type}
          >
            <option value="percent">{t("coupons.percent")}</option>
            <option value="fixed">{t("coupons.fixed")}</option>
            <option value="free_shipping">{t("coupons.freeShipping")}</option>
          </select>
        </AdminField>
        <NumberField
          error={errors.value}
          id="discount-value"
          label={t("coupons.value")}
          onChange={(value) => set("value", value ?? 0)}
          value={input.value}
        />
        <NumberField
          error={errors.max_discount_poisha}
          id="max-discount"
          label={t("coupons.maxDiscount")}
          nullable
          onChange={(value) => set("max_discount_poisha", value)}
          value={input.max_discount_poisha ?? null}
        />
        <NumberField
          error={errors.min_subtotal_poisha}
          id="minimum-order"
          label={t("coupons.minimumOrder")}
          onChange={(value) => set("min_subtotal_poisha", value ?? 0)}
          value={input.min_subtotal_poisha}
        />
        <NumberField
          id="usage-limit"
          label={t("coupons.usageLimit")}
          nullable
          onChange={(value) => set("usage_limit", value)}
          value={input.usage_limit ?? null}
        />
        <NumberField
          id="per-user-limit"
          label={t("coupons.perUserLimit")}
          onChange={(value) => set("per_user_limit", value ?? 1)}
          value={input.per_user_limit}
        />
        <AdminField error={errors.starts_at} htmlFor="coupon-start" label={t("common.startsAt")}>
          <input
            {...fieldErrorProps("coupon-start", errors.starts_at)}
            className={adminInputClass}
            id="coupon-start"
            onChange={(event) => set("starts_at", event.target.value)}
            type="datetime-local"
            value={input.starts_at}
          />
        </AdminField>
        <AdminField error={errors.ends_at} htmlFor="coupon-end" label={t("common.endsAt")}>
          <input
            {...fieldErrorProps("coupon-end", errors.ends_at)}
            className={adminInputClass}
            id="coupon-end"
            onChange={(event) => set("ends_at", event.target.value)}
            type="datetime-local"
            value={input.ends_at}
          />
        </AdminField>
        <label className="flex min-h-12 items-center gap-3 rounded-xl border px-4 font-bold">
          <input
            checked={input.is_active}
            onChange={(event) => set("is_active", event.target.checked)}
            type="checkbox"
          />
          {t("common.active")}
        </label>
        <label className="flex min-h-12 items-center gap-3 rounded-xl border px-4 font-bold">
          <input
            checked={input.is_discoverable}
            onChange={(event) => set("is_discoverable", event.target.checked)}
            type="checkbox"
          />
          {t("common.discoverable")}
        </label>
        <button
          className="signature-gradient inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-6 font-black text-white disabled:opacity-45 sm:col-span-2 sm:justify-self-start"
          disabled={busy}
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

function NumberField({
  id,
  label,
  value,
  onChange,
  nullable,
  error,
}: {
  id: string;
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  nullable?: boolean;
  error?: string;
}) {
  return (
    <AdminField error={error} htmlFor={id} label={label} required={!nullable}>
      <input
        {...fieldErrorProps(id, error)}
        className={adminInputClass}
        id={id}
        min={0}
        onChange={(event) =>
          onChange(event.target.value === "" && nullable ? null : Number(event.target.value))
        }
        required={!nullable}
        type="number"
        value={value ?? ""}
      />
    </AdminField>
  );
}
