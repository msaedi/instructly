'use client';

import { useQuery } from '@tanstack/react-query';

import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import {
  fetchInstructorCommissionStatus,
  type CommissionStatusResponse,
} from '@/src/api/services/instructors';
import { queryKeys } from '@/src/api/queryKeys';

export function useCommissionStatus(enabled: boolean = true) {
  return useQuery<CommissionStatusResponse>({
    queryKey: queryKeys.instructors.commissionStatus,
    queryFn: () => fetchInstructorCommissionStatus(),
    enabled,
    staleTime: CACHE_TIMES.FREQUENT,
    refetchOnWindowFocus: false,
  });
}
