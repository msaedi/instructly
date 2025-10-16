import type { PricingPreviewQuotePayloadBase } from '@/lib/api/pricing';

const CREDIT_STORAGE_PREFIX = 'insta:credits:last:';

type Serializable = Record<string, unknown> | unknown[] | string | number | boolean | null;

const stableSerialize = (value: Serializable): string => {
  if (value === null) {
    return 'null';
  }

  if (Array.isArray(value)) {
    return `[${value.map((item) => stableSerialize(item as Serializable)).join(',')}]`;
  }

  if (typeof value === 'object') {
    const entries = Object.keys(value as Record<string, Serializable>)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableSerialize((value as Record<string, Serializable>)[key] as Serializable)}`);
    return `{${entries.join(',')}}`;
  }

  return JSON.stringify(value);
};

export type StoredCreditDecision = {
  lastCreditCents: number;
  explicitlyRemoved: boolean;
};

export const computeCreditStorageKey = (options: {
  bookingId?: string | null;
  quotePayloadBase?: PricingPreviewQuotePayloadBase | null;
}): string | null => {
  const normalizedBookingId = options.bookingId?.trim();
  if (normalizedBookingId) {
    return `${CREDIT_STORAGE_PREFIX}${normalizedBookingId}`;
  }

  if (options.quotePayloadBase) {
    return `${CREDIT_STORAGE_PREFIX}${stableSerialize(options.quotePayloadBase as Serializable)}`;
  }

  return null;
};

export const readStoredCreditDecision = (key: string): StoredCreditDecision | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.sessionStorage?.getItem(key);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<StoredCreditDecision>;
    const lastCreditCents = typeof parsed.lastCreditCents === 'number' && Number.isFinite(parsed.lastCreditCents)
      ? Math.max(0, Math.round(parsed.lastCreditCents))
      : 0;
    const explicitlyRemoved = Boolean(parsed.explicitlyRemoved);
    return { lastCreditCents, explicitlyRemoved };
  } catch {
    return null;
  }
};

export const writeStoredCreditDecision = (key: string, value: StoredCreditDecision): void => {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.sessionStorage?.setItem(
      key,
      JSON.stringify({
        lastCreditCents: Math.max(0, Math.round(value.lastCreditCents)),
        explicitlyRemoved: Boolean(value.explicitlyRemoved),
      }),
    );
  } catch {
    // Ignore storage failures (quota, disabled storage, etc.)
  }
};

export const removeStoredCreditDecision = (key: string): void => {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.sessionStorage?.removeItem(key);
  } catch {
    // Ignore errors
  }
};
