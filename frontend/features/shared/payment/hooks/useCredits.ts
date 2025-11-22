import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { paymentService } from '@/services/api/payments';
import { logger } from '@/lib/logger';

export interface CreditBalance {
  available: number;
  expires_at: string | null;
  pending: number;
}

/**
 * Shared hook for fetching user's credit balance using React Query.
 *
 * This ensures that all components displaying credits (PaymentSection, BillingTab, etc.)
 * share the same cache and automatically update when credits are invalidated.
 *
 * Usage:
 * ```tsx
 * const { data: credits, isLoading, refetch } = useCredits();
 * const availableAmount = credits?.available ?? 0;
 * ```
 */
export function useCredits() {
  return useQuery<CreditBalance>({
    queryKey: queryKeys.payments.credits,
    queryFn: async () => {
      try {
        const balance = await paymentService.getCreditBalance();
        logger.debug('Credits fetched via useCredits hook', { available: balance.available });
        return balance;
      } catch (error) {
        logger.error('Failed to fetch credit balance', error as Error);
        throw error;
      }
    },
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    // Return zero balance on error instead of throwing
    retry: (failureCount, error) => {
      // Don't retry on 4xx errors (client errors)
      if (error && typeof error === 'object' && 'status' in error) {
        const status = error.status;
        if (typeof status === 'number' && status >= 400 && status < 500) {
          return false;
        }
      }
      // Retry up to 2 times for server/network errors
      return failureCount < 2;
    },
    // Provide a default value if query fails
    placeholderData: {
      available: 0,
      expires_at: null,
      pending: 0,
    },
  });
}
