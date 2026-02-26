export const PAYMENT_STATUS = {
  SCHEDULED: 'scheduled',
  AUTHORIZED: 'authorized',
  PAYMENT_METHOD_REQUIRED: 'payment_method_required',
  MANUAL_REVIEW: 'manual_review',
  LOCKED: 'locked',
  SETTLED: 'settled',
} as const;

export type PaymentStatus = (typeof PAYMENT_STATUS)[keyof typeof PAYMENT_STATUS];

export const CHECKOUT_SUCCESS_STATUSES: readonly PaymentStatus[] = [
  PAYMENT_STATUS.SCHEDULED,
  PAYMENT_STATUS.AUTHORIZED,
];

export const isCheckoutSuccess = (status: string | null | undefined): status is PaymentStatus =>
  !!status && CHECKOUT_SUCCESS_STATUSES.includes(status as PaymentStatus);

export const REFUNDABLE_STATUSES: readonly PaymentStatus[] = [PAYMENT_STATUS.SETTLED];

export const isRefundable = (status: string | null | undefined): status is PaymentStatus =>
  !!status && REFUNDABLE_STATUSES.includes(status as PaymentStatus);

export const ACTIVE_HOLD_STATUSES: readonly PaymentStatus[] = [
  PAYMENT_STATUS.AUTHORIZED,
  PAYMENT_STATUS.SCHEDULED,
];

export const hasActiveHold = (status: string | null | undefined): status is PaymentStatus =>
  !!status && ACTIVE_HOLD_STATUSES.includes(status as PaymentStatus);

export const BOOKING_ACTIVE_STATUSES: readonly PaymentStatus[] = [
  PAYMENT_STATUS.SCHEDULED,
  PAYMENT_STATUS.AUTHORIZED,
  PAYMENT_STATUS.LOCKED,
];

export const PAYMENT_NEEDS_ACTION_STATUSES: readonly PaymentStatus[] = [
  PAYMENT_STATUS.PAYMENT_METHOD_REQUIRED,
];

export const getPaymentStatusFromResponse = (response: unknown): string | undefined => {
  if (!response || typeof response !== 'object') {
    return undefined;
  }

  const record = response as Record<string, unknown>;
  if (typeof record['payment_status'] === 'string') {
    return record['payment_status'];
  }
  if (typeof record['status'] === 'string') {
    return record['status'];
  }
  return undefined;
};
