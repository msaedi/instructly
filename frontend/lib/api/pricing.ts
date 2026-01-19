import { fetchJson, ApiProblemError } from '@/lib/api/fetch';
import { logger } from '@/lib/logger';
import type {
  PricingPreviewResponse,
  PricingLineItem,
  PricingTierConfig,
  PricingConfig,
  PricingPreviewQuotePayload,
  PricingConfigResponse,
} from '@/features/shared/api/types';

export type { PricingPreviewResponse, PricingLineItem, PricingTierConfig, PricingConfig, PricingPreviewQuotePayload };

export type PricingPreviewQuotePayloadBase = Omit<PricingPreviewQuotePayload, 'applied_credit_cents'>;

export async function fetchPricingConfig(): Promise<PricingConfigResponse> {
  try {
    return await fetchJson<PricingConfigResponse>('/api/v1/config/pricing');
  } catch (error) {
    logger.error('Failed to load pricing config', error as Error);
    throw error;
  }
}

export async function fetchPricingPreview(
  bookingId: string,
  appliedCreditCents = 0,
  options: { signal?: AbortSignal | null } = {}
): Promise<PricingPreviewResponse> {
  const normalizedCredits = Math.max(0, Math.round(appliedCreditCents));
  const endpoint = `/api/v1/bookings/${bookingId}/pricing?applied_credit_cents=${normalizedCredits}`;
  try {
    return await fetchJson<PricingPreviewResponse>(endpoint, { signal: options.signal ?? null });
  } catch (error) {
    if ((error as { name?: string } | null)?.name === 'AbortError') {
      return undefined as unknown as PricingPreviewResponse;
    }
    if (error instanceof ApiProblemError) {
      throw error;
    }
    logger.error('Failed to fetch pricing preview', error as Error, { bookingId, appliedCreditCents });
    throw error;
  }
}

export async function fetchPricingPreviewQuote(
  payload: PricingPreviewQuotePayload,
  options: { signal?: AbortSignal | null } = {}
): Promise<PricingPreviewResponse> {
  const endpoint = '/api/v1/pricing/preview';
  try {
    return await fetchJson<PricingPreviewResponse>(endpoint, {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: {
        'Content-Type': 'application/json',
      },
      signal: options.signal ?? null,
    });
  } catch (error) {
    if ((error as { name?: string } | null)?.name === 'AbortError') {
      return undefined as unknown as PricingPreviewResponse;
    }
    if (error instanceof ApiProblemError) {
      throw error;
    }
    logger.error('Failed to fetch pricing quote preview', error as Error, {
      instructor_id: payload.instructor_id,
      instructor_service_id: payload.instructor_service_id,
    });
    throw error;
  }
}

export function formatCentsToDisplay(cents: number): string {
  const sign = cents < 0 ? '-' : '';
  const absoluteCents = Math.abs(Math.round(cents));
  const dollars = Math.floor(absoluteCents / 100);
  const remainder = absoluteCents % 100;
  return `${sign}$${dollars.toString()}.${remainder.toString().padStart(2, '0')}`;
}
