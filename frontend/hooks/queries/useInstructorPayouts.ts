import { useQuery } from '@tanstack/react-query';

import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import { paymentService, type PayoutHistoryResponse } from '@/services/api/payments';

export function useInstructorPayouts(enabled: boolean = true) {
  return useQuery<PayoutHistoryResponse>({
    queryKey: ['instructor', 'payouts'],
    queryFn: () => paymentService.getPayouts(),
    enabled,
    staleTime: CACHE_TIMES.FREQUENT,
    refetchOnWindowFocus: false,
  });
}
