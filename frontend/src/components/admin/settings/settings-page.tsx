"use client";

import { FloppyDisk } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import {
  isAdminStaleWrite,
  requireAdminEtag,
  useAdminApi,
  useAdminMutation,
  useAdminQuery,
} from "@/lib/admin/context";
import type { SettingSection } from "@/lib/admin/types";

import { MediaUploader } from "../media/media-uploader";
import { AdminField, adminInputClass, adminTextareaClass } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { useAdminToast } from "../ui/toast";
import { CodRiskSettingsEditor, ShippingSettingsEditor } from "./typed-settings-editors";

const SECTIONS: SettingSection[] = [
  "branding",
  "contact",
  "whatsapp",
  "shipping",
  "payment_methods",
  "social_links",
  "analytics",
  "announcement",
  "cod_risk",
  "storefront_toggles",
];

type Field = {
  key: string;
  type: "text" | "email" | "url" | "number" | "boolean" | "textarea";
  required?: boolean;
};

const FIELDS: Record<SettingSection, Field[]> = {
  branding: [
    { key: "store_name_bn", type: "text", required: true },
    { key: "store_name_en", type: "text", required: true },
  ],
  contact: [
    { key: "phone", type: "text", required: true },
    { key: "email", type: "email", required: true },
    { key: "hours_bn", type: "text" },
    { key: "hours_en", type: "text" },
    { key: "address_bn", type: "textarea" },
    { key: "address_en", type: "textarea" },
  ],
  whatsapp: [
    { key: "enabled", type: "boolean" },
    { key: "phone", type: "text" },
    { key: "message_bn", type: "textarea" },
    { key: "message_en", type: "textarea" },
  ],
  shipping: [],
  payment_methods: [
    { key: "cod", type: "boolean" },
    { key: "bkash", type: "boolean" },
    { key: "nagad", type: "boolean" },
    { key: "sslcommerz", type: "boolean" },
  ],
  social_links: [
    { key: "facebook", type: "url" },
    { key: "instagram", type: "url" },
    { key: "youtube", type: "url" },
  ],
  analytics: [
    { key: "google_analytics_id", type: "text" },
    { key: "meta_pixel_id", type: "text" },
  ],
  announcement: [
    { key: "enabled", type: "boolean" },
    { key: "bn", type: "text" },
    { key: "en", type: "text" },
  ],
  cod_risk: [],
  storefront_toggles: [
    { key: "show_announcement", type: "boolean" },
    { key: "show_social_links", type: "boolean" },
    { key: "show_payment_methods", type: "boolean" },
  ],
};

export function SettingsPage({ locale }: { locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const router = useRouter();
  const search = useSearchParams();
  const requested = search.get("section") as SettingSection | null;
  const section = requested && SECTIONS.includes(requested) ? requested : "branding";
  const query = useAdminQuery((signal) => api.setting(section, signal), [api, section]);
  const mutate = useAdminMutation(`settings:${section}`);
  const [value, setValue] = useState<Record<string, unknown>>({});
  const [uploadedBrandAsset, setUploadedBrandAsset] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    if (query.data) {
      const next = query.data.data.value;
      queueMicrotask(() => {
        setValue(next);
      });
    }
  }, [query.data]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = value;
    const serializedPayload = JSON.stringify(payload);
    if (
      /"(?:secret|password|token|script|api_key)"\s*:/i.test(serializedPayload) ||
      /<\/?script|javascript:/i.test(serializedPayload)
    ) {
      toast.push(t("settings.noSecrets"), "error");
      return;
    }
    setBusy(true);
    try {
      await mutate(payload, (key) =>
        api.updateSetting(section, payload, requireAdminEtag(query.data?.etag ?? null), key),
      );
      query.reload();
      toast.push(t("toast.saved"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6">
      <AdminPageHeader description={t("settings.description")} title={t("settings.title")} />
      <div className="grid gap-5 xl:grid-cols-[16rem_minmax(0,1fr)]">
        <nav
          aria-label={t("settings.title")}
          className="grid content-start gap-1 rounded-2xl border border-brand-purple/12 bg-white p-2 sm:grid-cols-2 xl:grid-cols-1"
        >
          {SECTIONS.map((item) => (
            <button
              key={item}
              aria-current={item === section ? "page" : undefined}
              className={`min-h-11 rounded-xl px-3 text-left font-bold ${item === section ? "bg-deep-indigo text-white" : "text-deep-indigo hover:bg-soft-lavender"}`}
              onClick={() => router.replace(`/${locale}/admin/settings?section=${item}`)}
              type="button"
            >
              {t(`settings.${item}`)}
            </button>
          ))}
        </nav>
        <div>
          {query.loading ? <AdminLoading label={t("common.loading")} /> : null}
          {query.error ? (
            <AdminLoadError
              error={query.error}
              onRetry={query.reload}
              retryLabel={t("common.retry")}
              title={t("common.loadError")}
            />
          ) : null}
          {query.data ? (
            <form
              className="grid gap-5 rounded-2xl border border-brand-purple/12 bg-white p-5 sm:grid-cols-2"
              onSubmit={submit}
            >
              <h2 className="text-2xl font-extrabold sm:col-span-2">{t(`settings.${section}`)}</h2>
              <p className="rounded-xl bg-sale-amber/10 p-3 text-sm font-bold text-deep-indigo sm:col-span-2">
                {t("settings.noSecrets")}
              </p>
              {section === "shipping" ? (
                <ShippingSettingsEditor onChange={setValue} value={value} />
              ) : null}
              {section === "cod_risk" ? (
                <CodRiskSettingsEditor onChange={setValue} value={value} />
              ) : null}
              {section === "branding" ? (
                <div className="grid gap-4 rounded-xl border border-brand-purple/12 p-4 sm:col-span-2">
                  <MediaUploader
                    onUploaded={(asset) => setUploadedBrandAsset(asset.id)}
                    purpose="logo"
                  />
                  {uploadedBrandAsset ? (
                    <div className="flex flex-wrap items-center gap-2 rounded-xl bg-success/10 p-3">
                      <code className="min-w-0 flex-1 truncate text-xs">{uploadedBrandAsset}</code>
                      {(["logo_asset_id", "favicon_asset_id"] as const).map((field) => (
                        <button
                          className="min-h-11 rounded-xl border border-brand-purple/20 bg-white px-4 font-bold text-brand-purple"
                          key={field}
                          onClick={() => {
                            setValue((current) => ({ ...current, [field]: uploadedBrandAsset }));
                            setUploadedBrandAsset(null);
                          }}
                          type="button"
                        >
                          {t(`settingsFields.${field}`)}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {(["logo_asset_id", "favicon_asset_id"] as const).map((field) =>
                    value[field] ? (
                      <div
                        className="flex flex-wrap items-center gap-3 rounded-xl bg-page-background p-3"
                        key={field}
                      >
                        <strong>{t(`settingsFields.${field}`)}</strong>
                        <code className="min-w-0 flex-1 truncate text-xs">
                          {String(value[field])}
                        </code>
                        <button
                          className="min-h-11 rounded-xl border border-error/20 px-4 font-bold text-error"
                          onClick={() => setValue((current) => ({ ...current, [field]: null }))}
                          type="button"
                        >
                          {t("common.removeMedia")}
                        </button>
                      </div>
                    ) : null,
                  )}
                </div>
              ) : null}
              {FIELDS[section].map((field) => {
                const current = value[field.key];
                if (field.type === "boolean")
                  return (
                    <label
                      key={field.key}
                      className="flex min-h-12 items-center gap-3 rounded-xl border border-brand-purple/12 px-4 font-bold"
                    >
                      <input
                        checked={Boolean(current)}
                        onChange={(event) =>
                          setValue((values) => ({ ...values, [field.key]: event.target.checked }))
                        }
                        type="checkbox"
                      />
                      {t.has(`settingsFields.${field.key}` as never)
                        ? t(`settingsFields.${field.key}` as never)
                        : field.key.replaceAll("_", " ")}
                    </label>
                  );
                return (
                  <AdminField
                    key={field.key}
                    htmlFor={`setting-${field.key}`}
                    label={
                      t.has(`settingsFields.${field.key}` as never)
                        ? t(`settingsFields.${field.key}` as never)
                        : field.key.replaceAll("_", " ")
                    }
                    required={field.required}
                  >
                    {field.type === "textarea" ? (
                      <textarea
                        className={adminTextareaClass}
                        id={`setting-${field.key}`}
                        onChange={(event) =>
                          setValue((values) => ({
                            ...values,
                            [field.key]: event.target.value || null,
                          }))
                        }
                        required={field.required}
                        value={String(current ?? "")}
                      />
                    ) : (
                      <input
                        className={adminInputClass}
                        id={`setting-${field.key}`}
                        min={field.type === "number" ? 0 : undefined}
                        onChange={(event) =>
                          setValue((values) => ({
                            ...values,
                            [field.key]:
                              field.type === "number"
                                ? Number(event.target.value)
                                : event.target.value || null,
                          }))
                        }
                        required={field.required}
                        type={field.type}
                        value={current === null || current === undefined ? "" : String(current)}
                      />
                    )}
                  </AdminField>
                );
              })}
              <button
                className="signature-gradient inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-6 font-black text-white disabled:opacity-45 sm:col-span-2 sm:justify-self-start"
                disabled={busy}
                type="submit"
              >
                <FloppyDisk aria-hidden size={20} />
                {busy ? t("common.saving") : t("common.save")}
              </button>
            </form>
          ) : null}
        </div>
      </div>
      <StaleRecordDialog onClose={() => setStale(false)} onReload={query.reload} open={stale} />
    </div>
  );
}
