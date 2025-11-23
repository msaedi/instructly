import { useQuery } from '@tanstack/react-query';

import { API_ENDPOINTS, fetchWithAuth } from '@/lib/api';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import type { InstructorProfile } from '@/types/instructor';

export function useInstructorProfileMe(enabled: boolean = true) {
  return useQuery<InstructorProfile>({
    queryKey: ['instructor', 'me'],
    queryFn: async () => {
      const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_PROFILE);
      if (!response.ok) {
        let message = 'Failed to load instructor profile';
        try {
          const errorBody = (await response.json()) as { detail?: string };
          if (errorBody?.detail) {
            message = errorBody.detail;
          }
        } catch {
          // ignore parse errors
        }
        const error = new Error(message) as Error & { status?: number };
        error.status = response.status;
        throw error;
      }
      return (await response.json()) as InstructorProfile;
    },
    staleTime: CACHE_TIMES.FREQUENT,
    refetchOnWindowFocus: false,
    enabled,
  });
}
