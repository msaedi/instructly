import { useQuery } from '@tanstack/react-query';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import { reviewsApi, ReviewListPageResponse } from '@/services/api/reviews';

// ReviewItem and ReviewsResponse removed - use generated types from @/services/api/reviews
// which re-exports from @/features/shared/api/types (OpenAPI shim)

export function useInstructorReviews(
  instructorId: string,
  page: number = 1,
  limit: number = 12,
  opts?: { minRating?: number; rating?: number; withText?: boolean; instructorServiceId?: string }
) {
  return useQuery<ReviewListPageResponse>({
    queryKey: ['instructors', instructorId, 'reviews', { page, limit, opts }],
    queryFn: async (): Promise<ReviewListPageResponse> => {
      const queryOpts: { minRating?: number; rating?: number; withText?: boolean } = {};

      if (opts?.minRating !== undefined) {
        queryOpts.minRating = opts.minRating;
      }

      if (opts?.rating !== undefined) {
        queryOpts.rating = opts.rating;
      }

      if (opts?.withText !== undefined) {
        queryOpts.withText = opts.withText;
      }

      // API returns ReviewListPageResponse directly - no transformation needed
      return reviewsApi.getRecent(
        instructorId,
        opts?.instructorServiceId,
        limit,
        page,
        Object.keys(queryOpts).length > 0 ? queryOpts : undefined
      );
    },
    staleTime: CACHE_TIMES.SLOW,
    enabled: !!instructorId,
  });
}
