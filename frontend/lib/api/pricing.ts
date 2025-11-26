import { fetchJson, ApiProblemError } from '@/lib/api/fetch';
import { logger } from '@/lib/logger';
import type { PriceFloorConfig } from '@/lib/pricing/priceFloors';

export type PricingLineItem = {
  label: string;
  amount_cents: number;
};

export type PricingTierConfig = {
  min: number;
  max: number | null;
  pct: number;
};

export type PricingConfig = {
  student_fee_pct: number;
  instructor_tiers: PricingTierConfig[];
  price_floor_cents: PriceFloorConfig;
  tier_activity_window_days?: number;
  tier_stepdown_max?: number;
  tier_inactivity_reset_days?: number;
  student_credit_cycle?: Record<string, number>;
};

export type PricingPreviewResponse = {
  base_price_cents: number;
  student_fee_cents: number;
  instructor_commission_cents: number;
  credit_applied_cents: number;
  student_pay_cents: number;
  application_fee_cents: number;
  top_up_transfer_cents: number;
  instructor_tier_pct: number | null;
  line_items: PricingLineItem[];
};

export type PricingPreviewQuotePayload = {
  instructor_id: string;
  instructor_service_id: string;
  booking_date: string;
  start_time: string;
  selected_duration: number;
  location_type: string;
  meeting_location: string;
  applied_credit_cents: number;
};

export type PricingPreviewQuotePayloadBase = Omit<PricingPreviewQuotePayload, 'applied_credit_cents'>;

type PricingConfigResponse = {
  config: PricingConfig;
  updated_at: string | null;
};

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
