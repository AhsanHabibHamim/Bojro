"use client";

import { FloppyDisk, Warning } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import type { AccountApi } from "@/lib/account/client";
import {
  isStaleWrite,
  requireAccountEtag,
  useAccountApi,
  useAccountQuery,
  useIdempotentMutation,
} from "@/lib/account/hooks";
import type { AddressInput } from "@/lib/account/types";
import { isAmbiguousMutationError } from "@/lib/account/idempotency";
import { isValidBangladeshPhone, normalizeBangladeshPhone } from "@/lib/commerce/checkout";
import type { GeoOption } from "@/lib/commerce/types";

import {
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
} from "../shared/account-page-state";

const emptyAddress: AddressInput = {
  label: "",
  recipient: "",
  phone: "",
  division_id: "",
  district_id: "",
  upazila_id: "",
  address_line: "",
  is_default: false,
};

function toAddressInput(
  address: Awaited<ReturnType<AccountApi["address"]>>["data"] | undefined,
): AddressInput {
  if (!address) return emptyAddress;
  return {
    label: address.label,
    recipient: address.recipient,
    phone: address.phone,
    division_id: address.division.id,
    district_id: address.district.id,
    upazila_id: address.upazila.id,
    address_line: address.address_line,
  };
}

export function AddressForm({ locale, addressId }: { locale: AppLocale; addressId?: string }) {
  const t = useTranslations("account.addresses.form");
  const common = useTranslations("account.common");
  const api = useAccountApi();
  const router = useRouter();
  const { getDivisions, getDistricts, getUpazilas, session } = useCommerce();
  const createMutation = useIdempotentMutation("address:create", session?.user?.id ?? null);
  const load = useCallback(
    (signal: AbortSignal) =>
      addressId ? api.address(addressId, locale, signal) : Promise.resolve(null),
    [addressId, api, locale],
  );
  const query = useAccountQuery(load, [load]);
  const [draft, setDraft] = useState<AddressInput | null>(null);
  const [divisions, setDivisions] = useState<GeoOption[]>([]);
  const [districts, setDistricts] = useState<GeoOption[]>([]);
  const [upazilas, setUpazilas] = useState<GeoOption[]>([]);
  const [geoLoading, setGeoLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const geoRequest = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    getDivisions(controller.signal)
      .then(setDivisions)
      .catch(() => setError(t("geoError")))
      .finally(() => setGeoLoading(false));
    return () => controller.abort();
  }, [getDivisions, t]);

  useEffect(() => {
    const address = query.data?.data;
    if (!address) return;
    const request = ++geoRequest.current;
    Promise.all([getDistricts(address.division.id), getUpazilas(address.district.id)])
      .then(([nextDistricts, nextUpazilas]) => {
        if (request !== geoRequest.current) return;
        setDistricts(nextDistricts);
        setUpazilas(nextUpazilas);
      })
      .catch(() => {
        if (request === geoRequest.current) setError(t("geoError"));
      });
  }, [getDistricts, getUpazilas, query.data, t]);

  if (addressId && query.loading && !query.data) return <AccountLoadingState />;
  if (query.error && !query.data)
    return <AccountErrorState error={query.error} retry={query.retry} />;
  const form = draft ?? toAddressInput(query.data?.data);

  const updateField = <Key extends keyof AddressInput>(key: Key, value: AddressInput[Key]) => {
    setError("");
    setStale(false);
    createMutation.reset();
    setDraft((current) => ({ ...(current ?? form), [key]: value }));
  };

  const changeDivision = async (divisionId: string) => {
    setDraft((current) => ({
      ...(current ?? form),
      division_id: divisionId,
      district_id: "",
      upazila_id: "",
    }));
    setDistricts([]);
    setUpazilas([]);
    createMutation.reset();
    const request = ++geoRequest.current;
    if (!divisionId) {
      setGeoLoading(false);
      return;
    }
    setGeoLoading(true);
    try {
      const nextDistricts = await getDistricts(divisionId);
      if (request === geoRequest.current) setDistricts(nextDistricts);
    } catch {
      if (request === geoRequest.current) setError(t("geoError"));
    } finally {
      if (request === geoRequest.current) setGeoLoading(false);
    }
  };

  const changeDistrict = async (districtId: string) => {
    setDraft((current) => ({
      ...(current ?? form),
      district_id: districtId,
      upazila_id: "",
    }));
    setUpazilas([]);
    createMutation.reset();
    const request = ++geoRequest.current;
    if (!districtId) {
      setGeoLoading(false);
      return;
    }
    setGeoLoading(true);
    try {
      const nextUpazilas = await getUpazilas(districtId);
      if (request === geoRequest.current) setUpazilas(nextUpazilas);
    } catch {
      if (request === geoRequest.current) setError(t("geoError"));
    } finally {
      if (request === geoRequest.current) setGeoLoading(false);
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      !form.label.trim() ||
      !form.recipient.trim() ||
      !isValidBangladeshPhone(form.phone) ||
      !form.division_id ||
      !form.district_id ||
      !form.upazila_id ||
      form.address_line.trim().length < 5
    ) {
      setError(t("validation"));
      return;
    }
    const input = {
      ...form,
      label: form.label.trim(),
      recipient: form.recipient.trim(),
      phone: normalizeBangladeshPhone(form.phone),
      address_line: form.address_line.trim(),
    };
    setSaving(true);
    setError("");
    setStale(false);
    try {
      if (addressId && query.data) {
        const editable = {
          label: input.label,
          recipient: input.recipient,
          phone: input.phone,
          division_id: input.division_id,
          district_id: input.district_id,
          upazila_id: input.upazila_id,
          address_line: input.address_line,
        };
        await api.updateAddress(addressId, editable, requireAccountEtag(query.data.etag), locale);
      } else {
        await createMutation.run(input, (key) => api.createAddress(input, key, locale));
      }
      router.replace(`/${locale}/account/addresses`);
    } catch (caught) {
      if (isStaleWrite(caught)) setStale(true);
      else setError(common(isAmbiguousMutationError(caught) ? "outcomeUnknown" : "saveError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <AccountPageHeader
        description={addressId ? t("editDescription") : t("newDescription")}
        title={addressId ? t("editTitle") : t("newTitle")}
      />
      <form
        className="mt-6 grid gap-4 rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:grid-cols-2 sm:p-7"
        onSubmit={(event) => void submit(event)}
      >
        <label>
          <span className="font-extrabold text-deep-indigo">{t("label")}</span>
          <input
            className="mt-1 min-h-12 w-full rounded-xl border border-brand-purple/20 px-4 focus:border-brand-purple focus:outline-none"
            maxLength={80}
            onChange={(event) => updateField("label", event.target.value)}
            required
            value={form.label}
          />
        </label>
        <label>
          <span className="font-extrabold text-deep-indigo">{t("recipient")}</span>
          <input
            autoComplete="name"
            className="mt-1 min-h-12 w-full rounded-xl border border-brand-purple/20 px-4 focus:border-brand-purple focus:outline-none"
            maxLength={160}
            onChange={(event) => updateField("recipient", event.target.value)}
            required
            value={form.recipient}
          />
        </label>
        <label className="sm:col-span-2">
          <span className="font-extrabold text-deep-indigo">{t("phone")}</span>
          <input
            autoComplete="tel"
            className="mt-1 min-h-12 w-full rounded-xl border border-brand-purple/20 px-4 focus:border-brand-purple focus:outline-none"
            inputMode="tel"
            maxLength={24}
            onChange={(event) => updateField("phone", event.target.value)}
            required
            value={form.phone}
          />
        </label>
        <label>
          <span className="font-extrabold text-deep-indigo">{t("division")}</span>
          <select
            className="mt-1 min-h-12 w-full rounded-xl border border-brand-purple/20 bg-white px-4 focus:border-brand-purple focus:outline-none"
            disabled={geoLoading && !divisions.length}
            onChange={(event) => void changeDivision(event.target.value)}
            required
            value={form.division_id}
          >
            <option value="">{t("selectDivision")}</option>
            {divisions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="font-extrabold text-deep-indigo">{t("district")}</span>
          <select
            className="mt-1 min-h-12 w-full rounded-xl border border-brand-purple/20 bg-white px-4 focus:border-brand-purple focus:outline-none"
            disabled={!form.division_id || geoLoading}
            onChange={(event) => void changeDistrict(event.target.value)}
            required
            value={form.district_id}
          >
            <option value="">{t("selectDistrict")}</option>
            {districts.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="font-extrabold text-deep-indigo">{t("upazila")}</span>
          <select
            className="mt-1 min-h-12 w-full rounded-xl border border-brand-purple/20 bg-white px-4 focus:border-brand-purple focus:outline-none"
            disabled={!form.district_id || geoLoading}
            onChange={(event) => updateField("upazila_id", event.target.value)}
            required
            value={form.upazila_id}
          >
            <option value="">{t("selectUpazila")}</option>
            {upazilas.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="sm:col-span-2">
          <span className="font-extrabold text-deep-indigo">{t("addressLine")}</span>
          <textarea
            className="mt-1 min-h-28 w-full rounded-xl border border-brand-purple/20 px-4 py-3 focus:border-brand-purple focus:outline-none"
            maxLength={500}
            minLength={5}
            onChange={(event) => updateField("address_line", event.target.value)}
            required
            value={form.address_line}
          />
        </label>
        {!addressId ? (
          <label className="flex min-h-11 items-center gap-3 sm:col-span-2">
            <input
              checked={Boolean(form.is_default)}
              className="size-5 accent-brand-purple"
              onChange={(event) => updateField("is_default", event.target.checked)}
              type="checkbox"
            />
            <span className="font-bold text-deep-indigo">{t("makeDefault")}</span>
          </label>
        ) : null}
        {stale ? (
          <p
            className="rounded-xl bg-sale-amber/15 p-3 font-bold text-deep-indigo sm:col-span-2"
            role="alert"
          >
            <Warning aria-hidden className="mr-2 inline" size={20} /> {common("stale")}
            <button
              className="ml-2 min-h-11 underline"
              onClick={() => {
                setDraft(null);
                query.retry();
              }}
              type="button"
            >
              {common("reload")}
            </button>
          </p>
        ) : null}
        {error ? (
          <p className="rounded-xl bg-error/10 p-3 font-bold text-error sm:col-span-2" role="alert">
            {error}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-3 sm:col-span-2">
          <button
            className="signature-gradient inline-flex min-h-12 items-center gap-2 rounded-full px-7 font-extrabold text-white disabled:opacity-55"
            disabled={saving || geoLoading}
            type="submit"
          >
            <FloppyDisk aria-hidden size={20} weight="duotone" />{" "}
            {saving ? common("saving") : common("save")}
          </button>
          <button
            className="min-h-12 rounded-full px-6 font-extrabold text-muted"
            onClick={() => router.back()}
            type="button"
          >
            {common("cancel")}
          </button>
        </div>
      </form>
    </div>
  );
}
