import type { AdminOrderAction, AdminOrderTransitionInput } from "./types";

export function availableOrderAction(
  actions: AdminOrderAction[],
  status: AdminOrderTransitionInput["to_status"],
): AdminOrderAction | null {
  return actions.find((action) => action.to_status === status) ?? null;
}

export function validateOrderTransition(
  action: AdminOrderAction,
  input: AdminOrderTransitionInput,
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (input.to_status !== action.to_status) errors.status = "ORDER_ACTION_NOT_AVAILABLE";
  if (action.requires_reason && !input.reason?.trim()) errors.reason = "REQUIRED";
  if (action.requires_manual_override && !input.manual_shipping_override_reason?.trim()) {
    errors.manual_shipment_override_reason = "SHIPMENT_OR_OVERRIDE_REQUIRED";
  }
  if (
    action.requires_refund_confirmation &&
    (!input.refund_confirmed || !input.refund_reference?.trim())
  ) {
    errors.refund_reference = "REFUND_CONFIRMATION_REQUIRED";
  }
  return errors;
}
