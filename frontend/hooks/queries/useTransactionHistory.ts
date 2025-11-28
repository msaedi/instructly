/**
 * React Query hook for fetching transaction history
 *
 * Provides cached access to the user's transaction history.
 * This replaces direct paymentService.getTransactionHistory calls to prevent duplicate API calls.
 *
 * @example
 * ```tsx
 * function TransactionList() {
 *   const { data: transactions, isLoading } = useTransactionHistory();
 *
 *   return isLoading ? <Spinner /> : <TransactionTable data={transactions} />;
 * }
 * ```
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { paymentService, Transaction } from '@/services/api/payments';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

/**
 * Query key for transaction history - exported for cache invalidation
 */
export const TRANSACTION_HISTORY_QUERY_KEY = ['payments', 'transactions'] as const;

/**
 * Hook to fetch user's transaction history with React Query caching.
 * This prevents duplicate API calls from React Strict Mode.
 */
export function useTransactionHistory(limit = 20, offset = 0) {
  return useQuery<Transaction[], Error>({
    queryKey: [...TRANSACTION_HISTORY_QUERY_KEY, { limit, offset }],
    queryFn: async () => {
      return paymentService.getTransactionHistory(limit, offset);
    },
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook to invalidate transaction history cache.
 * Use this after a new transaction is created.
 */
export function useInvalidateTransactionHistory() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: TRANSACTION_HISTORY_QUERY_KEY });
}
