"use client";

import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  CurrencyCircleDollar,
  IdentificationCard,
  LockKey,
  MapPin,
  Package,
  ShieldCheck,
  Truck,
  UserCircle,
} from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { CartTotals, type CartTotalsLabels } from "@/components/commerce/cart-totals";
import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import { loginHref } from "@/lib/account/return-to";
import { CommerceError } from "@/lib/commerce/client";
import { secondsUntil } from "@/lib/commerce/auth";
import {
  clearSubmissionKey,
  digestOrderRequest,
  isValidBangladeshPhone,
  normalizeBangladeshPhone,
  readSubmissionKey,
  type SubmissionKey,
  submissionKeyForDigest,
  writeSubmissionKey,
} from "@/lib/commerce/checkout";
import type {
  CheckoutDetails,
  CheckoutQuoteResponse,
  FieldError as CommerceFieldError,
  GeoOption,
  PlaceOrderRequest,
} from "@/lib/commerce/types";
import { formatNumber } from "@/lib/format-number";
import { formatPrice } from "@/lib/format-price";

export type CheckoutForm = {
  customerName: string;
  customerPhone: string;
  email: string;
  recipient: string;
  shippingPhone: string;
  divisionId: string;
  districtId: string;
  upazilaId: string;
  addressLine: string;
  notes: string;
};

export type FormErrors = Partial<Record<keyof CheckoutForm, string>>;

export type CheckoutLabels = {
  title: string;
  eyebrow: string;
  subtitle: string;
  loading: string;
  emptyTitle: string;
  emptyDescription: string;
  backToCart: string;
  account: {
    title: string;
    guest: string;
    signedIn: string;
    signIn: string;
  };
  contact: {
    title: string;
    name: string;
    phone: string;
    email: string;
    emailOptional: string;
  };
  address: {
    title: string;
    recipient: string;
    phone: string;
    division: string;
    district: string;
    upazila: string;
    line: string;
    linePlaceholder: string;
    notes: string;
    notesOptional: string;
    selectDivision: string;
    selectDistrict: string;
    selectUpazila: string;
    loading: string;
    error: string;
  };
  payment: {
    title: string;
    cod: string;
    codDescription: string;
    onlyCod: string;
  };
  review: {
    title: string;
    quote: string;
    quoting: string;
    expires: string;
    expiresIn: string;
    place: string;
    placing: string;
    editNotice: string;
    itemCount: string;
  };
  validation: {
    required: string;
    nameLength: string;
    addressLength: string;
    notesLength: string;
    phone: string;
    email: string;
    invalid: string;
  };
  conflict: {
    title: string;
    stock: string;
    quote: string;
    codRisk: string;
    authRequired: string;
    generic: string;
    unknown: string;
    quoteExpired: string;
    retryQuote: string;
  };
  secure: string;
  serverVerified: string;
  totals: CartTotalsLabels;
};

const initialForm: CheckoutForm = {
  customerName: "",
  customerPhone: "",
  email: "",
  recipient: "",
  shippingPhone: "",
  divisionId: "",
  districtId: "",
  upazilaId: "",
  addressLine: "",
  notes: "",
};

export function validateCheckoutForm(
  form: CheckoutForm,
  labels: CheckoutLabels["validation"],
): FormErrors {
  const errors: FormErrors = {};
  const required: Array<keyof CheckoutForm> = [
    "customerName",
    "customerPhone",
    "recipient",
    "shippingPhone",
    "divisionId",
    "districtId",
    "upazilaId",
    "addressLine",
  ];
  required.forEach((field) => {
    if (!form[field].trim()) errors[field] = labels.required;
  });
  if (form.customerName.trim() && form.customerName.trim().length < 2) {
    errors.customerName = labels.nameLength;
  }
  if (form.recipient.trim() && form.recipient.trim().length < 2) {
    errors.recipient = labels.nameLength;
  }
  if (form.addressLine.trim() && form.addressLine.trim().length < 5) {
    errors.addressLine = labels.addressLength;
  }
  if (form.notes.length > 500) errors.notes = labels.notesLength;
  if (form.customerPhone && !isValidBangladeshPhone(form.customerPhone)) {
    errors.customerPhone = labels.phone;
  }
  if (form.shippingPhone && !isValidBangladeshPhone(form.shippingPhone)) {
    errors.shippingPhone = labels.phone;
  }
  if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errors.email = labels.email;
  return errors;
}

const checkoutFieldMap: Record<string, keyof CheckoutForm> = {
  "customer.name": "customerName",
  "customer.phone": "customerPhone",
  "customer.email": "email",
  "shipping_address.recipient": "recipient",
  "shipping_address.phone": "shippingPhone",
  "shipping_address.division_id": "divisionId",
  "shipping_address.district_id": "districtId",
  "shipping_address.upazila_id": "upazilaId",
  "shipping_address.address_line": "addressLine",
  notes: "notes",
};

export function mapCheckoutFieldErrors(
  fieldErrors: CommerceFieldError[],
  labels: CheckoutLabels["validation"],
): FormErrors {
  const errors: FormErrors = {};
  for (const error of fieldErrors) {
    if (error.field === "shipping_address") {
      errors.divisionId = labels.invalid;
      errors.districtId = labels.invalid;
      errors.upazilaId = labels.invalid;
      continue;
    }
    const field = checkoutFieldMap[error.field];
    if (!field) continue;
    if (field === "customerName" || field === "recipient") errors[field] = labels.nameLength;
    else if (field === "customerPhone" || field === "shippingPhone") errors[field] = labels.phone;
    else if (field === "email") errors[field] = labels.email;
    else if (field === "addressLine") errors[field] = labels.addressLength;
    else if (field === "notes") errors[field] = labels.notesLength;
    else errors[field] = labels.invalid;
  }
  return errors;
}

function detailsFromForm(form: CheckoutForm): CheckoutDetails {
  return {
    customer: {
      name: form.customerName.trim(),
      phone: normalizeBangladeshPhone(form.customerPhone),
      email: form.email.trim() || null,
    },
    shipping_address: {
      recipient: form.recipient.trim(),
      phone: normalizeBangladeshPhone(form.shippingPhone),
      division_id: form.divisionId,
      district_id: form.districtId,
      upazila_id: form.upazilaId,
      address_line: form.addressLine.trim(),
    },
    notes: form.notes.trim() || null,
    payment_method: "cod",
  };
}

function conflictMessage(error: CommerceError, labels: CheckoutLabels["conflict"]): string {
  if (error.code === "PHONE_AUTHENTICATION_REQUIRED") return labels.authRequired;
  if (
    [
      "OUT_OF_STOCK",
      "INSUFFICIENT_STOCK",
      "VARIANT_UNAVAILABLE",
      "FLASH_QUANTITY_UNAVAILABLE",
      "CART_NOT_READY",
    ].includes(error.code)
  )
    return labels.stock;
  if (["QUOTE_CHANGED", "QUOTE_EXPIRED", "QUOTE_INVALID", "INVALID_QUOTE"].includes(error.code))
    return labels.quote;
  if (
    [
      "COD_RISK",
      "COD_NOT_ALLOWED",
      "ADVANCE_PAYMENT_REQUIRED",
      "COD_ADVANCE_PAYMENT_REQUIRED",
    ].includes(error.code)
  ) {
    return labels.codRisk;
  }
  return labels.generic;
}

export function isAmbiguousOrderError(error: CommerceError): boolean {
  return error.status === null || ["NETWORK_ERROR", "INVALID_RESPONSE"].includes(error.code);
}

function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? (
    <p className="mt-1 text-xs font-bold text-error" id={id} role="alert">
      {message}
    </p>
  ) : null;
}

export function CheckoutClient({ locale, labels }: { locale: AppLocale; labels: CheckoutLabels }) {
  const router = useRouter();
  const {
    cart,
    session,
    isBootstrapping,
    isReady,
    pendingAction,
    createQuote,
    placeOrder,
    getDivisions,
    getDistricts,
    getUpazilas,
  } = useCommerce();
  const [form, setForm] = useState(initialForm);
  const [formErrors, setFormErrors] = useState<FormErrors>({});
  const [divisions, setDivisions] = useState<GeoOption[]>([]);
  const [districts, setDistricts] = useState<GeoOption[]>([]);
  const [upazilas, setUpazilas] = useState<GeoOption[]>([]);
  const [geoLoading, setGeoLoading] = useState(true);
  const [geoError, setGeoError] = useState("");
  const [quote, setQuote] = useState<CheckoutQuoteResponse | null>(null);
  const [quoteNow, setQuoteNow] = useState(() => Date.now());
  const [conflict, setConflict] = useState("");
  const submissionKey = useRef<SubmissionKey | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getDivisions(controller.signal)
      .then((items) => {
        setDivisions(items);
        setGeoError("");
      })
      .catch(() => {
        if (!controller.signal.aborted) setGeoError(labels.address.error);
      })
      .finally(() => {
        if (!controller.signal.aborted) setGeoLoading(false);
      });
    return () => controller.abort();
  }, [getDivisions, labels.address.error]);

  useEffect(() => {
    if (!quote) return;
    const expiresAt = Date.parse(quote.expires_at);
    const expire = () => {
      setQuote(null);
      setConflict(labels.conflict.quoteExpired);
    };
    const timeout = window.setTimeout(
      expire,
      Number.isFinite(expiresAt) ? Math.max(0, expiresAt - Date.now()) : 0,
    );
    const ticker = window.setInterval(() => setQuoteNow(Date.now()), 1_000);
    return () => {
      window.clearTimeout(timeout);
      window.clearInterval(ticker);
    };
  }, [labels.conflict.quoteExpired, quote]);

  const quoteExpiresAt = quote ? Date.parse(quote.expires_at) : 0;
  const quoteExpired = Boolean(
    quote && (!Number.isFinite(quoteExpiresAt) || quoteExpiresAt <= quoteNow),
  );
  const validQuote = quoteExpired ? null : quote;
  const quoteSecondsRemaining = validQuote ? secondsUntil(quoteExpiresAt, quoteNow) : 0;

  const edit = <Field extends keyof CheckoutForm>(field: Field, value: CheckoutForm[Field]) => {
    setForm((current) => ({ ...current, [field]: value }));
    setFormErrors((current) => ({ ...current, [field]: undefined }));
    setQuote(null);
    setConflict("");
    submissionKey.current = null;
    clearSubmissionKey();
  };

  const requestQuote = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextErrors = validateCheckoutForm(form, labels.validation);
    setFormErrors(nextErrors);
    if (Object.keys(nextErrors).length) return;
    setConflict("");
    try {
      const nextQuote = await createQuote(detailsFromForm(form));
      setQuoteNow(Date.now());
      setQuote(nextQuote);
    } catch (error) {
      const normalized =
        error instanceof CommerceError ? error : new CommerceError(labels.conflict.generic);
      const structuredErrors = mapCheckoutFieldErrors(normalized.fieldErrors, labels.validation);
      if (Object.keys(structuredErrors).length) setFormErrors(structuredErrors);
      setConflict(conflictMessage(normalized, labels.conflict));
    }
  };

  const submitOrder = async () => {
    if (!validQuote || Date.now() >= quoteExpiresAt || pendingAction === "checkout") return;
    const request: PlaceOrderRequest = {
      ...detailsFromForm(form),
      quote_token: validQuote.quote_token,
    };
    setConflict("");
    try {
      const digest = await digestOrderRequest(request);
      submissionKey.current = submissionKeyForDigest(
        submissionKey.current ?? readSubmissionKey(),
        digest,
      );
      writeSubmissionKey(submissionKey.current);
      const response = await placeOrder(request, submissionKey.current.key);
      clearSubmissionKey();
      submissionKey.current = null;
      router.push(`/${locale}/order-success/${encodeURIComponent(response.order.number)}`);
    } catch (error) {
      const normalized =
        error instanceof CommerceError ? error : new CommerceError(labels.conflict.generic);
      const structuredErrors = mapCheckoutFieldErrors(normalized.fieldErrors, labels.validation);
      if (Object.keys(structuredErrors).length) setFormErrors(structuredErrors);
      setConflict(
        isAmbiguousOrderError(normalized)
          ? labels.conflict.unknown
          : conflictMessage(normalized, labels.conflict),
      );
      if (
        [
          "OUT_OF_STOCK",
          "INSUFFICIENT_STOCK",
          "VARIANT_UNAVAILABLE",
          "FLASH_QUANTITY_UNAVAILABLE",
          "CART_NOT_READY",
          "QUOTE_CHANGED",
          "QUOTE_EXPIRED",
          "QUOTE_INVALID",
        ].includes(normalized.code)
      ) {
        setQuote(null);
      }
    }
  };

  if (!cart && isBootstrapping) {
    return <div className="container-shell py-16 font-bold text-muted">{labels.loading}</div>;
  }

  if (!cart?.items.length) {
    return (
      <div className="container-shell grid min-h-[60vh] place-content-center py-16 text-center">
        <Package aria-hidden className="mx-auto text-brand-purple" size={64} weight="duotone" />
        <h1 className="mt-5 text-3xl font-extrabold">{labels.emptyTitle}</h1>
        <p className="mx-auto mt-3 max-w-md text-muted">{labels.emptyDescription}</p>
        <Link
          className="mx-auto mt-7 inline-flex min-h-12 items-center gap-2 rounded-full bg-deep-indigo px-6 font-extrabold text-white"
          href={`/${locale}/cart`}
        >
          <ArrowLeft aria-hidden size={18} weight="bold" /> {labels.backToCart}
        </Link>
      </div>
    );
  }

  const authoritativeCart = validQuote?.cart ?? cart;
  const fieldClass =
    "mt-1 min-h-12 w-full rounded-xl border border-brand-purple/20 bg-white px-4 focus:border-brand-purple focus:outline-none";

  return (
    <div className="container-shell py-9 sm:py-14">
      <div className="max-w-3xl">
        <p className="font-bold tracking-wide text-brand-purple uppercase">{labels.eyebrow}</p>
        <h1 className="mt-2 text-4xl font-extrabold sm:text-5xl">{labels.title}</h1>
        <p className="mt-3 text-muted">{labels.subtitle}</p>
      </div>

      <div className="mt-8 grid items-start gap-7 lg:grid-cols-[minmax(0,1fr)_23rem]">
        <form className="space-y-5" noValidate onSubmit={(event) => void requestQuote(event)}>
          <section className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-7">
            <h2 className="flex items-center gap-2 text-xl font-extrabold">
              <UserCircle aria-hidden className="text-brand-purple" size={27} weight="duotone" />
              {labels.account.title}
            </h2>
            {session?.authenticated && session.user ? (
              <p className="mt-3 rounded-xl bg-success/10 px-4 py-3 text-sm font-bold text-success">
                {labels.account.signedIn.replace("{name}", session.user.name)}
              </p>
            ) : (
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-soft-lavender px-4 py-3 text-sm">
                <p className="text-muted">{labels.account.guest}</p>
                <Link
                  className="min-h-11 py-2 font-extrabold text-brand-purple"
                  href={loginHref(locale, `/${locale}/checkout`)}
                >
                  {labels.account.signIn}
                </Link>
              </div>
            )}
          </section>

          <section className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-7">
            <h2 className="flex items-center gap-2 text-xl font-extrabold">
              <IdentificationCard
                aria-hidden
                className="text-brand-purple"
                size={27}
                weight="duotone"
              />
              {labels.contact.title}
            </h2>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label>
                <span className="font-bold text-deep-indigo">{labels.contact.name}</span>
                <input
                  aria-label={labels.contact.name}
                  aria-describedby={formErrors.customerName ? "customer-name-error" : undefined}
                  aria-invalid={Boolean(formErrors.customerName)}
                  autoComplete="name"
                  className={fieldClass}
                  maxLength={160}
                  minLength={2}
                  onChange={(event) => edit("customerName", event.target.value)}
                  value={form.customerName}
                />
                <FieldError id="customer-name-error" message={formErrors.customerName} />
              </label>
              <label>
                <span className="font-bold text-deep-indigo">{labels.contact.phone}</span>
                <input
                  aria-label={labels.contact.phone}
                  aria-describedby={formErrors.customerPhone ? "customer-phone-error" : undefined}
                  aria-invalid={Boolean(formErrors.customerPhone)}
                  autoComplete="tel"
                  className={fieldClass}
                  inputMode="tel"
                  maxLength={24}
                  onChange={(event) => edit("customerPhone", event.target.value)}
                  placeholder="01XXXXXXXXX"
                  value={form.customerPhone}
                />
                <FieldError id="customer-phone-error" message={formErrors.customerPhone} />
              </label>
              <label className="sm:col-span-2">
                <span className="font-bold text-deep-indigo">
                  {labels.contact.email}{" "}
                  <span className="font-normal text-muted">({labels.contact.emailOptional})</span>
                </span>
                <input
                  aria-label={labels.contact.email}
                  aria-describedby={formErrors.email ? "email-error" : undefined}
                  aria-invalid={Boolean(formErrors.email)}
                  autoComplete="email"
                  className={fieldClass}
                  inputMode="email"
                  maxLength={254}
                  onChange={(event) => edit("email", event.target.value)}
                  type="email"
                  value={form.email}
                />
                <FieldError id="email-error" message={formErrors.email} />
              </label>
            </div>
          </section>

          <section className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-7">
            <h2 className="flex items-center gap-2 text-xl font-extrabold">
              <MapPin aria-hidden className="text-brand-purple" size={27} weight="duotone" />
              {labels.address.title}
            </h2>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label>
                <span className="font-bold text-deep-indigo">{labels.address.recipient}</span>
                <input
                  aria-label={labels.address.recipient}
                  aria-describedby={formErrors.recipient ? "recipient-error" : undefined}
                  aria-invalid={Boolean(formErrors.recipient)}
                  autoComplete="shipping name"
                  className={fieldClass}
                  maxLength={160}
                  minLength={2}
                  onChange={(event) => edit("recipient", event.target.value)}
                  value={form.recipient}
                />
                <FieldError id="recipient-error" message={formErrors.recipient} />
              </label>
              <label>
                <span className="font-bold text-deep-indigo">{labels.address.phone}</span>
                <input
                  aria-label={labels.address.phone}
                  aria-describedby={formErrors.shippingPhone ? "shipping-phone-error" : undefined}
                  aria-invalid={Boolean(formErrors.shippingPhone)}
                  autoComplete="shipping tel"
                  className={fieldClass}
                  inputMode="tel"
                  maxLength={24}
                  onChange={(event) => edit("shippingPhone", event.target.value)}
                  placeholder="01XXXXXXXXX"
                  value={form.shippingPhone}
                />
                <FieldError id="shipping-phone-error" message={formErrors.shippingPhone} />
              </label>
              <label>
                <span className="font-bold text-deep-indigo">{labels.address.division}</span>
                <select
                  aria-label={labels.address.division}
                  aria-describedby={formErrors.divisionId ? "division-error" : undefined}
                  aria-invalid={Boolean(formErrors.divisionId)}
                  className={fieldClass}
                  disabled={geoLoading}
                  onChange={async (event) => {
                    const value = event.target.value;
                    edit("divisionId", value);
                    setForm((current) => ({ ...current, districtId: "", upazilaId: "" }));
                    setDistricts([]);
                    setUpazilas([]);
                    if (!value) return;
                    setGeoLoading(true);
                    try {
                      setDistricts(await getDistricts(value));
                      setGeoError("");
                    } catch {
                      setGeoError(labels.address.error);
                    } finally {
                      setGeoLoading(false);
                    }
                  }}
                  value={form.divisionId}
                >
                  <option value="">{labels.address.selectDivision}</option>
                  {divisions.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
                <FieldError id="division-error" message={formErrors.divisionId} />
              </label>
              <label>
                <span className="font-bold text-deep-indigo">{labels.address.district}</span>
                <select
                  aria-label={labels.address.district}
                  aria-describedby={formErrors.districtId ? "district-error" : undefined}
                  aria-invalid={Boolean(formErrors.districtId)}
                  className={fieldClass}
                  disabled={!form.divisionId || geoLoading}
                  onChange={async (event) => {
                    const value = event.target.value;
                    edit("districtId", value);
                    setForm((current) => ({ ...current, upazilaId: "" }));
                    setUpazilas([]);
                    if (!value) return;
                    setGeoLoading(true);
                    try {
                      setUpazilas(await getUpazilas(value));
                      setGeoError("");
                    } catch {
                      setGeoError(labels.address.error);
                    } finally {
                      setGeoLoading(false);
                    }
                  }}
                  value={form.districtId}
                >
                  <option value="">{labels.address.selectDistrict}</option>
                  {districts.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
                <FieldError id="district-error" message={formErrors.districtId} />
              </label>
              <label className="sm:col-span-2">
                <span className="font-bold text-deep-indigo">{labels.address.upazila}</span>
                <select
                  aria-label={labels.address.upazila}
                  aria-describedby={formErrors.upazilaId ? "upazila-error" : undefined}
                  aria-invalid={Boolean(formErrors.upazilaId)}
                  className={fieldClass}
                  disabled={!form.districtId || geoLoading}
                  onChange={(event) => edit("upazilaId", event.target.value)}
                  value={form.upazilaId}
                >
                  <option value="">{labels.address.selectUpazila}</option>
                  {upazilas.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
                <FieldError id="upazila-error" message={formErrors.upazilaId} />
              </label>
              {geoLoading ? (
                <p className="text-sm text-muted sm:col-span-2">{labels.address.loading}</p>
              ) : null}
              {geoError ? (
                <p className="text-sm font-bold text-error sm:col-span-2" role="alert">
                  {geoError}
                </p>
              ) : null}
              <label className="sm:col-span-2">
                <span className="font-bold text-deep-indigo">{labels.address.line}</span>
                <textarea
                  aria-label={labels.address.line}
                  aria-describedby={formErrors.addressLine ? "address-line-error" : undefined}
                  aria-invalid={Boolean(formErrors.addressLine)}
                  autoComplete="shipping street-address"
                  className={`${fieldClass} min-h-28 py-3`}
                  maxLength={500}
                  minLength={5}
                  onChange={(event) => edit("addressLine", event.target.value)}
                  placeholder={labels.address.linePlaceholder}
                  value={form.addressLine}
                />
                <FieldError id="address-line-error" message={formErrors.addressLine} />
              </label>
              <label className="sm:col-span-2">
                <span className="font-bold text-deep-indigo">
                  {labels.address.notes}{" "}
                  <span className="font-normal text-muted">({labels.address.notesOptional})</span>
                </span>
                <textarea
                  aria-label={labels.address.notes}
                  aria-describedby={formErrors.notes ? "notes-error" : undefined}
                  aria-invalid={Boolean(formErrors.notes)}
                  className={`${fieldClass} min-h-24 py-3`}
                  maxLength={500}
                  onChange={(event) => edit("notes", event.target.value)}
                  value={form.notes}
                />
                <FieldError id="notes-error" message={formErrors.notes} />
              </label>
            </div>
          </section>

          <section className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-7">
            <h2 className="flex items-center gap-2 text-xl font-extrabold">
              <CurrencyCircleDollar
                aria-hidden
                className="text-brand-purple"
                size={27}
                weight="duotone"
              />
              {labels.payment.title}
            </h2>
            <label className="mt-5 flex min-h-20 items-center gap-4 rounded-2xl border-2 border-brand-purple bg-soft-lavender/50 p-4">
              <input checked className="size-5 accent-brand-purple" readOnly type="radio" />
              <span className="min-w-0 flex-1">
                <strong className="block text-deep-indigo">{labels.payment.cod}</strong>
                <span className="text-sm text-muted">{labels.payment.codDescription}</span>
              </span>
              <CheckCircle aria-hidden className="shrink-0 text-success" size={27} weight="fill" />
            </label>
            <p className="mt-3 text-xs text-muted">{labels.payment.onlyCod}</p>
          </section>

          {conflict ? (
            <section className="rounded-2xl border border-error/20 bg-error/5 p-5" role="alert">
              <h2 className="text-lg font-extrabold text-error">{labels.conflict.title}</h2>
              <p className="mt-1 text-sm text-deep-indigo">{conflict}</p>
              {!validQuote ? (
                <p className="mt-2 text-sm font-bold text-brand-purple">
                  {labels.conflict.retryQuote}
                </p>
              ) : null}
            </section>
          ) : null}

          {!validQuote ? (
            <button
              className="signature-gradient min-h-13 w-full rounded-full px-7 font-extrabold text-white shadow-lg disabled:opacity-55"
              disabled={!isReady || pendingAction === "checkout"}
              type="submit"
            >
              {pendingAction === "checkout" ? labels.review.quoting : labels.review.quote}
            </button>
          ) : (
            <div className="rounded-2xl border border-success/20 bg-success/5 p-5">
              <p className="flex items-center gap-2 font-bold text-success">
                <CheckCircle aria-hidden size={22} weight="fill" /> {labels.review.expires}
              </p>
              <p className="mt-1 text-sm font-bold text-deep-indigo" role="timer">
                {labels.review.expiresIn.replace(
                  "{seconds}",
                  formatNumber(quoteSecondsRemaining, locale),
                )}
              </p>
              <button
                className="signature-gradient mt-4 inline-flex min-h-13 w-full items-center justify-center gap-2 rounded-full px-7 font-extrabold text-white shadow-lg disabled:opacity-55"
                disabled={!isReady || pendingAction === "checkout" || quoteSecondsRemaining <= 0}
                onClick={() => void submitOrder()}
                type="button"
              >
                {pendingAction === "checkout" ? labels.review.placing : labels.review.place}
                <ArrowRight aria-hidden size={19} weight="bold" />
              </button>
              <p className="mt-2 text-center text-xs text-muted">{labels.review.editNotice}</p>
            </div>
          )}
        </form>

        <aside className="rounded-3xl border border-brand-purple/10 bg-white p-6 shadow-soft lg:sticky lg:top-28">
          <h2 className="flex items-center gap-2 text-xl font-extrabold">
            <Truck aria-hidden className="text-brand-purple" size={25} weight="duotone" />
            {labels.review.title}
          </h2>
          <div className="mt-5 space-y-3 border-b border-brand-purple/10 pb-5">
            {authoritativeCart.items.map((item) => (
              <div key={item.id} className="flex items-start justify-between gap-3 text-sm">
                <p className="min-w-0 text-muted">
                  <strong className="line-clamp-1 text-deep-indigo">{item.product.name}</strong>
                  {labels.review.itemCount.replace("{count}", formatNumber(item.quantity, locale))}
                </p>
                <strong className="shrink-0 text-deep-indigo">
                  {formatPrice(item.line_total_poisha, locale)}
                </strong>
              </div>
            ))}
          </div>
          <div className="mt-5">
            <CartTotals
              hasShipping={Boolean(authoritativeCart.shipping || quote)}
              labels={labels.totals}
              locale={locale}
              totals={authoritativeCart.totals}
            />
          </div>
          <p className="mt-5 flex items-start gap-2 rounded-xl bg-soft-lavender p-3 text-xs leading-5 text-muted">
            <LockKey
              aria-hidden
              className="mt-0.5 shrink-0 text-brand-purple"
              size={18}
              weight="duotone"
            />
            {labels.secure}
          </p>
          <div className="mt-3 flex items-center justify-center gap-2 text-xs font-bold text-success">
            <ShieldCheck aria-hidden size={18} weight="duotone" /> {labels.serverVerified}
          </div>
        </aside>
      </div>
    </div>
  );
}
