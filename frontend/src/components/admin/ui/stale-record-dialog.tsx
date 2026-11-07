"use client";

import { useTranslations } from "next-intl";

import { AdminDialog } from "./dialog";

export function StaleRecordDialog({
  open,
  onClose,
  onReload,
}: {
  open: boolean;
  onClose: () => void;
  onReload: () => void;
}) {
  const t = useTranslations("admin.common");
  return (
    <AdminDialog
      closeLabel={t("close")}
      description={t("staleDescription")}
      footer={
        <>
          <button
            className="min-h-11 rounded-xl border border-brand-purple/15 px-5 font-bold"
            onClick={onClose}
            type="button"
          >
            {t("cancel")}
          </button>
          <button
            className="min-h-11 rounded-xl bg-deep-indigo px-5 font-bold text-white"
            onClick={() => {
              onClose();
              onReload();
            }}
            type="button"
          >
            {t("reload")}
          </button>
        </>
      }
      onClose={onClose}
      open={open}
      title={t("staleTitle")}
    >
      <p className="text-sm text-muted">{t("unknownOutcome")}</p>
    </AdminDialog>
  );
}
