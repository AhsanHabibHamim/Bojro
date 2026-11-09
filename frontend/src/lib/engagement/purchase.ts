import type { OrderReceipt } from "@/lib/commerce/types";
import type { AnalyticsEvent } from "@/lib/engagement/types";

const confirmedPaymentStatuses = new Set(["paid", "partially_refunded", "refunded"]);

export function confirmedOnlinePurchase(order: OrderReceipt | null): AnalyticsEvent | null {
  const eventId = order?.analytics.purchase_event_id;
  if (
    !order ||
    order.payment_method === "cod" ||
    !confirmedPaymentStatuses.has(order.payment_status) ||
    !eventId ||
    !/^[0-9a-f-]{36}$/i.test(eventId)
  ) {
    return null;
  }
  return {
    event_id: eventId,
    event_name: "purchase",
    commerce: {
      currency: "BDT",
      value_poisha: order.grand_total_poisha,
      item_ids: [
        ...new Set(
          order.items
            .map((item) => item.variant_id)
            .filter((variantId): variantId is string => Boolean(variantId)),
        ),
      ],
      quantity: order.items.reduce((total, item) => total + item.quantity, 0),
    },
  };
}
