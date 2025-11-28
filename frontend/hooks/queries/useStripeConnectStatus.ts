/**
 * React Query hook for Stripe Connect onboarding status
 *
 * Provides cached access to the instructor's Stripe Connect account status.
 * This replaces direct fetchWithAuth calls to /api/v1/payments/connect/status.
 *
 * @example
 * ```tsx
 * function StripeStatus() {
 *   const { data: status, isLoading } = useStripeConnectStatus();
 *
 *   if (isLoading) return <div>Loading...</div>;
 *   if (status?.onboarding_completed) return <div>Setup complete!</div>;
 *   return <div>Please complete Stripe setup</div>;
 * }
 * ```
 */
import { useQuery } from '@tanstack/react-query';

import { fetchWithAuth } from '@/lib/api';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

export interface StripeConnectStatus {
  has_account: boolean;
  onboarding_completed: boolean;
  charges_enabled: boolean;
  payouts_enabled: boolean;
  details_submitted: boolean;
}

const QUERY_KEY = ['payments', 'connect', 'status'] as const;

/**
 * Hook to fetch Stripe Connect onboarding status
 *
 * @param enabled - Whether the query should be enabled (default: true)
 * @returns React Query result with StripeConnectStatus data
 */
export function useStripeConnectStatus(enabled: boolean = true) {
  return useQuery<StripeConnectStatus>({
    queryKey: QUERY_KEY,
    queryFn: async () => {
      const response = await fetchWithAuth('/api/v1/payments/connect/status');
      if (!response.ok) {
        throw new Error('Failed to fetch Stripe Connect status');
      }
      return response.json() as Promise<StripeConnectStatus>;
    },
    enabled,
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes - status doesn't change often
    refetchOnWindowFocus: false,
  });
}

/**
 * Query key for use with invalidation
 */
export const stripeConnectStatusQueryKey = QUERY_KEY;
