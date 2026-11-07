import type { ReactNode } from "react";

export function AdminField({
  label,
  htmlFor,
  error,
  hint,
  required,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string | null;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <label className="text-sm font-extrabold text-deep-indigo" htmlFor={htmlFor}>
        {label}
        {required ? (
          <span aria-hidden className="ml-1 text-error">
            *
          </span>
        ) : null}
      </label>
      {children}
      {hint && !error ? <p className="text-xs text-muted">{hint}</p> : null}
      {error ? (
        <p className="text-sm font-bold text-error" id={`${htmlFor}-error`} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export const adminInputClass =
  "min-h-12 w-full rounded-xl border border-brand-purple/20 bg-white px-3.5 py-2.5 text-ink shadow-sm transition focus:border-brand-purple disabled:cursor-not-allowed disabled:bg-page-background disabled:text-muted aria-invalid:border-error";

export const adminTextareaClass = `${adminInputClass} min-h-28 resize-y`;

export function fieldErrorProps(id: string, error?: string | null) {
  return {
    "aria-describedby": error ? `${id}-error` : undefined,
    "aria-invalid": error ? (true as const) : undefined,
  };
}
