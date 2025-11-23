import { useQuery } from '@tanstack/react-query';

import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import { paymentService, type EarningsResponse } from '@/services/api/payments';

export function useInstructorEarnings(enabled: boolean = true) {
  return useQuery<EarningsResponse>({
    queryKey: ['instructor', 'earnings'],
    queryFn: () => paymentService.getEarnings(),
    enabled,
    staleTime: CACHE_TIMES.FREQUENT,
    refetchOnWindowFocus: false,
  });
}
