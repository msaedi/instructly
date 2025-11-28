/**
 * React Query hooks for batch reviews operations
 *
 * Provides cached access to batch rating lookups and existing review checks.
 * These replace direct reviewsApi calls in components to prevent duplicate API calls.
 *
 * @example
 * ```tsx
 * function LessonsList({ instructorIds }: { instructorIds: string[] }) {
 *   const { data: ratingsMap } = useRatingsBatch(instructorIds);
 *
 *   return instructorIds.map(id => (
 *     <div key={id}>Rating: {ratingsMap?.[id]?.rating ?? 'N/A'}</div>
 *   ));
 * }
 * ```
 */
import { useQuery } from '@tanstack/react-query';

import { reviewsApi, type RatingsBatchItem } from '@/services/api/reviews';
import { CACHE_TIMES } from '@/lib/react-query/queryClient';

/**
 * Hook to fetch ratings for multiple instructors in a single batch request.
 *
 * Returns a map of instructor_id -> { rating, review_count } for easy lookup.
 *
 * @param instructorIds - Array of instructor IDs to fetch ratings for
 * @param enabled - Whether the query should be enabled (default: true when instructorIds has items)
 */
export function useRatingsBatch(instructorIds: string[], enabled?: boolean) {
  // Sort IDs for consistent query key
  const sortedIds = [...instructorIds].sort();
  const queryEnabled = enabled ?? (sortedIds.length > 0);

  return useQuery({
    queryKey: ['reviews', 'ratings', 'batch', sortedIds],
    queryFn: async () => {
      if (sortedIds.length === 0) {
        return {} as Record<string, { rating: number | null; review_count: number }>;
      }
      const res = await reviewsApi.getRatingsBatch(sortedIds);
      // Convert array to map for O(1) lookups
      const ratingsMap: Record<string, { rating: number | null; review_count: number }> = {};
      for (const item of res.results) {
        ratingsMap[item.instructor_id] = { rating: item.rating, review_count: item.review_count };
      }
      return ratingsMap;
    },
    enabled: queryEnabled,
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes - ratings don't change often
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook to check which bookings already have reviews.
 *
 * Returns an array of booking IDs that have existing reviews,
 * and a convenient map for O(1) lookups.
 *
 * @param bookingIds - Array of booking IDs to check
 * @param enabled - Whether the query should be enabled (default: true when bookingIds has items)
 */
export function useExistingReviews(bookingIds: string[], enabled?: boolean) {
  // Sort IDs for consistent query key
  const sortedIds = [...bookingIds].sort();
  const queryEnabled = enabled ?? (sortedIds.length > 0);

  return useQuery({
    queryKey: ['reviews', 'booking', 'existing', sortedIds],
    queryFn: async () => {
      if (sortedIds.length === 0) {
        return { reviewedIds: [] as string[], reviewedMap: {} as Record<string, boolean> };
      }
      const reviewedIds = await reviewsApi.getExistingForBookings(sortedIds);
      // Create map for O(1) lookups
      const reviewedMap: Record<string, boolean> = {};
      for (const bid of reviewedIds) {
        reviewedMap[bid] = true;
      }
      return { reviewedIds, reviewedMap };
    },
    enabled: queryEnabled,
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    refetchOnWindowFocus: false,
  });
}

// Re-export types for convenience
export type { RatingsBatchItem };
