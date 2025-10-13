import { fetchJson } from '@/lib/api/fetch';
import { logger } from '@/lib/logger';
import type { PriceFloorConfig } from '@/lib/pricing/priceFloors';

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
