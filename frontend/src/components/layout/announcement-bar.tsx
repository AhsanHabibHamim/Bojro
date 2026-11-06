import { Lightning } from "@phosphor-icons/react/dist/ssr";
import { useTranslations } from "next-intl";

export function AnnouncementBar({ text, href }: { text?: string; href?: string | null }) {
  const t = useTranslations("announcement");
  const content = (
    <span className="inline-flex items-center justify-center gap-2">
      <Lightning aria-hidden size={17} weight="duotone" />
      {text ?? t("offer")}
    </span>
  );

  return (
    <aside
      id="announcement"
      aria-label={t("label")}
      className="bg-deep-indigo px-4 py-1.5 text-center text-sm font-semibold tracking-[0.01em] text-white"
    >
      {href ? (
        <a className="rounded-sm hover:underline" href={href}>
          {content}
        </a>
      ) : (
        content
      )}
    </aside>
  );
}
