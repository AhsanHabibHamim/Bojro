"use client";

import { WhatsappLogo } from "@phosphor-icons/react";

import { buildWhatsAppHref } from "@/lib/engagement/whatsapp";

export function WhatsAppButton({
  settings,
  label,
  className = "",
  showLabel = false,
}: {
  settings: { enabled: boolean; phone: string; message: string };
  label: string;
  className?: string;
  showLabel?: boolean;
}) {
  const href = buildWhatsAppHref(settings);
  if (!href) return null;
  return (
    <a
      aria-label={label}
      className={`inline-flex min-h-12 min-w-12 items-center justify-center gap-2 rounded-full bg-[#0d713d] px-3 font-extrabold text-white shadow-[0_10px_34px_rgb(13_113_61/0.35)] transition-transform hover:-translate-y-0.5 ${className}`}
      href={href}
      rel="noopener noreferrer"
      target="_blank"
    >
      <WhatsappLogo aria-hidden size={27} weight="fill" />
      {showLabel ? <span>{label}</span> : null}
    </a>
  );
}
