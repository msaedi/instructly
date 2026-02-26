/**
 * @jest-environment jsdom
 */
import {
  PAYMENT_STATUS,
  CHECKOUT_SUCCESS_STATUSES,
  REFUNDABLE_STATUSES,
  ACTIVE_HOLD_STATUSES,
  BOOKING_ACTIVE_STATUSES,
  PAYMENT_NEEDS_ACTION_STATUSES,
  isCheckoutSuccess,
  isRefundable,
  hasActiveHold,
  getPaymentStatusFromResponse,
} from '../paymentStatus';

describe('PAYMENT_STATUS constants', () => {
  it('has all expected status values', () => {
    expect(PAYMENT_STATUS.SCHEDULED).toBe('scheduled');
    expect(PAYMENT_STATUS.AUTHORIZED).toBe('authorized');
    expect(PAYMENT_STATUS.PAYMENT_METHOD_REQUIRED).toBe('payment_method_required');
    expect(PAYMENT_STATUS.MANUAL_REVIEW).toBe('manual_review');
    expect(PAYMENT_STATUS.LOCKED).toBe('locked');
    expect(PAYMENT_STATUS.SETTLED).toBe('settled');
  });
});

describe('status arrays', () => {
  it('CHECKOUT_SUCCESS_STATUSES contains scheduled and authorized', () => {
    expect(CHECKOUT_SUCCESS_STATUSES).toContain(PAYMENT_STATUS.SCHEDULED);
    expect(CHECKOUT_SUCCESS_STATUSES).toContain(PAYMENT_STATUS.AUTHORIZED);
    expect(CHECKOUT_SUCCESS_STATUSES).toHaveLength(2);
  });

  it('REFUNDABLE_STATUSES contains only settled', () => {
    expect(REFUNDABLE_STATUSES).toContain(PAYMENT_STATUS.SETTLED);
    expect(REFUNDABLE_STATUSES).toHaveLength(1);
  });

  it('ACTIVE_HOLD_STATUSES contains authorized and scheduled', () => {
    expect(ACTIVE_HOLD_STATUSES).toContain(PAYMENT_STATUS.AUTHORIZED);
    expect(ACTIVE_HOLD_STATUSES).toContain(PAYMENT_STATUS.SCHEDULED);
    expect(ACTIVE_HOLD_STATUSES).toHaveLength(2);
  });

  it('BOOKING_ACTIVE_STATUSES contains expected statuses', () => {
    expect(BOOKING_ACTIVE_STATUSES).toContain(PAYMENT_STATUS.SCHEDULED);
    expect(BOOKING_ACTIVE_STATUSES).toContain(PAYMENT_STATUS.AUTHORIZED);
    expect(BOOKING_ACTIVE_STATUSES).toContain(PAYMENT_STATUS.LOCKED);
    expect(BOOKING_ACTIVE_STATUSES).toHaveLength(3);
  });

  it('PAYMENT_NEEDS_ACTION_STATUSES contains payment_method_required', () => {
    expect(PAYMENT_NEEDS_ACTION_STATUSES).toContain(PAYMENT_STATUS.PAYMENT_METHOD_REQUIRED);
    expect(PAYMENT_NEEDS_ACTION_STATUSES).toHaveLength(1);
  });
});

describe('isCheckoutSuccess', () => {
  it('returns true for scheduled status', () => {
    expect(isCheckoutSuccess('scheduled')).toBe(true);
  });

  it('returns true for authorized status', () => {
    expect(isCheckoutSuccess('authorized')).toBe(true);
  });

  it('returns false for other statuses', () => {
    expect(isCheckoutSuccess('settled')).toBe(false);
    expect(isCheckoutSuccess('locked')).toBe(false);
    expect(isCheckoutSuccess('payment_method_required')).toBe(false);
  });

  it('returns false for null or undefined', () => {
    expect(isCheckoutSuccess(null)).toBe(false);
    expect(isCheckoutSuccess(undefined)).toBe(false);
  });

  it('returns false for empty string', () => {
    expect(isCheckoutSuccess('')).toBe(false);
  });
});

describe('isRefundable', () => {
  it('returns true for settled status', () => {
    expect(isRefundable('settled')).toBe(true);
  });

  it('returns false for other statuses', () => {
    expect(isRefundable('scheduled')).toBe(false);
    expect(isRefundable('authorized')).toBe(false);
    expect(isRefundable('locked')).toBe(false);
  });

  it('returns false for null or undefined', () => {
    expect(isRefundable(null)).toBe(false);
    expect(isRefundable(undefined)).toBe(false);
  });
});

describe('hasActiveHold', () => {
  it('returns true for authorized status', () => {
    expect(hasActiveHold('authorized')).toBe(true);
  });

  it('returns true for scheduled status', () => {
    expect(hasActiveHold('scheduled')).toBe(true);
  });

  it('returns false for other statuses', () => {
    expect(hasActiveHold('settled')).toBe(false);
    expect(hasActiveHold('locked')).toBe(false);
  });

  it('returns false for null or undefined', () => {
    expect(hasActiveHold(null)).toBe(false);
    expect(hasActiveHold(undefined)).toBe(false);
  });
});

describe('getPaymentStatusFromResponse', () => {
  it('extracts payment_status from response object', () => {
    const response = { payment_status: 'authorized' };
    expect(getPaymentStatusFromResponse(response)).toBe('authorized');
  });

  it('extracts status from response object if no payment_status', () => {
    const response = { status: 'settled' };
    expect(getPaymentStatusFromResponse(response)).toBe('settled');
  });

  it('prefers payment_status over status', () => {
    const response = { payment_status: 'authorized', status: 'settled' };
    expect(getPaymentStatusFromResponse(response)).toBe('authorized');
  });

  it('returns undefined for null response', () => {
    expect(getPaymentStatusFromResponse(null)).toBeUndefined();
  });

  it('returns undefined for undefined response', () => {
    expect(getPaymentStatusFromResponse(undefined)).toBeUndefined();
  });

  it('returns undefined for non-object response', () => {
    expect(getPaymentStatusFromResponse('string')).toBeUndefined();
    expect(getPaymentStatusFromResponse(123)).toBeUndefined();
    expect(getPaymentStatusFromResponse(true)).toBeUndefined();
  });

  it('returns undefined when no payment_status or status present', () => {
    expect(getPaymentStatusFromResponse({})).toBeUndefined();
    expect(getPaymentStatusFromResponse({ other: 'value' })).toBeUndefined();
  });

  it('returns undefined for non-string payment_status', () => {
    expect(getPaymentStatusFromResponse({ payment_status: 123 })).toBeUndefined();
    expect(getPaymentStatusFromResponse({ payment_status: null })).toBeUndefined();
    expect(getPaymentStatusFromResponse({ payment_status: {} })).toBeUndefined();
  });

  it('returns undefined for non-string status', () => {
    expect(getPaymentStatusFromResponse({ status: 123 })).toBeUndefined();
    expect(getPaymentStatusFromResponse({ status: null })).toBeUndefined();
  });
});
