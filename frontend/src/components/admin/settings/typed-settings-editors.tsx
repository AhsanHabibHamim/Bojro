"use client";

import { Plus, Trash } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";

import { AdminField, adminInputClass } from "../ui/form-field";

type Value = Record<string, unknown>;

export function ShippingSettingsEditor({
  value,
  onChange,
}: {
  value: Value;
  onChange: (value: Value) => void;
}) {
  const t = useTranslations("admin.settingsFields");
  const zones = (value.zones as Record<string, Value> | undefined) ?? {};

  function setZone(name: string, zone: Value) {
    onChange({ ...value, version: 3, zones: { ...zones, [name]: zone } });
  }

  function setZones(next: Record<string, Value>) {
    onChange({ ...value, version: 3, zones: next });
  }

  return (
    <div className="grid gap-5 sm:col-span-2">
      <AdminField htmlFor="free-shipping-threshold" label={t("free_shipping_threshold_poisha")}>
        <input
          className={adminInputClass}
          id="free-shipping-threshold"
          min={0}
          onChange={(event) =>
            onChange({
              ...value,
              version: 3,
              free_shipping_threshold_poisha: event.target.value
                ? Number(event.target.value)
                : null,
            })
          }
          type="number"
          value={
            value.free_shipping_threshold_poisha == null
              ? ""
              : String(value.free_shipping_threshold_poisha)
          }
        />
      </AdminField>
      <button
        className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/15 px-4 font-bold text-brand-purple sm:justify-self-start"
        onClick={() => {
          let index = Object.keys(zones).length + 1;
          while (`zone_${index}` in zones) index += 1;
          setZones({
            ...zones,
            [`zone_${index}`]: {
              district_codes: [],
              minimum_days: 1,
              maximum_days: 3,
              additional_kg_poisha: 0,
              tiers: [{ max_weight_g: 1000, charge_poisha: 0 }],
            },
          });
        }}
        type="button"
      >
        <Plus aria-hidden size={18} /> {t("add_zone")}
      </button>
      {Object.entries(zones).map(([name, zone]) => {
        const tiers = (zone.tiers as Value[] | undefined) ?? [];
        return (
          <fieldset className="grid gap-4 rounded-2xl border border-brand-purple/12 p-4" key={name}>
            <legend className="px-2 text-lg font-extrabold">{name.replaceAll("_", " ")}</legend>
            <div className="flex flex-wrap items-end gap-3">
              <AdminField htmlFor={`zone-${name}-key`} label={t("zone_key")}>
                <input
                  className={adminInputClass}
                  defaultValue={name}
                  id={`zone-${name}-key`}
                  onBlur={(event) => {
                    const nextName = event.target.value.trim();
                    if (!nextName || nextName === name || nextName in zones) return;
                    const next = { ...zones };
                    delete next[name];
                    next[nextName] = zone;
                    setZones(next);
                  }}
                />
              </AdminField>
              <button
                className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-error/20 px-4 font-bold text-error"
                onClick={() => {
                  const next = { ...zones };
                  delete next[name];
                  setZones(next);
                }}
                type="button"
              >
                <Trash aria-hidden size={18} /> {t("remove_zone")}
              </button>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <AdminField htmlFor={`zone-${name}-districts`} label={t("district_codes")}>
                <input
                  className={adminInputClass}
                  id={`zone-${name}-districts`}
                  onChange={(event) =>
                    setZone(name, {
                      ...zone,
                      district_codes: event.target.value
                        .split(",")
                        .map((code) => code.trim())
                        .filter(Boolean),
                    })
                  }
                  value={Array.isArray(zone.district_codes) ? zone.district_codes.join(", ") : ""}
                />
              </AdminField>
              {(["minimum_days", "maximum_days", "additional_kg_poisha"] as const).map((field) => (
                <AdminField htmlFor={`zone-${name}-${field}`} key={field} label={t(field)} required>
                  <input
                    className={adminInputClass}
                    id={`zone-${name}-${field}`}
                    min={field === "additional_kg_poisha" ? 0 : 1}
                    onChange={(event) =>
                      setZone(name, { ...zone, [field]: Number(event.target.value) })
                    }
                    required
                    type="number"
                    value={Number(zone[field] ?? 0)}
                  />
                </AdminField>
              ))}
            </div>
            <div className="grid gap-3">
              <div className="flex items-center justify-between gap-3">
                <h4 className="font-extrabold">{t("tiers")}</h4>
                <button
                  className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/15 px-4 font-bold text-brand-purple"
                  onClick={() =>
                    setZone(name, {
                      ...zone,
                      tiers: [...tiers, { max_weight_g: 1000, charge_poisha: 0 }],
                    })
                  }
                  type="button"
                >
                  <Plus aria-hidden size={18} /> {t("add_tier")}
                </button>
              </div>
              {tiers.map((tier, index) => (
                <div
                  className="grid gap-3 rounded-xl bg-page-background p-3 sm:grid-cols-[1fr_1fr_auto]"
                  key={`${name}-tier-${index}`}
                >
                  <AdminField
                    htmlFor={`${name}-tier-weight-${index}`}
                    label={t("max_weight_g")}
                    required
                  >
                    <input
                      className={adminInputClass}
                      id={`${name}-tier-weight-${index}`}
                      min={1}
                      onChange={(event) =>
                        setZone(name, {
                          ...zone,
                          tiers: tiers.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, max_weight_g: Number(event.target.value) }
                              : item,
                          ),
                        })
                      }
                      required
                      type="number"
                      value={Number(tier.max_weight_g ?? 0)}
                    />
                  </AdminField>
                  <AdminField
                    htmlFor={`${name}-tier-charge-${index}`}
                    label={t("charge_poisha")}
                    required
                  >
                    <input
                      className={adminInputClass}
                      id={`${name}-tier-charge-${index}`}
                      min={0}
                      onChange={(event) =>
                        setZone(name, {
                          ...zone,
                          tiers: tiers.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, charge_poisha: Number(event.target.value) }
                              : item,
                          ),
                        })
                      }
                      required
                      type="number"
                      value={Number(tier.charge_poisha ?? 0)}
                    />
                  </AdminField>
                  <button
                    aria-label={t("remove_tier")}
                    className="grid size-11 self-end place-items-center rounded-xl text-error hover:bg-error/10"
                    onClick={() =>
                      setZone(name, {
                        ...zone,
                        tiers: tiers.filter((_, itemIndex) => itemIndex !== index),
                      })
                    }
                    type="button"
                  >
                    <Trash aria-hidden size={18} />
                  </button>
                </div>
              ))}
            </div>
          </fieldset>
        );
      })}
    </div>
  );
}

export function CodRiskSettingsEditor({
  value,
  onChange,
}: {
  value: Value;
  onChange: (value: Value) => void;
}) {
  const t = useTranslations("admin.settingsFields");
  const statuses = Array.isArray(value.return_statuses) ? value.return_statuses : [];
  return (
    <div className="grid gap-4 sm:col-span-2 sm:grid-cols-2">
      {(["enabled", "advance_payment_required"] as const).map((field) => (
        <label
          className="flex min-h-12 items-center gap-3 rounded-xl border border-brand-purple/12 px-4 font-bold"
          key={field}
        >
          <input
            checked={Boolean(value[field])}
            onChange={(event) => onChange({ ...value, version: 3, [field]: event.target.checked })}
            type="checkbox"
          />
          {t(field)}
        </label>
      ))}
      {(["minimum_completed_orders", "maximum_return_rate"] as const).map((field) => (
        <AdminField htmlFor={`cod-${field}`} key={field} label={t(field)} required>
          <input
            className={adminInputClass}
            id={`cod-${field}`}
            max={field === "maximum_return_rate" ? 1 : undefined}
            min={0}
            onChange={(event) =>
              onChange({ ...value, version: 3, [field]: Number(event.target.value) })
            }
            required
            step={field === "maximum_return_rate" ? 0.01 : 1}
            type="number"
            value={Number(value[field] ?? 0)}
          />
        </AdminField>
      ))}
      <fieldset className="rounded-xl border border-brand-purple/12 p-4 sm:col-span-2">
        <legend className="px-2 font-extrabold">{t("return_statuses")}</legend>
        <div className="flex flex-wrap gap-4">
          {(["returned", "refunded"] as const).map((status) => (
            <label className="flex min-h-11 items-center gap-2 font-bold" key={status}>
              <input
                checked={statuses.includes(status)}
                onChange={(event) =>
                  onChange({
                    ...value,
                    version: 3,
                    return_statuses: event.target.checked
                      ? [...statuses, status]
                      : statuses.filter((item) => item !== status),
                  })
                }
                type="checkbox"
              />
              {t(status)}
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  );
}
