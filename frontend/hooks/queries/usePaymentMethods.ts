/**
 * React Query hook for fetching payment methods
 *
 * Provides cached access to the user's saved payment methods.
 * This replaces direct paymentService.listPaymentMethods calls to prevent duplicate API calls.
 *
 * @example
 * ```tsx
 * function PaymentSection() {
 *   const { data: paymentMethods, isLoading } = usePaymentMethods();
 *
 *   return isLoading ? <Spinner /> : <PaymentMethodList methods={paymentMethods} />;
 * }
 * ```
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { paymentService } from '@/services/api/payments';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

export interface PaymentMethodData {
  id: string;
  last4: string;
  brand: string;
  is_default: boolean;
  created_at: string;
}

/**
 * Query key for payment methods - exported for cache invalidation
 */
export const PAYMENT_METHODS_QUERY_KEY = ['payments', 'methods'] as const;

/**
 * Hook to fetch user's saved payment methods with React Query caching.
 * This prevents duplicate API calls from React Strict Mode.
 */
export function usePaymentMethods() {
  return useQuery<PaymentMethodData[], Error>({
    queryKey: PAYMENT_METHODS_QUERY_KEY,
    queryFn: async () => {
      const methods = await paymentService.listPaymentMethods();
      return methods;
    },
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook to invalidate payment methods cache.
 * Use this after adding/removing a payment method.
 */
export function useInvalidatePaymentMethods() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: PAYMENT_METHODS_QUERY_KEY });
}
