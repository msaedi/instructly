/**
 * React Query hook for 2FA status
 *
 * Provides cached access to the current user's two-factor authentication status.
 * This replaces direct fetchWithAuth calls to /api/v1/2fa/status.
 *
 * @example
 * ```tsx
 * function SecuritySettings() {
 *   const { data: tfaStatus, isLoading } = useTfaStatus();
 *
 *   if (isLoading) return <div>Loading...</div>;
 *   return <div>2FA is {tfaStatus?.enabled ? 'enabled' : 'disabled'}</div>;
 * }
 * ```
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchWithAuth } from '@/lib/api';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import type { components } from '@/features/shared/api/types';

type TfaStatus = components['schemas']['TFAStatusResponse'];

const QUERY_KEY = ['user', '2fa', 'status'] as const;

/**
 * Hook to fetch user's 2FA status
 *
 * @param enabled - Whether the query should be enabled (default: true)
 * @returns React Query result with TfaStatus data
 */
export function useTfaStatus(enabled: boolean = true) {
  return useQuery<TfaStatus>({
    queryKey: QUERY_KEY,
    queryFn: async () => {
      const response = await fetchWithAuth('/api/v1/2fa/status');
      if (!response.ok) {
        throw new Error('Failed to fetch 2FA status');
      }
      return (await response.json()) as TfaStatus;
    },
    enabled,
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes - status doesn't change often
    refetchOnWindowFocus: false,
  });
}

/**
 * Query key for use with invalidation
 */
export const tfaStatusQueryKey = QUERY_KEY;

/**
 * Hook to invalidate 2FA status cache
 * Use this after enabling, disabling, or modifying 2FA settings
 */
export function useInvalidateTfaStatus() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });
}
