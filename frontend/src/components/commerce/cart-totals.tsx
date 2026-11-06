import type { AppLocale } from "@/i18n/routing";
import type { CommerceTotals } from "@/lib/commerce/types";
import { formatPrice } from "@/lib/format-price";

export type CartTotalsLabels = {
  subtotal: string;
  discount: string;
  shipping: string;
  shippingPending: string;
  total: string;
};

export function CartTotals({
  totals,
  locale,
  labels,
  hasShipping,
}: {
  totals: CommerceTotals;
  locale: AppLocale;
  labels: CartTotalsLabels;
  hasShipping: boolean;
}) {
  return (
    <dl className="space-y-2.5 text-sm">
      <div className="flex items-center justify-between gap-4">
        <dt className="text-muted">{labels.subtotal}</dt>
        <dd className="font-bold text-deep-indigo">
          {formatPrice(totals.subtotal_poisha, locale)}
        </dd>
      </div>
      {totals.discount_poisha > 0 ? (
        <div className="flex items-center justify-between gap-4 text-success">
          <dt>{labels.discount}</dt>
          <dd className="font-bold">−{formatPrice(totals.discount_poisha, locale)}</dd>
        </div>
      ) : null}
      <div className="flex items-center justify-between gap-4">
        <dt className="text-muted">{labels.shipping}</dt>
        <dd className="text-right font-bold text-deep-indigo">
          {hasShipping ? formatPrice(totals.shipping_poisha, locale) : labels.shippingPending}
        </dd>
      </div>
      <div className="flex items-end justify-between gap-4 border-t border-brand-purple/10 pt-3">
        <dt className="font-extrabold text-deep-indigo">{labels.total}</dt>
        <dd className="text-xl font-extrabold text-brand-purple">
          {formatPrice(totals.grand_total_poisha, locale)}
        </dd>
      </div>
    </dl>
  );
}
