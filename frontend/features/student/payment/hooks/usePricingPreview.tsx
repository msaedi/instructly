/* eslint-disable react-refresh/only-export-components */
import { ApiProblemError } from '@/lib/api/fetch';
import { logger } from '@/lib/logger';
import {
  fetchPricingPreview,
  fetchPricingPreviewQuote,
  type PricingPreviewQuotePayload,
  type PricingPreviewQuotePayloadBase,
  type PricingPreviewResponse,
} from '@/lib/api/pricing';
import { createContext, useCallback, useContext, useMemo, useRef, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import {
  computeCreditStorageKey,
  readStoredCreditDecision,
  writeStoredCreditDecision,
} from '../utils/creditStorage';

export type PreviewCause = 'date-time-only' | 'duration-change' | 'credit-change';

type PricingPreviewController = {
  preview: PricingPreviewResponse | null;
  loading: boolean;
  error: string | null;
  lastAppliedCreditCents: number;
  requestPricingPreview: (options?: { key?: string; cause?: PreviewCause }) => Promise<PricingPreviewResponse | null>;
  applyCredit: (
    creditCents: number,
    options?: { skipIfUnchanged?: boolean; suppressLoading?: boolean },
  ) => Promise<PricingPreviewResponse | null>;
  reset: () => void;
  bookingId: string | null;
};

type PricingPreviewControllerOptions = {
  bookingId: string | null | undefined;
  quotePayload?: PricingPreviewQuotePayload | PricingPreviewQuotePayloadBase | null;
  quotePayloadResolver?: () => PricingPreviewQuotePayloadBase | null;
};

export const PricingPreviewContext = createContext<PricingPreviewController | null>(null);

const stableSerialize = (value: unknown): string => {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableSerialize).join(',')}]`;
  }
  const entries = Object.keys(value as Record<string, unknown>)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableSerialize((value as Record<string, unknown>)[key])}`);
  return `{${entries.join(',')}}`;
};

const DEV_MODE = process.env.NODE_ENV !== 'production';

const logDev = (...args: unknown[]) => {
  if (!DEV_MODE) {
    return;
  }
  logger.debug('pricing-preview:dev-log', { args });
};

const hashQuotePayload = (payload?: PricingPreviewQuotePayloadBase | null): string | null => {
  if (!payload) {
    return null;
  }
  return stableSerialize(payload);
};

const QUOTE_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const QUOTE_TIME_PATTERN = /^\d{2}:\d{2}$/;
const ALLOWED_LOCATION_TYPES = new Set([
  'student_location',
  'instructor_location',
  'online',
  'neutral_location',
]);

const validateQuotePayload = (
  payload: PricingPreviewQuotePayloadBase,
): { valid: boolean; missingKeys: string[] } => {
  const missingKeys: string[] = [];

  if (!payload.instructor_id?.trim()) {
    missingKeys.push('instructor_id');
  }
  if (!payload.instructor_service_id?.trim()) {
    missingKeys.push('instructor_service_id');
  }
  if (!payload.booking_date || !QUOTE_DATE_PATTERN.test(payload.booking_date)) {
    missingKeys.push('booking_date');
  }
  if (!payload.start_time || !QUOTE_TIME_PATTERN.test(payload.start_time)) {
    missingKeys.push('start_time');
  }
  if (!Number.isFinite(payload.selected_duration) || payload.selected_duration <= 0) {
    missingKeys.push('selected_duration');
  }
  const normalizedLocationType = payload.location_type?.trim().toLowerCase();
  if (!normalizedLocationType || !ALLOWED_LOCATION_TYPES.has(normalizedLocationType)) {
    missingKeys.push('location_type');
  }
  if (!payload.meeting_location?.trim()) {
    missingKeys.push('meeting_location');
  }

  return { valid: missingKeys.length === 0, missingKeys };
};

const extractBasePayload = (
  payload: PricingPreviewQuotePayload | PricingPreviewQuotePayloadBase | null,
): PricingPreviewQuotePayloadBase | null => {
  if (!payload) {
    return null;
  }

  const {
    instructor_id,
    instructor_service_id,
    booking_date,
    start_time,
    selected_duration,
    location_type,
    meeting_location,
  } = payload;

  return {
    instructor_id,
    instructor_service_id,
    booking_date,
    start_time,
    selected_duration,
    location_type,
    meeting_location,
  };
};

export function usePricingPreviewController({
  bookingId,
  quotePayload,
  quotePayloadResolver,
}: PricingPreviewControllerOptions): PricingPreviewController {
  const [preview, setPreview] = useState<PricingPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastAppliedRef = useRef(0);
  const appliedCreditCentsRef = useRef(0);
  const previewRef = useRef<PricingPreviewResponse | null>(null);
  const initAbortRef = useRef<AbortController | null>(null);
  const commitAbortRef = useRef<AbortController | null>(null);
  const activeRequestCountRef = useRef(0);
  const lastCommitValueRef = useRef<number | null>(null);
  const lastInitKeyRef = useRef<string | null>(null);
  const quoteResolverRef = useRef<PricingPreviewControllerOptions['quotePayloadResolver']>(quotePayloadResolver);
  const quotePayloadRef = useRef<PricingPreviewQuotePayload | PricingPreviewQuotePayloadBase | null>(
    quotePayload ?? null,
  );

  useEffect(() => {
    quoteResolverRef.current = quotePayloadResolver;
  }, [quotePayloadResolver]);

  useEffect(() => {
    quotePayloadRef.current = quotePayload ?? null;
  }, [quotePayload]);

  useEffect(() => {
    const creditCents = Math.max(0, preview?.credit_applied_cents ?? 0);
    appliedCreditCentsRef.current = creditCents;
    lastAppliedRef.current = creditCents;
  }, [preview?.credit_applied_cents]);

  const reset = useCallback(() => {
    initAbortRef.current?.abort();
    commitAbortRef.current?.abort();
    initAbortRef.current = null;
    commitAbortRef.current = null;
    activeRequestCountRef.current = 0;
    lastCommitValueRef.current = null;
    lastInitKeyRef.current = null;
    lastAppliedRef.current = 0;
    previewRef.current = null;
    setPreview(null);
    setError(null);
    setLoading(false);
  }, []);

  const beginRequest = useCallback(() => {
    activeRequestCountRef.current += 1;
    setLoading(true);
  }, []);

  const endRequest = useCallback(() => {
    activeRequestCountRef.current = Math.max(0, activeRequestCountRef.current - 1);
    if (activeRequestCountRef.current === 0) {
      setLoading(false);
    }
  }, []);

  const resolveQuotePayloadBase = useCallback(() => {
    const payload = quotePayloadRef.current ?? quoteResolverRef.current?.() ?? null;
    return extractBasePayload(payload);
  }, []);

  const getCreditStorageKey = useCallback(() => {
    const normalizedBookingId = bookingId?.trim() || null;
    const basePayload = resolveQuotePayloadBase();
    return computeCreditStorageKey({
      bookingId: normalizedBookingId,
      quotePayloadBase: basePayload,
    });
  }, [bookingId, resolveQuotePayloadBase]);

  const persistCreditDecision = useCallback(
    (creditCents: number) => {
      const key = getCreditStorageKey();
      if (!key) {
        return;
      }
      const sanitizedCents = Math.max(0, Math.round(creditCents));
      const existing = readStoredCreditDecision(key);
      if (sanitizedCents === 0) {
        if (!existing) {
          return;
        }
        if (existing.lastCreditCents > 0 && !existing.explicitlyRemoved) {
          return;
        }
      }
      const nextDecision = {
        lastCreditCents: sanitizedCents,
        explicitlyRemoved: sanitizedCents > 0 ? false : existing?.explicitlyRemoved ?? false,
      };
      if (
        !existing ||
        existing.lastCreditCents !== nextDecision.lastCreditCents ||
        existing.explicitlyRemoved !== nextDecision.explicitlyRemoved
      ) {
        writeStoredCreditDecision(key, nextDecision);
      }
    },
    [getCreditStorageKey],
  );

  const computeInitKey = useCallback(() => {
    const normalizedBookingId = bookingId?.trim() ? bookingId : null;
    if (normalizedBookingId) {
      return normalizedBookingId;
    }
    const basePayload = resolveQuotePayloadBase();
    return hashQuotePayload(basePayload);
  }, [bookingId, resolveQuotePayloadBase]);

  const applyPreviewResult = useCallback((result: PricingPreviewResponse | null) => {
    if (!result) {
      return previewRef.current;
    }
    const sanitizedCreditCents = Math.max(0, result.credit_applied_cents ?? 0);
    previewRef.current = result;
    lastAppliedRef.current = sanitizedCreditCents;
    appliedCreditCentsRef.current = sanitizedCreditCents;
    setPreview(result);
    setError(null);
    persistCreditDecision(sanitizedCreditCents);
    return result;
  }, [persistCreditDecision]);

  const performFetch = useCallback(
    async (creditCents: number, signal: AbortSignal): Promise<PricingPreviewResponse | null> => {
      const normalizedBookingId = bookingId?.trim() ? bookingId : null;
      const normalizedCreditCents = Math.max(0, Math.round(creditCents));

      if (normalizedBookingId) {
        logDev('GET pricing preview', {
          bookingId: normalizedBookingId,
          applied_credit_cents: normalizedCreditCents,
        });
        return fetchPricingPreview(normalizedBookingId, normalizedCreditCents, { signal });
      }

      const quotePayloadBase = resolveQuotePayloadBase();
      if (!quotePayloadBase) {
        logDev('Skipping pricing preview fetch: missing quote payload', {
          credit: normalizedCreditCents,
        });
        return previewRef.current;
      }

      const { missingKeys } = validateQuotePayload(quotePayloadBase);
      if (missingKeys.length > 0) {
        logDev('Skipping pricing preview fetch: missing fields', {
          missingKeys,
          credit: normalizedCreditCents,
        });
        return previewRef.current;
      }

      const payload: PricingPreviewQuotePayload = {
        ...quotePayloadBase,
        applied_credit_cents: normalizedCreditCents,
      };

      logDev('POST pricing preview', {
        payload_hash: hashQuotePayload(quotePayloadBase),
        applied_credit_cents: normalizedCreditCents,
      });

      return fetchPricingPreviewQuote(payload, { signal });
    },
    [bookingId, resolveQuotePayloadBase],
  );

  const requestPricingPreview = useCallback(async (options?: { key?: string; cause?: PreviewCause }) => {
    const cause = options?.cause ?? null;
    const requestKey = options?.key ?? computeInitKey();

    if (!cause && requestKey && lastInitKeyRef.current === requestKey && previewRef.current) {
      return previewRef.current;
    }

    lastInitKeyRef.current = requestKey ?? null;

    initAbortRef.current?.abort();
    const controller = new AbortController();
    initAbortRef.current = controller;
    const suppressLoading = cause === 'date-time-only';
    if (!suppressLoading) {
      beginRequest();
    }

    const shouldCarryCredit = cause === 'date-time-only' || cause === 'duration-change';
    const appliedCreditForRequest = Math.max(
      0,
      Math.round(shouldCarryCredit ? appliedCreditCentsRef.current : 0),
    );

    try {
      const result = await performFetch(appliedCreditForRequest, controller.signal);
      if (controller.signal.aborted) {
        return previewRef.current;
      }
      return applyPreviewResult(result);
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') {
        return previewRef.current;
      }
      logger.error('pricing-preview:init-error', err as Error, {
        bookingId,
      });
      setError('Unable to load pricing preview. Please try again.');
      return previewRef.current;
    } finally {
      if (!suppressLoading) {
        endRequest();
      }
      if (initAbortRef.current === controller) {
        initAbortRef.current = null;
      }
    }
  }, [
    applyPreviewResult,
    appliedCreditCentsRef,
    beginRequest,
    bookingId,
    computeInitKey,
    endRequest,
    performFetch,
  ]);

  const applyCredit = useCallback<PricingPreviewController['applyCredit']>(
    async (creditCents, options) => {
      const normalizedCreditCents = Math.max(0, Math.round(creditCents));

      if (
        (options?.skipIfUnchanged && previewRef.current?.credit_applied_cents === normalizedCreditCents) ||
        (commitAbortRef.current && lastCommitValueRef.current === normalizedCreditCents)
      ) {
        return previewRef.current;
      }

      if (previewRef.current?.credit_applied_cents === normalizedCreditCents && !commitAbortRef.current) {
        return previewRef.current;
      }

      lastCommitValueRef.current = normalizedCreditCents;
      commitAbortRef.current?.abort();
      const controller = new AbortController();
      commitAbortRef.current = controller;
      const shouldUseLoading = !options?.suppressLoading;
      if (shouldUseLoading) {
        beginRequest();
      }

      try {
        const result = await performFetch(normalizedCreditCents, controller.signal);
        if (controller.signal.aborted) {
          return previewRef.current;
        }
        return applyPreviewResult(result);
      } catch (err) {
        if ((err as Error)?.name === 'AbortError') {
          return previewRef.current;
        }

        if (err instanceof ApiProblemError) {
          const detail = err.problem?.detail ?? 'Unable to load pricing preview. Please try again.';
          const status = err.response?.status;
          if (status !== undefined) {
            logger.warn('pricing-preview:error', {
              bookingId,
              requestedCreditCents: normalizedCreditCents,
              status,
              detail,
            });
          } else {
            logger.error('pricing-preview:unexpected-problem', err, {
              bookingId,
              requestedCreditCents: normalizedCreditCents,
            });
          }
          setError(detail);
        } else {
          logger.error('pricing-preview:commit-error', err as Error, {
            bookingId,
            requestedCreditCents: normalizedCreditCents,
          });
          setError('Unable to load pricing preview. Please try again.');
        }

        lastCommitValueRef.current = null;
        throw err;
      } finally {
        if (shouldUseLoading) {
          endRequest();
        }
        if (commitAbortRef.current === controller) {
          commitAbortRef.current = null;
        }
      }
    },
    [applyPreviewResult, beginRequest, bookingId, endRequest, performFetch],
  );

  useEffect(() => {
    const key = computeInitKey();
    if (!key) {
      return;
    }
    void requestPricingPreview({ key });
  }, [computeInitKey, requestPricingPreview]);

  return useMemo(() => ({
    preview,
    loading,
    error,
    lastAppliedCreditCents: lastAppliedRef.current,
    requestPricingPreview,
    applyCredit,
    reset,
    bookingId: bookingId ?? null,
  }), [applyCredit, bookingId, error, loading, preview, requestPricingPreview, reset]);
}

export type PricingPreviewProviderProps = PricingPreviewControllerOptions & {
  children: ReactNode;
};

export function PricingPreviewProvider({ bookingId, quotePayload = null, quotePayloadResolver, children }: PricingPreviewProviderProps) {
  const controller = usePricingPreviewController({
    bookingId,
    quotePayload,
    ...(quotePayloadResolver ? { quotePayloadResolver } : {}),
  });
  return <PricingPreviewContext.Provider value={controller}>{children}</PricingPreviewContext.Provider>;
}

export function usePricingPreview(optional = false): PricingPreviewController | null {
  const context = useContext(PricingPreviewContext);
  if (!context) {
    if (optional) {
      return null;
    }
    throw new Error('usePricingPreview must be used within a PricingPreviewProvider');
  }
  return context;
}
