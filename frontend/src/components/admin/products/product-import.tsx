"use client";

import { CheckCircle, FileCsv, WarningCircle } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { useAdminApi, useAdminMutation } from "@/lib/admin/context";
import type { AdminCatalogImportResult } from "@/lib/admin/types";
import { PRODUCT_CSV_COLUMNS, validateProductCsvFile } from "@/lib/admin/validation";

import { AdminField, adminInputClass, fieldErrorProps } from "../ui/form-field";
import { AdminPageHeader } from "../ui/page-header";
import { useAdminToast } from "../ui/toast";

export function ProductImport() {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const validate = useAdminMutation("product-import-validate");
  const commit = useAdminMutation("product-import-commit");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AdminCatalogImportResult | null>(null);
  const [busy, setBusy] = useState<"validate" | "commit" | null>(null);

  async function validateFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    const localErrors = validateProductCsvFile(file);
    if (localErrors.file) {
      setError(t("common.fieldError"));
      return;
    }
    setBusy("validate");
    setError(null);
    try {
      const next = await validate({ file }, (key) => api.validateProductImport(file, key));
      setResult(next);
    } catch {
      setError(t("errors.generic"));
    } finally {
      setBusy(null);
    }
  }

  async function commitFile() {
    if (!file || result?.status !== "valid") return;
    setBusy("commit");
    setError(null);
    try {
      const next = await commit({ file }, (key) => api.commitProductImport(file, key));
      setResult(next);
      toast.push(t("toast.saved"));
    } catch {
      setError(t("errors.generic"));
      toast.push(t("toast.error"), "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-6">
      <AdminPageHeader description={t("products.csvDescription")} title={t("products.csvTitle")} />
      <form
        className="grid gap-5 rounded-2xl border border-brand-purple/12 bg-white p-5"
        onSubmit={validateFile}
      >
        <AdminField
          error={error}
          hint={t("products.csvDescription")}
          htmlFor="product-csv"
          label={t("products.chooseCsv")}
          required
        >
          <input
            {...fieldErrorProps("product-csv", error)}
            accept=".csv,text/csv"
            className={`${adminInputClass} file:mr-3 file:rounded-lg file:border-0 file:bg-soft-lavender file:px-3 file:py-2 file:font-bold file:text-brand-purple`}
            id="product-csv"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setResult(null);
              setError(null);
            }}
            required
            type="file"
          />
        </AdminField>
        <details className="rounded-xl bg-page-background p-4">
          <summary className="cursor-pointer font-black text-deep-indigo">
            {t("common.csvColumns")}
          </summary>
          <code className="mt-3 block overflow-x-auto text-xs break-all text-muted">
            {PRODUCT_CSV_COLUMNS.join(",")}
          </code>
        </details>
        <button
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-deep-indigo px-5 font-black text-white disabled:opacity-45 sm:justify-self-start"
          disabled={!file || busy !== null}
          type="submit"
        >
          <FileCsv aria-hidden size={20} />{" "}
          {busy === "validate" ? t("common.loading") : t("common.validate")}
        </button>
      </form>
      {result ? (
        <section
          className={`rounded-2xl border p-5 ${result.status === "valid" || result.status === "imported" ? "border-success/25 bg-success/5" : "border-error/25 bg-error/5"}`}
          aria-live="polite"
        >
          <div className="flex items-center gap-3">
            {result.status === "valid" || result.status === "imported" ? (
              <CheckCircle aria-hidden className="text-success" size={32} weight="duotone" />
            ) : (
              <WarningCircle aria-hidden className="text-error" size={32} weight="duotone" />
            )}
            <div>
              <h2 className="text-xl font-extrabold">{t("products.validationResult")}</h2>
              <p className="text-sm font-bold text-muted">
                {result.status === "valid" || result.status === "imported"
                  ? t("products.valid")
                  : t("products.invalid")}{" "}
                · {t("products.rows", { count: result.row_count })}
              </p>
            </div>
          </div>
          {result.issues.length ? (
            <ul className="mt-4 grid gap-2">
              {result.issues.map((item, index) => (
                <li
                  key={`${item.row}-${item.field}-${index}`}
                  className="rounded-xl bg-white p-3 text-sm"
                >
                  <strong>
                    {item.row ? `Row ${item.row}` : "File"}
                    {item.field ? ` · ${item.field}` : ""}
                  </strong>
                  : {item.message}
                </li>
              ))}
            </ul>
          ) : null}
          {result.status === "valid" ? (
            <button
              className="mt-5 min-h-11 rounded-xl bg-success px-5 font-black text-white disabled:opacity-45"
              disabled={busy !== null}
              onClick={() => void commitFile()}
              type="button"
            >
              {busy === "commit" ? t("common.saving") : t("products.commit")}
            </button>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
