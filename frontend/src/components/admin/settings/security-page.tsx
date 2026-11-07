"use client";

import { Copy, Key, ShieldCheck, SignOut } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { useAdminApi, useAdminMutation, useAdminSession } from "@/lib/admin/context";
import { isAmbiguousAdminMutation } from "@/lib/admin/idempotency";
import type { AdminRecoveryCodes, AdminTotpSetup } from "@/lib/admin/types";

import { AdminField, adminInputClass, fieldErrorProps } from "../ui/form-field";
import { AdminPageHeader } from "../ui/page-header";
import { AdminStatusBadge } from "../ui/status-badge";
import { useAdminToast } from "../ui/toast";

export function SecurityPage({ locale }: { locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const { session, refresh } = useAdminSession();
  const toast = useAdminToast();
  const router = useRouter();
  const changePassword = useAdminMutation("admin-password-change");
  const setupMutation = useAdminMutation("admin-totp-setup");
  const confirmMutation = useAdminMutation("admin-totp-confirm");
  const disableMutation = useAdminMutation("admin-totp-disable");
  const logoutMutation = useAdminMutation("admin-logout-all");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [setupPassword, setSetupPassword] = useState("");
  const [setup, setSetup] = useState<AdminTotpSetup | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [recovery, setRecovery] = useState<AdminRecoveryCodes | null>(null);
  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (newPassword.length < 12 || newPassword !== confirmPassword) {
      setPasswordError(t("errors.VALIDATION_ERROR"));
      return;
    }
    setBusy("password");
    try {
      await changePassword({ currentPassword, newPassword }, (key) =>
        api.changePassword(currentPassword, newPassword, key),
      );
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordError(null);
      toast.push(t("toast.saved"));
    } catch {
      setPasswordError(t("errors.generic"));
    } finally {
      setBusy(null);
    }
  }

  async function beginSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("setup");
    try {
      const result = await setupMutation({ password: setupPassword }, (key) =>
        api.setupTotp(setupPassword, key),
      );
      setSetupPassword("");
      setSetup(result);
    } catch {
      toast.push(t("toast.error"), "error");
    } finally {
      setBusy(null);
    }
  }

  async function confirmSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("confirm");
    try {
      const result = await confirmMutation({ code: confirmCode }, (key) =>
        api.confirmTotp(confirmCode, key),
      );
      setConfirmCode("");
      setSetup(null);
      setRecovery(result);
      await refresh();
      toast.push(t("toast.saved"));
    } catch {
      toast.push(t("toast.error"), "error");
    } finally {
      setBusy(null);
    }
  }

  async function disable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("disable");
    try {
      await disableMutation({ password: disablePassword, code: disableCode }, (key) =>
        api.disableTotp(disablePassword, disableCode, key),
      );
      setDisablePassword("");
      setDisableCode("");
      await refresh();
      toast.push(t("toast.saved"));
    } catch {
      toast.push(t("toast.error"), "error");
    } finally {
      setBusy(null);
    }
  }

  async function logoutAllSessions() {
    setBusy("logout");
    try {
      await logoutMutation({ all: true }, (key) => api.logoutAll(key));
      router.replace(`/${locale}/admin/login`);
    } catch (error) {
      if (isAmbiguousAdminMutation(error)) {
        api.transport.clearSession();
        toast.push(t("common.unknownOutcome"), "error");
        router.replace(`/${locale}/admin/login`);
      } else {
        toast.push(t("toast.error"), "error");
      }
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-6">
      <AdminPageHeader description={t("security.description")} title={t("security.title")} />
      <section className="grid gap-5 rounded-2xl border border-brand-purple/12 bg-white p-5">
        <div className="flex items-center gap-3">
          <Key aria-hidden className="text-brand-purple" size={26} weight="duotone" />
          <h2 className="text-xl font-extrabold">{t("security.password")}</h2>
        </div>
        <form className="grid gap-4 sm:grid-cols-3" onSubmit={submitPassword}>
          <AdminField
            error={passwordError}
            htmlFor="current-password"
            label={t("security.currentPassword")}
            required
          >
            <input
              {...fieldErrorProps("current-password", passwordError)}
              autoComplete="current-password"
              className={adminInputClass}
              id="current-password"
              onChange={(event) => setCurrentPassword(event.target.value)}
              required
              type="password"
              value={currentPassword}
            />
          </AdminField>
          <AdminField htmlFor="new-password" label={t("security.newPassword")} required>
            <input
              autoComplete="new-password"
              className={adminInputClass}
              id="new-password"
              minLength={12}
              onChange={(event) => setNewPassword(event.target.value)}
              required
              type="password"
              value={newPassword}
            />
          </AdminField>
          <AdminField htmlFor="confirm-password" label={t("security.confirmPassword")} required>
            <input
              autoComplete="new-password"
              className={adminInputClass}
              id="confirm-password"
              minLength={12}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              type="password"
              value={confirmPassword}
            />
          </AdminField>
          <button
            className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white disabled:opacity-45 sm:col-span-3 sm:justify-self-start"
            disabled={busy !== null}
            type="submit"
          >
            {busy === "password" ? t("common.saving") : t("common.save")}
          </button>
        </form>
      </section>
      <section className="grid gap-5 rounded-2xl border border-brand-purple/12 bg-white p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <ShieldCheck aria-hidden className="text-brand-purple" size={26} weight="duotone" />
            <h2 className="text-xl font-extrabold">{t("security.totp")}</h2>
          </div>
          <AdminStatusBadge status={session?.mfa.configured ? "enabled" : "disabled"} />
        </div>
        <p className="text-sm text-muted">
          {session?.mfa.configured ? t("security.totpEnabled") : t("security.totpDisabled")}
        </p>
        {!session?.mfa.configured && !setup ? (
          <form className="grid max-w-md gap-4" onSubmit={beginSetup}>
            <AdminField
              htmlFor="totp-setup-password"
              label={t("security.currentPassword")}
              required
            >
              <input
                autoComplete="current-password"
                className={adminInputClass}
                id="totp-setup-password"
                onChange={(event) => setSetupPassword(event.target.value)}
                required
                type="password"
                value={setupPassword}
              />
            </AdminField>
            <button
              className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white disabled:opacity-45"
              disabled={busy !== null}
              type="submit"
            >
              {t("security.setup")}
            </button>
          </form>
        ) : null}
        {setup ? (
          <form className="grid gap-4 rounded-2xl bg-page-background p-4" onSubmit={confirmSetup}>
            <div>
              <p className="text-xs font-black text-muted uppercase">{t("security.manualKey")}</p>
              <code className="mt-1 block overflow-x-auto rounded-xl bg-white p-3 text-sm">
                {setup.manual_key}
              </code>
            </div>
            <code className="overflow-x-auto text-xs text-muted">{setup.otpauth_uri}</code>
            <AdminField htmlFor="totp-confirm-code" label={t("security.confirmCode")} required>
              <input
                autoComplete="one-time-code"
                className={adminInputClass}
                id="totp-confirm-code"
                inputMode="numeric"
                onChange={(event) => setConfirmCode(event.target.value)}
                required
                value={confirmCode}
              />
            </AdminField>
            <button
              className="min-h-11 rounded-xl bg-success px-5 font-black text-white disabled:opacity-45 sm:justify-self-start"
              disabled={busy !== null}
              type="submit"
            >
              {t("common.confirm")}
            </button>
          </form>
        ) : null}
        {recovery ? (
          <div
            className="rounded-2xl border border-sale-amber/35 bg-sale-amber/10 p-5"
            role="status"
          >
            <h3 className="text-lg font-extrabold">{t("security.recoveryCodes")}</h3>
            <p className="mt-1 text-sm font-bold text-deep-indigo">
              {t("security.recoveryWarning")}
            </p>
            <ul className="mt-4 grid grid-cols-2 gap-2 font-mono text-sm">
              {recovery.recovery_codes.map((code) => (
                <li key={code} className="rounded-lg bg-white p-2">
                  {code}
                </li>
              ))}
            </ul>
            <button
              className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-xl bg-deep-indigo px-4 font-black text-white"
              onClick={() =>
                void navigator.clipboard
                  .writeText(recovery.recovery_codes.join("\n"))
                  .then(() => toast.push(t("toast.copied")))
              }
              type="button"
            >
              <Copy aria-hidden size={18} />
              {t("toast.copied")}
            </button>
            <button
              className="mt-4 ml-2 min-h-11 rounded-xl border border-brand-purple/15 px-4 font-black"
              onClick={() => setRecovery(null)}
              type="button"
            >
              {t("security.savedOffline")}
            </button>
          </div>
        ) : null}
        {session?.mfa.configured ? (
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={disable}>
            <AdminField
              htmlFor="totp-disable-password"
              label={t("security.currentPassword")}
              required
            >
              <input
                autoComplete="current-password"
                className={adminInputClass}
                id="totp-disable-password"
                onChange={(event) => setDisablePassword(event.target.value)}
                required
                type="password"
                value={disablePassword}
              />
            </AdminField>
            <AdminField htmlFor="totp-disable-code" label={t("auth.code")} required>
              <input
                autoComplete="one-time-code"
                className={adminInputClass}
                id="totp-disable-code"
                onChange={(event) => setDisableCode(event.target.value)}
                required
                value={disableCode}
              />
            </AdminField>
            <button
              className="min-h-11 rounded-xl border border-error/25 px-5 font-black text-error disabled:opacity-45 sm:col-span-2 sm:justify-self-start"
              disabled={busy !== null}
              type="submit"
            >
              {t("security.disable")}
            </button>
          </form>
        ) : null}
      </section>
      <section className="grid gap-4 rounded-2xl border border-error/20 bg-white p-5">
        <div className="flex items-center gap-3">
          <SignOut aria-hidden className="text-error" size={26} />
          <h2 className="text-xl font-extrabold">{t("security.sessionRevocation")}</h2>
        </div>
        <p className="text-sm text-muted">{t("security.logoutAllDescription")}</p>
        <button
          className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-error px-5 font-black text-white disabled:opacity-45 sm:justify-self-start"
          disabled={busy !== null}
          onClick={() => void logoutAllSessions()}
          type="button"
        >
          <SignOut aria-hidden size={18} />
          {t("auth.logoutAll")}
        </button>
      </section>
    </div>
  );
}
