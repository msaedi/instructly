import { useQuery } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { queryFn } from '@/lib/react-query/api';
import type { InstructorService } from '@/types/instructor';

interface ServicesResponse {
  services: InstructorService[];
  total: number;
}

/**
 * Hook to fetch instructor services
 * Uses 1-hour cache as services rarely change
 */
export function useInstructorServices(instructorId: string) {
  return useQuery<ServicesResponse>({
    queryKey: ['instructors', instructorId, 'services'],
    queryFn: queryFn(`/instructors/${instructorId}/services`, {
      requireAuth: false, // Public endpoint
    }),
    staleTime: CACHE_TIMES.STATIC, // 1 hour
    enabled: !!instructorId,
  });
}
