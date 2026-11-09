import { CaretRight, House } from "@phosphor-icons/react/dist/ssr";

import type { AppLocale } from "@/i18n/routing";

export type BreadcrumbItem = { label: string; href?: string };

export function Breadcrumbs({
  locale,
  homeLabel,
  items,
}: {
  locale: AppLocale;
  homeLabel: string;
  items: BreadcrumbItem[];
}) {
  return (
    <nav aria-label="Breadcrumb" className="overflow-x-auto text-sm text-muted">
      <ol className="flex min-w-max items-center gap-2 py-1">
        <li>
          <a
            className="inline-flex min-h-11 items-center gap-1 rounded-sm hover:text-brand-purple"
            href={`/${locale}`}
          >
            <House aria-hidden size={16} weight="duotone" />
            {homeLabel}
          </a>
        </li>
        {items.map((item, index) => (
          <li key={`${item.label}-${index}`} className="flex items-center gap-2">
            <CaretRight aria-hidden className="text-brand-purple/50" size={13} weight="bold" />
            {item.href ? (
              <a
                className="inline-flex min-h-11 items-center rounded-sm hover:text-brand-purple"
                href={item.href}
              >
                {item.label}
              </a>
            ) : (
              <span aria-current="page" className="font-bold text-deep-indigo">
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
