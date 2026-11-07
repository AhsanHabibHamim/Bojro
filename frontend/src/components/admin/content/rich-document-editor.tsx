"use client";

import { useEffect, useState } from "react";

import { RichDocumentRenderer } from "@/components/content/rich-document-renderer";
import { parseRichDocumentSource } from "@/lib/admin/rich-document";
import type { RichDocument } from "@/lib/admin/types";

import { AdminField, adminTextareaClass, fieldErrorProps } from "../ui/form-field";

export function RichDocumentEditor({
  id,
  label,
  help,
  invalidMessage,
  previewLabel,
  value,
  onChange,
  onValidityChange,
}: {
  id: string;
  label: string;
  help: string;
  invalidMessage: string;
  previewLabel: string;
  value: RichDocument;
  onChange: (document: RichDocument) => void;
  onValidityChange: (valid: boolean) => void;
}) {
  const [source, setSource] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState(value);

  useEffect(() => {
    const nextSource = JSON.stringify(value, null, 2);
    queueMicrotask(() => {
      setSource(nextSource);
      setPreview(value);
      setError(null);
      onValidityChange(true);
    });
  }, [onValidityChange, value]);

  function update(next: string) {
    setSource(next);
    try {
      const document = parseRichDocumentSource(next);
      setError(null);
      setPreview(document);
      onChange(document);
      onValidityChange(true);
    } catch {
      setError(invalidMessage);
      onValidityChange(false);
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <AdminField error={error} hint={help} htmlFor={id} label={label} required>
        <textarea
          {...fieldErrorProps(id, error)}
          className={`${adminTextareaClass} min-h-96 font-mono text-xs leading-5`}
          id={id}
          onChange={(event) => update(event.target.value)}
          spellCheck={false}
          value={source}
        />
      </AdminField>
      <section className="rounded-2xl border border-brand-purple/12 bg-page-background p-5">
        <h3 className="mb-4 text-lg font-extrabold">{previewLabel}</h3>
        <RichDocumentRenderer className="rounded-xl bg-white p-5" document={preview} />
      </section>
    </div>
  );
}
