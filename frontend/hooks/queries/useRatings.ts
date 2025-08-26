import { useQuery } from '@tanstack/react-query';
import { reviewsApi, InstructorRatingsResponse, SearchRatingResponse } from '@/services/api/reviews';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

export function useInstructorRatingsQuery(instructorId: string) {
  return useQuery<InstructorRatingsResponse>({
    queryKey: ['ratings', 'instructor', instructorId],
    queryFn: () => reviewsApi.getInstructorRatings(instructorId),
    enabled: !!instructorId,
    staleTime: 5 * 60 * 1000, // 5 minutes to align with backend cache
    gcTime: CACHE_TIMES.SLOW, // reuse existing slow cache window
  });
}

export function useSearchRatingQuery(instructorId: string, instructorServiceId?: string) {
  return useQuery<SearchRatingResponse>({
    queryKey: ['ratings', 'search', instructorId, instructorServiceId || 'all'],
    queryFn: () => reviewsApi.getSearchRating(instructorId, instructorServiceId),
    enabled: !!instructorId,
    staleTime: 5 * 60 * 1000,
    gcTime: CACHE_TIMES.SLOW,
  });
}
