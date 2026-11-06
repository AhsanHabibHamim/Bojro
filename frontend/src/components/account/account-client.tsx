"use client";

import {
  ArrowRight,
  CheckCircle,
  ClockCountdown,
  EnvelopeSimple,
  LockKey,
  Phone,
  ShieldCheck,
  SignOut,
  UserCircle,
} from "@phosphor-icons/react";
import { type FormEvent, useEffect, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import { CommerceError } from "@/lib/commerce/client";
import { otpDeadlines, secondsUntil, type OtpDeadlines } from "@/lib/commerce/auth";
import {
  isValidBangladeshPhone,
  normalizeBanglaDigits,
  normalizeBangladeshPhone,
} from "@/lib/commerce/checkout";
import type { OtpChallenge } from "@/lib/commerce/types";
import { formatNumber } from "@/lib/format-number";

export type AccountLabels = {
  title: string;
  subtitle: string;
  loading: string;
  signedIn: {
    title: string;
    description: string;
    phone: string;
    email: string;
    cartAdjusted: string;
    logout: string;
    loggingOut: string;
  };
  available: {
    title: string;
    description: string;
  };
  otp: {
    tab: string;
    title: string;
    description: string;
    phone: string;
    name: string;
    nameOptional: string;
    request: string;
    requesting: string;
    requestSuccess: string;
    code: string;
    devCode: string;
    verify: string;
    verifying: string;
    resend: string;
    resendIn: string;
    expiresIn: string;
    invalidPhone: string;
    retryAfter: string;
  };
  email: {
    tab: string;
    title: string;
    description: string;
    address: string;
    password: string;
    login: string;
    loggingIn: string;
  };
  security: string;
  genericError: string;
};

function secondsLabel(template: string, seconds: number, locale: "bn" | "en"): string {
  return template.replace("{seconds}", formatNumber(Math.max(0, seconds), locale));
}

export function AccountClient({
  labels,
  isDevelopment,
}: {
  labels: AccountLabels;
  isDevelopment: boolean;
}) {
  const {
    locale,
    session,
    isBootstrapping,
    pendingAction,
    requestOtp,
    verifyOtp,
    loginWithEmail,
    logout,
  } = useCommerce();
  const [method, setMethod] = useState<"otp" | "email">("otp");
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState<OtpChallenge | null>(null);
  const [deadlines, setDeadlines] = useState<OtpDeadlines | null>(null);
  const [requestRetryAt, setRequestRetryAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if ((!challenge || !deadlines) && !requestRetryAt) return;
    const update = () => setNow(Date.now());
    const timer = window.setInterval(update, 1_000);
    document.addEventListener("visibilitychange", update);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", update);
    };
  }, [challenge, deadlines, requestRetryAt]);

  const resendRemaining = deadlines ? secondsUntil(deadlines.resendAt, now) : 0;
  const expiresRemaining = deadlines ? secondsUntil(deadlines.expiresAt, now) : 0;
  const requestRetryRemaining = requestRetryAt ? secondsUntil(requestRetryAt, now) : 0;
  const effectiveResendRemaining = Math.max(resendRemaining, requestRetryRemaining);

  const beginChallenge = (nextChallenge: OtpChallenge) => {
    const startedAt = Date.now();
    setChallenge(nextChallenge);
    setDeadlines(
      otpDeadlines(nextChallenge.expires_in_seconds, nextChallenge.resend_after_seconds, startedAt),
    );
    setNow(startedAt);
    setRequestRetryAt(null);
    setStatus(labels.otp.requestSuccess);
    setError("");
  };

  const submitOtpRequest = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isValidBangladeshPhone(phone)) {
      setError(labels.otp.invalidPhone);
      setStatus("");
      return;
    }
    setError("");
    setStatus("");
    try {
      beginChallenge(await requestOtp(normalizeBangladeshPhone(phone)));
    } catch (requestError) {
      if (requestError instanceof CommerceError && requestError.retryAfterSeconds !== null) {
        setRequestRetryAt(Date.now() + requestError.retryAfterSeconds * 1_000);
        setNow(Date.now());
      }
      setError(labels.genericError);
    }
  };

  const submitOtpVerification = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!challenge || !deadlines || Date.now() >= deadlines.expiresAt || !/^\d{6}$/.test(code)) {
      return;
    }
    setError("");
    try {
      await verifyOtp({
        challenge_id: challenge.challenge_id,
        code,
        name: name.trim() || undefined,
      });
      setCode("");
      setChallenge(null);
      setDeadlines(null);
    } catch {
      setError(labels.genericError);
    }
  };

  const submitEmail = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    try {
      await loginWithEmail({ email: email.trim(), password });
    } catch {
      setError(labels.genericError);
    } finally {
      setPassword("");
    }
  };

  if (!session && isBootstrapping) {
    return <div className="container-shell py-16 font-bold text-muted">{labels.loading}</div>;
  }

  return (
    <div className="container-shell py-10 sm:py-16">
      <div className="mx-auto max-w-4xl">
        <div className="text-center">
          <UserCircle
            aria-hidden
            className="mx-auto text-brand-purple"
            size={58}
            weight="duotone"
          />
          <h1 className="mt-4 text-4xl font-extrabold sm:text-5xl">{labels.title}</h1>
          <p className="mx-auto mt-3 max-w-2xl text-muted">{labels.subtitle}</p>
        </div>

        {session?.authenticated && session.user ? (
          <section className="mx-auto mt-9 max-w-2xl rounded-3xl border border-brand-purple/10 bg-white p-6 shadow-soft sm:p-8">
            <div className="flex items-start gap-4">
              <span className="inline-grid size-14 shrink-0 place-items-center rounded-2xl bg-success/10 text-success">
                <CheckCircle aria-hidden size={31} weight="fill" />
              </span>
              <div>
                <h2 className="text-2xl font-extrabold">{labels.signedIn.title}</h2>
                <p className="mt-1 text-muted">{labels.signedIn.description}</p>
              </div>
            </div>
            <dl className="mt-6 divide-y divide-brand-purple/10 rounded-2xl bg-soft-lavender/40 px-5">
              <div className="flex justify-between gap-4 py-4">
                <dt className="font-bold text-muted">{labels.otp.name}</dt>
                <dd className="text-right font-extrabold text-deep-indigo">{session.user.name}</dd>
              </div>
              <div className="flex justify-between gap-4 py-4">
                <dt className="font-bold text-muted">{labels.signedIn.phone}</dt>
                <dd className="text-right font-extrabold text-deep-indigo">{session.user.phone}</dd>
              </div>
              <div className="flex justify-between gap-4 py-4">
                <dt className="font-bold text-muted">{labels.signedIn.email}</dt>
                <dd className="text-right font-extrabold text-deep-indigo">
                  {session.user.email ?? "—"}
                </dd>
              </div>
            </dl>
            {session.merge_warnings.length ? (
              <p
                className="mt-4 rounded-xl bg-sale-amber/15 px-4 py-3 text-sm font-bold text-deep-indigo"
                role="status"
              >
                {labels.signedIn.cartAdjusted}
              </p>
            ) : null}
            <button
              className="mt-6 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-full border border-error/25 font-extrabold text-error transition-colors hover:bg-error/5 disabled:opacity-55"
              disabled={pendingAction === "auth"}
              onClick={async () => {
                setError("");
                try {
                  await logout();
                } catch {
                  setError(labels.genericError);
                }
              }}
              type="button"
            >
              <SignOut aria-hidden size={21} weight="duotone" />
              {pendingAction === "auth" ? labels.signedIn.loggingOut : labels.signedIn.logout}
            </button>
            {error ? (
              <p
                className="mt-4 rounded-xl bg-error/10 px-4 py-3 text-sm font-bold text-error"
                role="alert"
              >
                {error}
              </p>
            ) : null}
          </section>
        ) : (
          <section className="mx-auto mt-9 max-w-2xl overflow-hidden rounded-3xl border border-brand-purple/10 bg-white shadow-soft">
            <div className="grid grid-cols-2 border-b border-brand-purple/10 bg-soft-lavender/35 p-2">
              {(["otp", "email"] as const).map((item) => (
                <button
                  key={item}
                  aria-pressed={method === item}
                  className={`min-h-11 rounded-full px-4 font-extrabold transition-colors ${method === item ? "bg-white text-brand-purple shadow-sm" : "text-muted"}`}
                  onClick={() => {
                    setMethod(item);
                    setError("");
                    setStatus("");
                  }}
                  type="button"
                >
                  {item === "otp" ? labels.otp.tab : labels.email.tab}
                </button>
              ))}
            </div>

            <div className="p-6 sm:p-8">
              {method === "otp" ? (
                challenge ? (
                  <form onSubmit={(event) => void submitOtpVerification(event)}>
                    <h2 className="flex items-center gap-2 text-2xl font-extrabold">
                      <ShieldCheck
                        aria-hidden
                        className="text-brand-purple"
                        size={27}
                        weight="duotone"
                      />
                      {labels.otp.title}
                    </h2>
                    <p className="mt-2 text-sm text-muted">{status}</p>
                    <label className="mt-5 block">
                      <span className="font-bold text-deep-indigo">
                        {isDevelopment ? labels.otp.devCode : labels.otp.code}
                      </span>
                      <input
                        autoComplete="one-time-code"
                        className="mt-1 min-h-13 w-full rounded-xl border border-brand-purple/20 px-4 text-center text-xl tracking-[0.4em] focus:border-brand-purple focus:outline-none"
                        inputMode="numeric"
                        maxLength={6}
                        onChange={(event) =>
                          setCode(normalizeBanglaDigits(event.target.value).replace(/\D/g, ""))
                        }
                        pattern="[0-9]{6}"
                        value={code}
                      />
                    </label>
                    <div className="mt-3 flex flex-wrap justify-between gap-2 text-xs text-muted">
                      <span className="inline-flex items-center gap-1">
                        <ClockCountdown aria-hidden size={16} />
                        {secondsLabel(labels.otp.expiresIn, expiresRemaining, locale)}
                      </span>
                      <button
                        className="min-h-11 px-2 font-extrabold text-brand-purple disabled:text-muted"
                        disabled={effectiveResendRemaining > 0 || pendingAction === "auth"}
                        onClick={async () => {
                          try {
                            beginChallenge(await requestOtp(normalizeBangladeshPhone(phone)));
                          } catch (requestError) {
                            if (
                              requestError instanceof CommerceError &&
                              requestError.retryAfterSeconds !== null
                            ) {
                              setRequestRetryAt(
                                Date.now() + requestError.retryAfterSeconds * 1_000,
                              );
                              setNow(Date.now());
                            }
                            setError(labels.genericError);
                          }
                        }}
                        type="button"
                      >
                        {effectiveResendRemaining > 0
                          ? secondsLabel(labels.otp.resendIn, effectiveResendRemaining, locale)
                          : labels.otp.resend}
                      </button>
                    </div>
                    <button
                      className="signature-gradient mt-4 inline-flex min-h-13 w-full items-center justify-center gap-2 rounded-full font-extrabold text-white disabled:opacity-55"
                      disabled={
                        code.length !== 6 || expiresRemaining <= 0 || pendingAction === "auth"
                      }
                      type="submit"
                    >
                      {pendingAction === "auth" ? labels.otp.verifying : labels.otp.verify}
                      <ArrowRight aria-hidden size={18} weight="bold" />
                    </button>
                  </form>
                ) : (
                  <form onSubmit={(event) => void submitOtpRequest(event)}>
                    <h2 className="flex items-center gap-2 text-2xl font-extrabold">
                      <Phone aria-hidden className="text-brand-purple" size={27} weight="duotone" />
                      {labels.otp.title}
                    </h2>
                    <p className="mt-2 text-sm text-muted">{labels.otp.description}</p>
                    <label className="mt-5 block">
                      <span className="font-bold text-deep-indigo">{labels.otp.phone}</span>
                      <input
                        autoComplete="tel"
                        className="mt-1 min-h-13 w-full rounded-xl border border-brand-purple/20 px-4 focus:border-brand-purple focus:outline-none"
                        inputMode="tel"
                        maxLength={24}
                        onChange={(event) => setPhone(event.target.value)}
                        placeholder="01XXXXXXXXX"
                        value={phone}
                      />
                    </label>
                    <label className="mt-4 block">
                      <span className="font-bold text-deep-indigo">
                        {labels.otp.name}{" "}
                        <span className="font-normal text-muted">({labels.otp.nameOptional})</span>
                      </span>
                      <input
                        autoComplete="name"
                        className="mt-1 min-h-13 w-full rounded-xl border border-brand-purple/20 px-4 focus:border-brand-purple focus:outline-none"
                        maxLength={120}
                        onChange={(event) => setName(event.target.value)}
                        value={name}
                      />
                    </label>
                    <button
                      className="signature-gradient mt-6 inline-flex min-h-13 w-full items-center justify-center gap-2 rounded-full font-extrabold text-white disabled:opacity-55"
                      disabled={pendingAction === "auth" || requestRetryRemaining > 0}
                      type="submit"
                    >
                      {pendingAction === "auth"
                        ? labels.otp.requesting
                        : requestRetryRemaining > 0
                          ? secondsLabel(labels.otp.retryAfter, requestRetryRemaining, locale)
                          : labels.otp.request}
                      <ArrowRight aria-hidden size={18} weight="bold" />
                    </button>
                  </form>
                )
              ) : (
                <form onSubmit={(event) => void submitEmail(event)}>
                  <h2 className="flex items-center gap-2 text-2xl font-extrabold">
                    <EnvelopeSimple
                      aria-hidden
                      className="text-brand-purple"
                      size={27}
                      weight="duotone"
                    />
                    {labels.email.title}
                  </h2>
                  <p className="mt-2 text-sm text-muted">{labels.email.description}</p>
                  <label className="mt-5 block">
                    <span className="font-bold text-deep-indigo">{labels.email.address}</span>
                    <input
                      autoComplete="email"
                      className="mt-1 min-h-13 w-full rounded-xl border border-brand-purple/20 px-4 focus:border-brand-purple focus:outline-none"
                      onChange={(event) => setEmail(event.target.value)}
                      required
                      type="email"
                      value={email}
                    />
                  </label>
                  <label className="mt-4 block">
                    <span className="font-bold text-deep-indigo">{labels.email.password}</span>
                    <input
                      autoComplete="current-password"
                      className="mt-1 min-h-13 w-full rounded-xl border border-brand-purple/20 px-4 focus:border-brand-purple focus:outline-none"
                      maxLength={128}
                      minLength={1}
                      onChange={(event) => setPassword(event.target.value)}
                      required
                      type="password"
                      value={password}
                    />
                  </label>
                  <button
                    className="signature-gradient mt-6 inline-flex min-h-13 w-full items-center justify-center gap-2 rounded-full font-extrabold text-white disabled:opacity-55"
                    disabled={!email || !password || pendingAction === "auth"}
                    type="submit"
                  >
                    {pendingAction === "auth" ? labels.email.loggingIn : labels.email.login}
                    <ArrowRight aria-hidden size={18} weight="bold" />
                  </button>
                </form>
              )}

              {error ? (
                <p
                  className="mt-4 rounded-xl bg-error/10 px-4 py-3 text-sm font-bold text-error"
                  role="alert"
                >
                  {error}
                </p>
              ) : null}
              {status && !challenge ? (
                <p
                  className="mt-4 rounded-xl bg-success/10 px-4 py-3 text-sm font-bold text-success"
                  role="status"
                >
                  {status}
                </p>
              ) : null}
              <p className="mt-5 flex items-start gap-2 border-t border-brand-purple/10 pt-5 text-xs leading-5 text-muted">
                <LockKey
                  aria-hidden
                  className="mt-0.5 shrink-0 text-brand-purple"
                  size={17}
                  weight="duotone"
                />
                {labels.security}
              </p>
            </div>
          </section>
        )}

        <section className="mx-auto mt-6 max-w-2xl rounded-2xl border border-brand-purple/10 bg-soft-lavender/40 p-5 text-center">
          <h2 className="text-lg font-extrabold">{labels.available.title}</h2>
          <p className="mt-1 text-sm text-muted">{labels.available.description}</p>
        </section>
      </div>
    </div>
  );
}
