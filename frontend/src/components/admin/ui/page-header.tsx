import type { ReactNode } from "react";

export function AdminPageHeader({
  title,
  description,
  eyebrow,
  actions,
}: {
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 border-b border-brand-purple/10 pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow ? (
          <p className="text-xs font-black tracking-[0.18em] text-brand-purple uppercase">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="mt-1 text-3xl font-extrabold sm:text-4xl">{title}</h1>
        {description ? (
          <p className="mt-2 max-w-3xl text-sm text-muted sm:text-base">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
    </header>
  );
}
