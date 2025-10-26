'use client';

import { useQuery } from '@tanstack/react-query';
import { badgesApi } from '@/services/api/badges';
import type { StudentBadgeItem } from '@/types/badges';
import { CACHE_TIMES, queryKeys } from '@/lib/react-query/queryClient';

export function useStudentBadges() {
  return useQuery<StudentBadgeItem[], Error>({
    queryKey: queryKeys.badges.student,
    queryFn: badgesApi.getStudentBadges,
    staleTime: CACHE_TIMES.FREQUENT,
  });
}
