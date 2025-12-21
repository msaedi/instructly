import { useQuery } from '@tanstack/react-query';
import { fetchPlatformConfig, type PlatformConfig, type PlatformFees } from '@/lib/api/config';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

export const PLATFORM_CONFIG_QUERY_KEY = ['config', 'public'] as const;

const FALLBACK_FEES: PlatformFees = {
  founding_instructor: 0.08,
  tier_1: 0.15,
  tier_2: 0.12,
  tier_3: 0.10,
  student_booking_fee: 0.12,
};

export function usePlatformConfig() {
  const { data, isLoading, error } = useQuery<PlatformConfig, Error>({
    queryKey: PLATFORM_CONFIG_QUERY_KEY,
    queryFn: fetchPlatformConfig,
    staleTime: CACHE_TIMES.STATIC,
    gcTime: CACHE_TIMES.STATIC * 24,
    refetchOnWindowFocus: false,
  });

  return {
    config: data ?? null,
    isLoading,
    error: error ? 'Unable to load platform configuration.' : null,
  };
}

export function usePlatformFees() {
  const { config, isLoading, error } = usePlatformConfig();
  return {
    fees: config?.fees ?? FALLBACK_FEES,
    isLoading,
    error,
  };
}
