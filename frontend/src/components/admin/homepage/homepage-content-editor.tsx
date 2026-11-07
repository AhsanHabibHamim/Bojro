"use client";

import { Plus, Trash } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";

import type { HomepageSectionType } from "@/lib/admin/types";

import { AdminField, adminInputClass, adminTextareaClass } from "../ui/form-field";

type Content = Record<string, unknown>;
type ScalarField = {
  key: string;
  type: "text" | "textarea" | "number" | "boolean" | "lines";
};
type RowField = { key: string; type: "text" | "textarea" | "boolean" };

const COMMON: ScalarField[] = [
  { key: "eyebrow", type: "text" },
  { key: "title", type: "text" },
  { key: "cta", type: "text" },
];

const SCALARS: Partial<Record<HomepageSectionType, ScalarField[]>> = {
  hero: [
    { key: "description", type: "textarea" },
    { key: "primary_target", type: "text" },
  ],
  marquee: [
    { key: "items", type: "lines" },
    { key: "speed_seconds", type: "number" },
  ],
  flash_sale: [
    { key: "subtitle", type: "textarea" },
    { key: "view_all_target", type: "text" },
  ],
  best_seller_categories: [
    { key: "subtitle", type: "textarea" },
    { key: "max_items", type: "number" },
    { key: "view_all_target", type: "text" },
  ],
  best_selling: [
    { key: "subtitle", type: "textarea" },
    { key: "max_items", type: "number" },
    { key: "view_all_target", type: "text" },
  ],
  featured_category_band: [
    { key: "category", type: "text" },
    { key: "headline", type: "text" },
    { key: "description", type: "textarea" },
    { key: "target", type: "text" },
    { key: "image_asset_id", type: "text" },
  ],
  social_proof: [
    { key: "subtitle", type: "textarea" },
    { key: "gallery_asset_ids", type: "lines" },
  ],
  shipping_offer: [
    { key: "description", type: "textarea" },
    { key: "threshold_poisha", type: "number" },
    { key: "target", type: "text" },
    { key: "code", type: "text" },
  ],
  brand_story: [
    { key: "paragraphs", type: "lines" },
    { key: "image_asset_id", type: "text" },
    { key: "target", type: "text" },
  ],
  reviews: [
    { key: "subtitle", type: "textarea" },
    { key: "max_items", type: "number" },
    { key: "verified_badge_requires_order", type: "boolean" },
  ],
  deals: [
    { key: "subtitle", type: "textarea" },
    { key: "page_size", type: "number" },
    { key: "view_all_target", type: "text" },
  ],
  footer: [{ key: "description", type: "textarea" }],
};

const ROWS: Partial<Record<HomepageSectionType, { key: string; fields: RowField[] }>> = {
  hero: {
    key: "benefits",
    fields: [
      { key: "label", type: "text" },
      { key: "icon", type: "text" },
    ],
  },
  promo_chips: {
    key: "chips",
    fields: [
      { key: "label", type: "text" },
      { key: "target", type: "text" },
    ],
  },
  feature_bands: {
    key: "bands",
    fields: [
      { key: "title", type: "text" },
      { key: "description", type: "textarea" },
      { key: "target", type: "text" },
      { key: "image_asset_id", type: "text" },
    ],
  },
  comparison: {
    key: "rows",
    fields: [
      { key: "label", type: "text" },
      { key: "bojro", type: "boolean" },
      { key: "other", type: "boolean" },
    ],
  },
  social_proof: {
    key: "stats",
    fields: [
      { key: "value", type: "text" },
      { key: "label", type: "text" },
    ],
  },
};

export function HomepageContentEditor({
  id,
  sectionType,
  content,
  onChange,
}: {
  id: string;
  sectionType: HomepageSectionType;
  content: Content;
  onChange: (content: Content) => void;
}) {
  const t = useTranslations("admin.homepageFields");

  function label(key: string) {
    return t.has(key as never) ? t(key as never) : key.replaceAll("_", " ");
  }

  function set(key: string, value: unknown) {
    const next = { ...content };
    if (value === "" || value === null || (Array.isArray(value) && !value.length)) delete next[key];
    else next[key] = value;
    onChange(next);
  }

  const rowConfig = ROWS[sectionType];
  const rows = rowConfig
    ? ((content[rowConfig.key] as Array<Record<string, unknown>> | undefined) ?? [])
    : [];

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {[...COMMON, ...(SCALARS[sectionType] ?? [])].map((field) => {
        const fieldId = `${id}-${field.key}`;
        const value = content[field.key];
        if (field.type === "boolean") {
          return (
            <label
              key={field.key}
              className="flex min-h-12 items-center gap-3 rounded-xl border border-brand-purple/12 px-4 font-bold"
            >
              <input
                checked={Boolean(value)}
                onChange={(event) => set(field.key, event.target.checked)}
                type="checkbox"
              />
              {label(field.key)}
            </label>
          );
        }
        return (
          <AdminField htmlFor={fieldId} key={field.key} label={label(field.key)}>
            {field.type === "textarea" || field.type === "lines" ? (
              <textarea
                className={adminTextareaClass}
                id={fieldId}
                onChange={(event) =>
                  set(
                    field.key,
                    field.type === "lines"
                      ? event.target.value
                          .split("\n")
                          .map((item) => item.trim())
                          .filter(Boolean)
                      : event.target.value,
                  )
                }
                value={
                  field.type === "lines"
                    ? Array.isArray(value)
                      ? value.join("\n")
                      : ""
                    : String(value ?? "")
                }
              />
            ) : (
              <input
                className={adminInputClass}
                id={fieldId}
                min={field.type === "number" ? 0 : undefined}
                onChange={(event) =>
                  set(
                    field.key,
                    field.type === "number"
                      ? event.target.value
                        ? Number(event.target.value)
                        : null
                      : event.target.value,
                  )
                }
                type={field.type}
                value={value == null ? "" : String(value)}
              />
            )}
          </AdminField>
        );
      })}

      {sectionType === "flash_sale" ? (
        <label className="flex min-h-12 items-center gap-3 rounded-xl border border-brand-purple/12 px-4 font-bold">
          <input
            checked={Boolean((content.countdown as Record<string, unknown> | undefined)?.enabled)}
            onChange={(event) =>
              set("countdown", event.target.checked ? { enabled: true, source: "sale_end" } : null)
            }
            type="checkbox"
          />
          {label("countdown")}
        </label>
      ) : null}

      {rowConfig ? (
        <section className="grid gap-3 rounded-xl border border-brand-purple/12 p-4 sm:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <h4 className="font-extrabold">{label(rowConfig.key)}</h4>
            <button
              className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/15 px-4 font-bold text-brand-purple"
              onClick={() =>
                set(rowConfig.key, [
                  ...rows,
                  Object.fromEntries(
                    rowConfig.fields.map((field) => [
                      field.key,
                      field.type === "boolean" ? false : "",
                    ]),
                  ),
                ])
              }
              type="button"
            >
              <Plus aria-hidden size={18} /> {label("addItem")}
            </button>
          </div>
          {rows.map((row, index) => (
            <div
              className="grid gap-3 rounded-xl bg-page-background p-3 sm:grid-cols-2"
              key={`${rowConfig.key}-${index}`}
            >
              {rowConfig.fields.map((field) => (
                <AdminField
                  htmlFor={`${id}-${rowConfig.key}-${index}-${field.key}`}
                  key={field.key}
                  label={label(field.key)}
                >
                  {field.type === "boolean" ? (
                    <input
                      checked={Boolean(row[field.key])}
                      className="size-6"
                      id={`${id}-${rowConfig.key}-${index}-${field.key}`}
                      onChange={(event) =>
                        set(
                          rowConfig.key,
                          rows.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, [field.key]: event.target.checked }
                              : item,
                          ),
                        )
                      }
                      type="checkbox"
                    />
                  ) : (
                    <input
                      className={adminInputClass}
                      id={`${id}-${rowConfig.key}-${index}-${field.key}`}
                      onChange={(event) =>
                        set(
                          rowConfig.key,
                          rows.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, [field.key]: event.target.value }
                              : item,
                          ),
                        )
                      }
                      value={String(row[field.key] ?? "")}
                    />
                  )}
                </AdminField>
              ))}
              <button
                aria-label={label("removeItem")}
                className="grid size-11 place-items-center rounded-xl text-error hover:bg-error/10 sm:col-span-2"
                onClick={() =>
                  set(
                    rowConfig.key,
                    rows.filter((_, itemIndex) => itemIndex !== index),
                  )
                }
                type="button"
              >
                <Trash aria-hidden size={18} />
              </button>
            </div>
          ))}
        </section>
      ) : null}
    </div>
  );
}
