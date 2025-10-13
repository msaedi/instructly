import { useEffect, useState } from 'react';
import { fetchPricingConfig } from '@/lib/api/pricing';
import type { PriceFloorConfig } from '@/lib/pricing/priceFloors';
import { logger } from '@/lib/logger';

export function usePricingFloors() {
  const [floors, setFloors] = useState<PriceFloorConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setIsLoading(true);
        const response = await fetchPricingConfig();
        if (!cancelled) {
          setFloors(response.config.price_floor_cents);
          setError(null);
        }
      } catch (err) {
        logger.error('Failed to fetch pricing floors', err as Error);
        if (!cancelled) {
          setError('Unable to load minimum pricing rules.');
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

  return { floors, isLoading, error };
}
