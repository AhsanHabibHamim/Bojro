import type { AppLocale } from "@/i18n/routing";
import { formatAccountDate } from "@/lib/account/format";
import type { CustomerTimelineEvent } from "@/lib/account/types";

export function OrderTimeline({
  events,
  locale,
  statuses,
}: {
  events: CustomerTimelineEvent[];
  locale: AppLocale;
  statuses: Record<string, string>;
}) {
  return (
    <ol className="mt-5 space-y-0">
      {events.map((event, index) => (
        <li
          key={event.id ?? `${event.status}-${event.at}`}
          className="relative flex gap-4 pb-6 last:pb-0"
        >
          {index < events.length - 1 ? (
            <span
              aria-hidden
              className="absolute top-5 left-[0.55rem] h-full w-px bg-brand-purple/20"
            />
          ) : null}
          <span className="relative mt-1 size-3 shrink-0 rounded-full bg-brand-purple ring-4 ring-soft-lavender" />
          <div>
            <strong className="text-deep-indigo">{statuses[event.status] ?? event.status}</strong>
            <time className="block text-sm text-muted" dateTime={event.at}>
              {formatAccountDate(event.at, locale, true)}
            </time>
            {(event.customer_note ?? event.note) ? (
              <p className="mt-1 text-sm text-muted">{event.customer_note ?? event.note}</p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
