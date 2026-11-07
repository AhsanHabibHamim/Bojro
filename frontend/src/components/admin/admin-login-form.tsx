"use client";

import { Lightning, LockKey, ShieldCheck } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { AdminApiError } from "@/lib/admin/client";
import { useAdminSession } from "@/lib/admin/context";

import { safeAdminReturnTo } from "./admin-auth-gate";
import { AdminField, adminInputClass, fieldErrorProps } from "./ui/form-field";

type Challenge = {
  id: string;
  expiresAt: number;
  methods: Array<"totp" | "recovery_code">;
};

export function AdminLoginForm({
  locale,
  returnTo,
}: {
  locale: AppLocale;
  returnTo: string | null;
}) {
  const t = useTranslations("admin.auth");
  const router = useRouter();
  const { session, status, login, verifyTotp } = useAdminSession();
  const destination = safeAdminReturnTo(returnTo, locale);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [method, setMethod] = useState<"totp" | "recovery_code">("totp");
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "ready" && session?.authenticated) router.replace(destination);
  }, [destination, router, session?.authenticated, status]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await login(email.trim(), password);
      setPassword("");
      if (result.state === "totp_required") {
        setChallenge({
          id: result.challenge_id,
          expiresAt: Date.now() + result.expires_in_seconds * 1_000,
          methods: result.methods,
        });
        setMethod(result.methods.includes("totp") ? "totp" : "recovery_code");
      } else {
        router.replace(destination);
      }
    } catch {
      setPassword("");
      setError(t("genericError"));
    } finally {
      setSubmitting(false);
    }
  }

  async function submitChallenge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!challenge || Date.now() >= challenge.expiresAt) {
      setChallenge(null);
      setCode("");
      setError(t("expired"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await verifyTotp(challenge.id, code.trim(), method);
      setCode("");
      router.replace(destination);
    } catch (caught) {
      setCode("");
      setError(
        caught instanceof AdminApiError && caught.code === "ADMIN_TOTP_CHALLENGE_EXPIRED"
          ? t("expired")
          : t("genericError"),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="admin-login-grid min-h-dvh bg-deep-indigo" id="main-content">
      <section className="bolt-grid hidden min-h-dvh place-content-center p-10 text-white lg:grid">
        <div className="max-w-lg">
          <span className="inline-flex rounded-3xl bg-white/10 p-5">
            <Lightning aria-hidden size={58} weight="duotone" />
          </span>
          <p className="mt-8 text-sm font-black tracking-[0.2em] text-sale-amber uppercase">
            {t("eyebrow")}
          </p>
          <h1 className="mt-3 text-5xl font-extrabold text-white">{t("title")}</h1>
          <p className="mt-5 text-lg text-white/75">{t("description")}</p>
        </div>
      </section>
      <section className="grid min-h-dvh place-content-center bg-page-background p-4 sm:p-8">
        <div className="w-[min(30rem,calc(100vw-2rem))] rounded-3xl border border-brand-purple/12 bg-white p-6 shadow-2xl sm:p-9">
          <div className="mb-7 inline-flex rounded-2xl bg-soft-lavender p-3 text-brand-purple lg:hidden">
            <Lightning aria-hidden size={34} weight="duotone" />
          </div>
          <div className="flex items-start gap-3">
            <ShieldCheck
              aria-hidden
              className="mt-1 shrink-0 text-brand-purple"
              size={29}
              weight="duotone"
            />
            <div>
              <h2 className="text-2xl font-extrabold">{challenge ? t("totpTitle") : t("title")}</h2>
              <p className="mt-1 text-sm text-muted">
                {challenge ? t("totpDescription") : t("description")}
              </p>
            </div>
          </div>

          {challenge ? (
            <form className="mt-7 grid gap-5" onSubmit={submitChallenge}>
              <AdminField
                error={error}
                htmlFor="admin-verification-code"
                label={method === "totp" ? t("totp") : t("recovery")}
                required
              >
                <input
                  {...fieldErrorProps("admin-verification-code", error)}
                  autoComplete="one-time-code"
                  autoFocus
                  className={adminInputClass}
                  id="admin-verification-code"
                  inputMode={method === "totp" ? "numeric" : "text"}
                  maxLength={method === "totp" ? 8 : 64}
                  onChange={(event) => setCode(event.target.value)}
                  required
                  value={code}
                />
              </AdminField>
              {challenge.methods.length > 1 ? (
                <button
                  className="min-h-11 justify-self-start rounded-xl px-3 text-sm font-black text-brand-purple hover:bg-soft-lavender"
                  onClick={() => {
                    setCode("");
                    setMethod((current) => (current === "totp" ? "recovery_code" : "totp"));
                  }}
                  type="button"
                >
                  {method === "totp" ? t("useRecovery") : t("useTotp")}
                </button>
              ) : null}
              <button
                className="signature-gradient min-h-12 rounded-xl px-5 font-black text-white disabled:opacity-60"
                disabled={submitting || !code.trim()}
                type="submit"
              >
                {submitting ? t("verifying") : t("verify")}
              </button>
            </form>
          ) : (
            <form className="mt-7 grid gap-5" onSubmit={submitLogin}>
              <AdminField htmlFor="admin-email" label={t("email")} required>
                <input
                  autoComplete="username"
                  className={adminInputClass}
                  id="admin-email"
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  type="email"
                  value={email}
                />
              </AdminField>
              <AdminField error={error} htmlFor="admin-password" label={t("password")} required>
                <input
                  {...fieldErrorProps("admin-password", error)}
                  autoComplete="current-password"
                  className={adminInputClass}
                  id="admin-password"
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type="password"
                  value={password}
                />
              </AdminField>
              <button
                className="signature-gradient inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-5 font-black text-white disabled:opacity-60"
                disabled={submitting || !email.trim() || !password}
                type="submit"
              >
                <LockKey aria-hidden size={20} weight="duotone" />
                {submitting ? t("signingIn") : t("signIn")}
              </button>
            </form>
          )}
          <p className="mt-6 border-t border-brand-purple/10 pt-5 text-xs leading-5 text-muted">
            {t("security")}
          </p>
        </div>
      </section>
    </main>
  );
}
