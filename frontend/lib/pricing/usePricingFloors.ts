import { useEffect, useState } from 'react';
import { fetchPricingConfig, type PricingConfig } from '@/lib/api/pricing';
import type { PriceFloorConfig } from '@/lib/pricing/priceFloors';
import { logger } from '@/lib/logger';

export function usePricingConfig() {
  const [config, setConfig] = useState<PricingConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setIsLoading(true);
        const response = await fetchPricingConfig();
        if (!cancelled) {
          setConfig(response.config);
          setError(null);
        }
      } catch (err) {
        logger.error('Failed to fetch pricing config', err as Error);
        if (!cancelled) {
          setError('Unable to load pricing configuration.');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return { config, isLoading, error };
}

export function usePricingFloors() {
  const { config, isLoading, error } = usePricingConfig();
  const floors: PriceFloorConfig | null = config?.price_floor_cents ?? null;
  return { floors, isLoading, error };
}
