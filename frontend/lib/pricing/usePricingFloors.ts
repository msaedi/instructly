import { useQuery } from '@tanstack/react-query';
import { fetchPricingConfig, type PricingConfig } from '@/lib/api/pricing';
import type { PriceFloorConfig } from '@/lib/pricing/priceFloors';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

/**
 * Query key for pricing config - exported for cache invalidation
 */
export const PRICING_CONFIG_QUERY_KEY = ['config', 'pricing'] as const;

/**
 * Hook to fetch pricing configuration with React Query caching.
 * This prevents duplicate API calls from React Strict Mode and
 * enables query deduplication across multiple components.
 */
export function usePricingConfig() {
  const { data, isLoading, error } = useQuery<PricingConfig, Error>({
    queryKey: PRICING_CONFIG_QUERY_KEY,
    queryFn: async () => {
      const response = await fetchPricingConfig();
      return response.config;
    },
    staleTime: CACHE_TIMES.STATIC, // 1 hour - pricing config rarely changes
    refetchOnWindowFocus: false,
  });

  return {
    config: data ?? null,
    isLoading,
    error: error ? 'Unable to load pricing configuration.' : null,
  };
}

export function usePricingFloors() {
  const { config, isLoading, error } = usePricingConfig();
  const floors: PriceFloorConfig | null = config?.price_floor_cents ?? null;
  return { floors, isLoading, error };
}
