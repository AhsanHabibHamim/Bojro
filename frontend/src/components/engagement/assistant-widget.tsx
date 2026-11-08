"use client";

import {
  ArrowClockwise,
  ChatCircleDots,
  CheckCircle,
  LinkSimple,
  LockKey,
  PaperPlaneRight,
  Robot,
  ShieldCheck,
  Trash,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { isValidBangladeshPhone, normalizeBangladeshPhone } from "@/lib/commerce/checkout";
import { EngagementError, engagementApi, type EngagementApi } from "@/lib/engagement/client";
import {
  containsSensitiveChatInput,
  enforceAssistantIdentity,
  isAssistantIdentityQuestion,
  stripRepeatedAssistantDisclosure,
} from "@/lib/engagement/privacy";
import type {
  AssistantMessage,
  AssistantMessageRequest,
  AssistantSession,
} from "@/lib/engagement/types";

import { WhatsAppButton } from "./whatsapp-button";

export type AssistantLabels = {
  button: string;
  close: string;
  title: string;
  disclosureLabel: string;
  start: string;
  starting: string;
  firstMessage: string;
  identityAnswer: string;
  inputLabel: string;
  placeholder: string;
  send: string;
  sending: string;
  sensitive: string;
  tooLong: string;
  genericError: string;
  rateLimited: string;
  retry: string;
  delete: string;
  deleting: string;
  deleted: string;
  citations: string;
  handoff: string;
  uncertain: string;
  verification: {
    open: string;
    title: string;
    description: string;
    number: string;
    phone: string;
    submit: string;
    submitting: string;
    invalid: string;
    failure: string;
    result: string;
    status: string;
    payment: string;
    area: string;
    updated: string;
    statusRequest: string;
  };
};

export type AssistantPublicSettings = {
  enabled: boolean;
  display_name: string;
  disclosure: string;
  disclosure_version: string;
};

export function isValidAssistantOrderNumber(value: string): boolean {
  return /^BJ-\d{4}-\d{6}$/i.test(value.trim());
}

function disclosureMessage(
  session: AssistantSession,
  labels: AssistantLabels,
  locale: AppLocale,
): AssistantMessage {
  return {
    id: `disclosure-${session.id}`,
    role: "assistant",
    content: enforceAssistantIdentity(labels.firstMessage, locale),
    citations: [],
    actions: [],
    grounded: true,
    created_at: new Date().toISOString(),
  };
}

export function AssistantWidget({
  locale,
  settings,
  whatsapp,
  whatsappLabel,
  labels,
  api = engagementApi,
}: {
  locale: AppLocale;
  settings: AssistantPublicSettings;
  whatsapp: { enabled: boolean; phone: string; message: string };
  whatsappLabel: string;
  labels: AssistantLabels;
  api?: EngagementApi;
}) {
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<AssistantSession | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState("");
  const [starting, setStarting] = useState(false);
  const [sending, setSending] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [status, setStatus] = useState("");
  const [pendingRetry, setPendingRetry] = useState<AssistantMessageRequest | null>(null);
  const [retryAfter, setRetryAfter] = useState(0);
  const [verificationOpen, setVerificationOpen] = useState(false);
  const [orderNumber, setOrderNumber] = useState("");
  const [phone, setPhone] = useState("");
  const [verificationStatus, setVerificationStatus] = useState<
    "idle" | "pending" | "invalid" | "error" | "success"
  >("idle");
  const closeRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    closeRef.current?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    if (retryAfter <= 0) return;
    const timer = window.setInterval(() => setRetryAfter((value) => Math.max(0, value - 1)), 1_000);
    return () => window.clearInterval(timer);
  }, [retryAfter]);

  useEffect(() => {
    transcriptRef.current?.scrollTo?.({
      top: transcriptRef.current.scrollHeight,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }, [messages, sending]);

  if (!settings.enabled) return null;

  const start = async () => {
    if (starting) return;
    setStarting(true);
    setStatus("");
    try {
      const created = await api.createAssistantSession({
        locale,
        accepted_ai_disclosure: true,
      });
      setSession(created);
      setMessages([disclosureMessage(created, labels, locale)]);
      queueMicrotask(() => inputRef.current?.focus());
    } catch {
      setStatus(labels.genericError);
    } finally {
      setStarting(false);
    }
  };

  const sendRequest = async (
    request: AssistantMessageRequest,
    appendUser: boolean,
  ): Promise<AssistantMessage | null> => {
    if (!session || sending || retryAfter > 0) return null;
    setSending(true);
    setStatus("");
    setPendingRetry(null);
    if (appendUser) {
      setMessages((current) => [
        ...current,
        {
          id: request.client_message_id,
          role: "user",
          content: request.message,
          citations: [],
          actions: [],
          grounded: true,
          created_at: new Date().toISOString(),
        },
      ]);
    }
    try {
      const result = await api.sendAssistantMessage(session.id, request, locale);
      const message = {
        ...result.message,
        content: stripRepeatedAssistantDisclosure(result.message.content, [
          session.disclosure,
          settings.disclosure,
          labels.firstMessage,
        ]),
      };
      setMessages((current) => [...current, message]);
      return message;
    } catch (caught) {
      const seconds = caught instanceof EngagementError ? (caught.retryAfterSeconds ?? 0) : 0;
      setRetryAfter(seconds);
      setPendingRetry(request);
      setStatus(
        seconds > 0
          ? labels.rateLimited.replace("{seconds}", String(seconds))
          : labels.genericError,
      );
      return null;
    } finally {
      setSending(false);
    }
  };

  const submitMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = input.trim();
    if (!message) return;
    if (message.length > 1_000) {
      setStatus(labels.tooLong);
      return;
    }
    if (containsSensitiveChatInput(message)) {
      setStatus(labels.sensitive);
      setVerificationOpen(true);
      return;
    }
    const clientMessageId = crypto.randomUUID();
    setInput("");
    if (isAssistantIdentityQuestion(message)) {
      const createdAt = new Date().toISOString();
      setMessages((current) => [
        ...current,
        {
          id: clientMessageId,
          role: "user",
          content: message,
          citations: [],
          actions: [],
          grounded: true,
          created_at: createdAt,
        },
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: labels.identityAnswer,
          citations: [],
          actions: [],
          grounded: true,
          created_at: createdAt,
        },
      ]);
      return;
    }
    void sendRequest({ client_message_id: clientMessageId, message }, true);
  };

  const verifyOrder = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!session || sending) return;
    const number = orderNumber.trim().toUpperCase();
    if (!isValidAssistantOrderNumber(number) || !isValidBangladeshPhone(phone)) {
      setVerificationStatus("invalid");
      return;
    }
    setVerificationStatus("pending");
    try {
      const verification = await api.verifyAssistantOrder(session.id, {
        order_number: number,
        phone: normalizeBangladeshPhone(phone),
      });
      if (!verification.verified) throw new Error("Order verification was not accepted");
      const statusMessage = await sendRequest(
        { client_message_id: crypto.randomUUID(), message: labels.verification.statusRequest },
        true,
      );
      if (
        !statusMessage?.grounded ||
        !statusMessage.citations.some((citation) => citation.type === "order_status")
      ) {
        throw new Error("Grounded order status was unavailable");
      }
      setOrderNumber("");
      setPhone("");
      setVerificationStatus("success");
    } catch {
      setPhone("");
      setVerificationStatus("error");
    }
  };

  const deleteChat = async () => {
    if (!session || deleting) return;
    setDeleting(true);
    setStatus("");
    try {
      await api.deleteAssistantSession(session.id);
      setSession(null);
      setMessages([]);
      setPendingRetry(null);
      setOrderNumber("");
      setPhone("");
      setStatus(labels.deleted);
    } catch {
      setStatus(labels.genericError);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <button
        aria-label={labels.button}
        aria-expanded={open}
        className="fixed right-4 bottom-[calc(8.75rem+env(safe-area-inset-bottom))] z-[61] grid size-12 place-items-center rounded-full bg-deep-indigo text-white shadow-[0_10px_34px_rgb(42_21_101/0.35)] transition-transform hover:-translate-y-0.5 lg:right-20 lg:bottom-6"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <ChatCircleDots aria-hidden size={27} weight="duotone" />
      </button>
      {open ? (
        <section
          aria-label={labels.title}
          aria-modal="false"
          className="fixed inset-x-3 bottom-[calc(12.5rem+env(safe-area-inset-bottom))] z-[70] flex max-h-[min(70dvh,42rem)] flex-col overflow-hidden rounded-3xl border border-brand-purple/15 bg-white shadow-[0_24px_90px_rgb(42_21_101/0.32)] sm:left-auto sm:right-4 sm:w-[25rem] lg:right-6 lg:bottom-20"
          role="dialog"
        >
          <header className="flex items-center gap-3 border-b border-brand-purple/10 p-4">
            <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-soft-lavender text-brand-purple">
              <Robot aria-hidden size={25} weight="duotone" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-lg font-extrabold">
                {settings.display_name || labels.title}
              </h2>
              <p className="text-xs font-bold text-brand-purple">{labels.disclosureLabel}</p>
            </div>
            <button
              ref={closeRef}
              aria-label={labels.close}
              className="grid size-11 place-items-center rounded-full hover:bg-soft-lavender"
              onClick={() => setOpen(false)}
              type="button"
            >
              <X aria-hidden size={21} />
            </button>
          </header>
          <aside className="flex gap-2 bg-sale-amber/10 px-4 py-3 text-xs leading-5 text-deep-indigo">
            <WarningCircle aria-hidden className="mt-0.5 shrink-0" size={18} weight="duotone" />
            <p>{settings.disclosure || labels.firstMessage}</p>
          </aside>

          {!session ? (
            <div className="grid min-h-64 place-content-center p-6 text-center">
              <ShieldCheck
                aria-hidden
                className="mx-auto text-brand-purple"
                size={48}
                weight="duotone"
              />
              <p className="mt-4 text-sm leading-6 text-muted">{labels.firstMessage}</p>
              <button
                className="signature-gradient mt-5 min-h-12 rounded-full px-6 font-extrabold text-white disabled:opacity-55"
                disabled={starting}
                onClick={() => void start()}
                type="button"
              >
                {starting ? labels.starting : labels.start}
              </button>
              {status ? (
                <p className="mt-3 text-sm font-bold text-error" role="alert">
                  {status}
                </p>
              ) : null}
            </div>
          ) : (
            <>
              <div
                ref={transcriptRef}
                aria-label={labels.title}
                aria-live="polite"
                aria-relevant="additions text"
                className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4"
                role="log"
              >
                {messages.map((message) => (
                  <AssistantMessageBubble
                    key={message.id}
                    labels={labels}
                    locale={locale}
                    message={message}
                    onVerify={() => setVerificationOpen(true)}
                    whatsapp={whatsapp}
                    whatsappLabel={whatsappLabel}
                  />
                ))}
                {sending ? (
                  <p className="text-sm font-bold text-muted" role="status">
                    {labels.sending}
                  </p>
                ) : null}
              </div>

              {verificationOpen ? (
                <form
                  className="border-t border-brand-purple/10 bg-page-background p-4"
                  onSubmit={(event) => void verifyOrder(event)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-base font-extrabold">{labels.verification.title}</h3>
                      <p className="mt-1 text-xs leading-5 text-muted">
                        {labels.verification.description}
                      </p>
                    </div>
                    <LockKey
                      aria-hidden
                      className="shrink-0 text-brand-purple"
                      size={23}
                      weight="duotone"
                    />
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    <label>
                      <span className="sr-only">{labels.verification.number}</span>
                      <input
                        autoComplete="off"
                        className="min-h-11 w-full rounded-xl border border-brand-purple/20 bg-white px-3 text-sm"
                        maxLength={18}
                        onChange={(event) => {
                          setOrderNumber(event.target.value);
                          setVerificationStatus("idle");
                        }}
                        placeholder={labels.verification.number}
                        value={orderNumber}
                      />
                    </label>
                    <label>
                      <span className="sr-only">{labels.verification.phone}</span>
                      <input
                        autoComplete="off"
                        className="min-h-11 w-full rounded-xl border border-brand-purple/20 bg-white px-3 text-sm"
                        inputMode="tel"
                        maxLength={24}
                        onChange={(event) => {
                          setPhone(event.target.value);
                          setVerificationStatus("idle");
                        }}
                        placeholder={labels.verification.phone}
                        type="tel"
                        value={phone}
                      />
                    </label>
                  </div>
                  <button
                    className="mt-3 min-h-11 w-full rounded-full bg-deep-indigo px-4 font-bold text-white disabled:opacity-55"
                    disabled={verificationStatus === "pending" || sending}
                    type="submit"
                  >
                    {verificationStatus === "pending"
                      ? labels.verification.submitting
                      : labels.verification.submit}
                  </button>
                  {verificationStatus === "error" || verificationStatus === "invalid" ? (
                    <p className="mt-2 text-xs font-bold text-error" role="alert">
                      {verificationStatus === "error"
                        ? labels.verification.failure
                        : labels.verification.invalid}
                    </p>
                  ) : null}
                  {verificationStatus === "success" ? (
                    <p
                      className="mt-2 flex items-center gap-2 text-xs font-bold text-success"
                      role="status"
                    >
                      <CheckCircle aria-hidden size={18} weight="fill" />{" "}
                      {labels.verification.result}
                    </p>
                  ) : null}
                </form>
              ) : (
                <button
                  className="mx-4 mb-2 min-h-11 rounded-xl border border-brand-purple/15 px-4 text-sm font-extrabold text-brand-purple"
                  onClick={() => setVerificationOpen(true)}
                  type="button"
                >
                  <LockKey aria-hidden className="mr-2 inline" size={17} />
                  {labels.verification.open}
                </button>
              )}

              <div className="border-t border-brand-purple/10 p-3">
                {status ? (
                  <div
                    className="mb-2 rounded-xl bg-error/8 p-3 text-xs font-bold text-error"
                    role="alert"
                  >
                    <p>{status}</p>
                    {pendingRetry ? (
                      <button
                        className="mt-2 inline-flex min-h-11 items-center gap-2 text-deep-indigo disabled:opacity-50"
                        disabled={sending || retryAfter > 0}
                        onClick={() => void sendRequest(pendingRetry, false)}
                        type="button"
                      >
                        <ArrowClockwise aria-hidden size={17} /> {labels.retry}
                      </button>
                    ) : null}
                  </div>
                ) : null}
                <form className="flex items-end gap-2" onSubmit={submitMessage}>
                  <label className="min-w-0 flex-1">
                    <span className="sr-only">{labels.inputLabel}</span>
                    <textarea
                      ref={inputRef}
                      className="max-h-28 min-h-12 w-full resize-none rounded-2xl border border-brand-purple/20 px-3 py-2 text-sm"
                      maxLength={1_001}
                      onChange={(event) => {
                        setInput(event.target.value);
                        setStatus("");
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          event.currentTarget.form?.requestSubmit();
                        }
                      }}
                      placeholder={labels.placeholder}
                      rows={1}
                      value={input}
                    />
                  </label>
                  <button
                    aria-label={labels.send}
                    className="grid size-12 shrink-0 place-items-center rounded-full bg-brand-purple text-white disabled:opacity-55"
                    disabled={sending || !input.trim() || retryAfter > 0}
                    type="submit"
                  >
                    <PaperPlaneRight aria-hidden size={21} weight="fill" />
                  </button>
                </form>
                <button
                  className="mt-2 inline-flex min-h-11 items-center gap-2 px-2 text-xs font-bold text-muted hover:text-error"
                  disabled={deleting}
                  onClick={() => void deleteChat()}
                  type="button"
                >
                  <Trash aria-hidden size={17} /> {deleting ? labels.deleting : labels.delete}
                </button>
              </div>
            </>
          )}
        </section>
      ) : null}
    </>
  );
}

function AssistantMessageBubble({
  message,
  labels,
  locale,
  onVerify,
  whatsapp,
  whatsappLabel,
}: {
  message: AssistantMessage;
  labels: AssistantLabels;
  locale: AppLocale;
  onVerify: () => void;
  whatsapp: { enabled: boolean; phone: string; message: string };
  whatsappLabel: string;
}) {
  const assistant = message.role === "assistant";
  return (
    <article
      className={`max-w-[92%] rounded-2xl p-3 text-sm leading-6 ${assistant ? "mr-auto bg-soft-lavender/55 text-ink" : "ml-auto bg-brand-purple text-white"}`}
    >
      <p>{message.content}</p>
      {assistant && message.citations.length ? (
        <div className="mt-3 border-t border-brand-purple/10 pt-2">
          <p className="text-xs font-extrabold text-deep-indigo">{labels.citations}</p>
          <ul className="mt-1 space-y-1">
            {message.citations.map((citation) => (
              <li key={citation.id}>
                {citation.href ? (
                  <Link
                    className="inline-flex min-h-11 items-center gap-1 font-bold text-brand-purple underline decoration-brand-purple/30 underline-offset-2"
                    href={citation.href}
                  >
                    <LinkSimple aria-hidden size={15} /> {citation.label}
                  </Link>
                ) : (
                  <span className="text-xs text-muted">{citation.label}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {assistant && message.actions.length ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {message.actions.map((action, index) => {
            if (action.type === "verify_order") {
              return (
                <button
                  key={`${action.type}-${index}`}
                  className="min-h-11 rounded-full border border-brand-purple/20 px-3 font-bold text-brand-purple"
                  onClick={onVerify}
                  type="button"
                >
                  {action.label}
                </button>
              );
            }
            if (action.type === "whatsapp_handoff") {
              return (
                <WhatsAppButton
                  key={`${action.type}-${index}`}
                  showLabel
                  className="text-xs"
                  label={action.label || labels.handoff}
                  settings={whatsapp}
                />
              );
            }
            return action.href ? (
              <Link
                key={`${action.type}-${index}`}
                className="inline-flex min-h-11 items-center rounded-full border border-brand-purple/20 px-3 font-bold text-brand-purple"
                href={action.href}
              >
                {action.label}
              </Link>
            ) : null;
          })}
        </div>
      ) : null}
      {assistant && !message.grounded ? (
        <div className="mt-3 rounded-xl bg-white/70 p-3">
          <p className="text-xs text-muted">{labels.uncertain}</p>
          <WhatsAppButton
            showLabel
            className="mt-2 text-xs"
            label={whatsappLabel}
            settings={whatsapp}
          />
        </div>
      ) : null}
      <span className="sr-only">{assistant ? labels.disclosureLabel : locale}</span>
    </article>
  );
}
