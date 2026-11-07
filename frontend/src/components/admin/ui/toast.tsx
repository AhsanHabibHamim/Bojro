"use client";

import { CheckCircle, Info, WarningCircle, X } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { createContext, type ReactNode, use, useCallback, useState } from "react";

type ToastTone = "success" | "error" | "info";
type Toast = { id: string; message: string; tone: ToastTone };
type ToastContextValue = { push: (message: string, tone?: ToastTone) => void };

const ToastContext = createContext<ToastContextValue | null>(null);

export function AdminToastProvider({ children }: { children: ReactNode }) {
  const t = useTranslations("admin.common");
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);
  const push = useCallback(
    (message: string, tone: ToastTone = "success") => {
      const id = crypto.randomUUID();
      setToasts((current) => [...current.slice(-3), { id, message, tone }]);
      window.setTimeout(() => dismiss(id), 5_000);
    },
    [dismiss],
  );

  return (
    <ToastContext value={{ push }}>
      {children}
      <div
        aria-atomic="false"
        aria-live="polite"
        className="pointer-events-none fixed right-4 bottom-4 z-[140] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2"
      >
        {toasts.map((toast) => {
          const Icon =
            toast.tone === "success" ? CheckCircle : toast.tone === "error" ? WarningCircle : Info;
          return (
            <div
              key={toast.id}
              className={`pointer-events-auto flex min-h-14 items-start gap-3 rounded-2xl border bg-white p-4 shadow-xl ${
                toast.tone === "error"
                  ? "border-error/30 text-error"
                  : toast.tone === "success"
                    ? "border-success/30 text-success"
                    : "border-brand-purple/20 text-deep-indigo"
              }`}
              role={toast.tone === "error" ? "alert" : "status"}
            >
              <Icon aria-hidden className="mt-0.5 shrink-0" size={22} weight="duotone" />
              <p className="min-w-0 flex-1 text-sm font-bold text-ink">{toast.message}</p>
              <button
                aria-label={t("close")}
                className="grid size-11 shrink-0 place-items-center rounded-xl text-muted hover:bg-page-background"
                onClick={() => dismiss(toast.id)}
                type="button"
              >
                <X aria-hidden size={18} weight="bold" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext>
  );
}

export function useAdminToast(): ToastContextValue {
  const value = use(ToastContext);
  if (!value) throw new Error("useAdminToast must be used inside AdminToastProvider");
  return value;
}
