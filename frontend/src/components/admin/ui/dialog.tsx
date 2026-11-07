"use client";

import { X } from "@phosphor-icons/react";
import { type ReactNode, useEffect, useId, useRef } from "react";

export function AdminDialog({
  open,
  onClose,
  title,
  description,
  closeLabel,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  closeLabel: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open) {
      opener.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      if (!dialog.open) {
        if (typeof dialog.showModal === "function") dialog.showModal();
        else dialog.setAttribute("open", "");
      }
      queueMicrotask(() => {
        dialog.querySelector<HTMLElement>("[data-autofocus],button,input,select,textarea")?.focus();
      });
    } else if (dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
      opener.current?.focus();
    }
  }, [open]);

  useEffect(
    () => () => {
      opener.current?.focus();
    },
    [],
  );

  return (
    <dialog
      ref={ref}
      aria-describedby={description ? descriptionId : undefined}
      aria-labelledby={titleId}
      className="m-auto max-h-[calc(100dvh-2rem)] w-[min(42rem,calc(100vw-2rem))] rounded-3xl border border-brand-purple/15 bg-white p-0 text-ink shadow-2xl backdrop:bg-deep-indigo/65 open:flex open:flex-col"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="flex items-start gap-4 border-b border-brand-purple/10 px-5 py-4 sm:px-6">
        <div className="min-w-0 flex-1">
          <h2 className="text-xl font-extrabold" id={titleId}>
            {title}
          </h2>
          {description ? (
            <p className="mt-1 text-sm text-muted" id={descriptionId}>
              {description}
            </p>
          ) : null}
        </div>
        <button
          aria-label={closeLabel}
          className="grid size-11 shrink-0 place-items-center rounded-xl border border-brand-purple/10 text-deep-indigo hover:bg-soft-lavender"
          onClick={onClose}
          type="button"
        >
          <X aria-hidden size={20} weight="bold" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-5 sm:p-6">{children}</div>
      {footer ? (
        <div className="flex flex-wrap justify-end gap-3 border-t border-brand-purple/10 px-5 py-4 sm:px-6">
          {footer}
        </div>
      ) : null}
    </dialog>
  );
}
