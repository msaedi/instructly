import { useQuery } from '@tanstack/react-query';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';
import { reviewsApi, ReviewListPageResponse } from '@/services/api/reviews';
import { queryKeys } from '@/src/api/queryKeys';

// ReviewItem and ReviewsResponse removed - use generated types from @/services/api/reviews
// which re-exports from @/features/shared/api/types (OpenAPI shim)

export function useInstructorReviews(
  instructorId: string,
  page: number = 1,
  limit: number = 12,
  opts?: { minRating?: number; rating?: number; withText?: boolean; instructorServiceId?: string }
) {
  const queryKeyFilters: {
    page: number;
    limit: number;
    minRating?: number;
    rating?: number;
    withText?: boolean;
    instructorServiceId?: string;
  } = {
    page,
    limit,
  };

  if (opts?.minRating !== undefined) {
    queryKeyFilters.minRating = opts.minRating;
  }

  if (opts?.rating !== undefined) {
    queryKeyFilters.rating = opts.rating;
  }

  if (opts?.withText !== undefined) {
    queryKeyFilters.withText = opts.withText;
  }

  if (opts?.instructorServiceId !== undefined) {
    queryKeyFilters.instructorServiceId = opts.instructorServiceId;
  }

  return useQuery<ReviewListPageResponse>({
    queryKey: queryKeys.instructors.reviewsList(instructorId, queryKeyFilters),
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
