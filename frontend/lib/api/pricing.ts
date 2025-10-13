import { fetchJson, ApiProblemError } from '@/lib/api/fetch';
import { logger } from '@/lib/logger';
import type { PriceFloorConfig } from '@/lib/pricing/priceFloors';

export type PricingLineItem = {
  label: string;
  amount_cents: number;
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

type PricingConfigResponse = {
  config: {
    price_floor_cents: PriceFloorConfig;
  };
  updated_at: string | null;
};

export async function fetchPricingConfig(): Promise<PricingConfigResponse> {
  try {
    return await fetchJson<PricingConfigResponse>('/api/config/pricing');
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
  const endpoint = `/api/bookings/${bookingId}/pricing?applied_credit_cents=${normalizedCredits}`;
  try {
    return await fetchJson<PricingPreviewResponse>(endpoint, { signal: options.signal ?? null });
  } catch (error) {
    if (error instanceof ApiProblemError) {
      throw error;
    }
    logger.error('Failed to fetch pricing preview', error as Error, { bookingId, appliedCreditCents });
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
