/**
 * Reviews v1 Service Layer
 *
 * Provides typed hooks and functions for the Reviews domain.
 * All reviews API interactions should go through this service layer.
 *
 * @module reviews
 * @see /api/v1/reviews
 */

import {
  // Query hooks
  useGetReviewForBookingApiV1ReviewsBookingBookingIdGet,
  useGetInstructorRatingsApiV1ReviewsInstructorInstructorIdRatingsGet,
  useGetRecentReviewsApiV1ReviewsInstructorInstructorIdRecentGet,
  useGetSearchRatingApiV1ReviewsInstructorInstructorIdSearchRatingGet,
  // Mutation hooks
  useSubmitReviewApiV1ReviewsPost,
  useGetExistingReviewsForBookingsApiV1ReviewsBookingExistingPost,
  useGetRatingsBatchApiV1ReviewsRatingsBatchPost,
  useRespondToReviewApiV1ReviewsReviewIdRespondPost,
} from '@/src/api/generated/reviews-v1/reviews-v1';

// =============================================================================
// Query Hooks - Data fetching with React Query
// =============================================================================

/**
 * Get rating statistics for an instructor.
 *
 * Public endpoint - no authentication required.
 * Returns overall rating, per-service ratings, and rating distribution.
 *
 * @example
 * ```tsx
 * function InstructorRatings({ instructorId }: { instructorId: string }) {
 *   const { data, isLoading } = useInstructorRatings(instructorId);
 *
 *   if (isLoading) return <Spinner />;
 *   return <RatingDisplay overall={data?.overall} />;
 * }
 * ```
 */
export function useInstructorRatings(instructorId: string) {
  return useGetInstructorRatingsApiV1ReviewsInstructorInstructorIdRatingsGet(instructorId, {
    query: {
      enabled: !!instructorId,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  });
}

/**
 * Get paginated list of recent reviews for an instructor.
 *
 * Public endpoint - no authentication required.
 * Supports filtering by rating, service, and text presence.
 *
 * @example
 * ```tsx
 * function ReviewList({ instructorId }: { instructorId: string }) {
 *   const { data } = useRecentReviews({ instructorId, limit: 10, page: 1 });
 *   return <ReviewCards reviews={data?.reviews} />;
 * }
 * ```
 */
export function useRecentReviews(params: {
  instructorId: string;
  instructorServiceId?: string;
  limit?: number;
  page?: number;
  minRating?: number;
  rating?: number;
  withText?: boolean;
}) {
  const { instructorId, instructorServiceId, limit, page, minRating, rating, withText } = params;
  return useGetRecentReviewsApiV1ReviewsInstructorInstructorIdRecentGet(
    instructorId,
    {
      instructor_service_id: instructorServiceId,
      limit,
      page,
      min_rating: minRating,
      rating,
      with_text: withText,
    },
    {
      query: {
        enabled: !!instructorId,
        staleTime: 5 * 60 * 1000, // 5 minutes
      },
    }
  );
}

/**
 * Get compact rating info for search results context.
 *
 * Public endpoint - no authentication required.
 * Returns rating and review count optimized for search result display.
 *
 * @example
 * ```tsx
 * function SearchRating({ instructorId }: { instructorId: string }) {
 *   const { data } = useSearchRating(instructorId);
 *   return <RatingBadge rating={data?.rating} count={data?.review_count} />;
 * }
 * ```
 */
export function useSearchRating(instructorId: string, instructorServiceId?: string) {
  return useGetSearchRatingApiV1ReviewsInstructorInstructorIdSearchRatingGet(
    instructorId,
    { instructor_service_id: instructorServiceId },
    {
      query: {
        enabled: !!instructorId,
        staleTime: 5 * 60 * 1000, // 5 minutes
      },
    }
  );
}

/**
 * Get the review for a specific booking.
 *
 * Students can only view reviews they submitted.
 * Returns null if no review exists for the booking.
 *
 * @example
 * ```tsx
 * function BookingReview({ bookingId }: { bookingId: string }) {
 *   const { data: review } = useReviewForBooking(bookingId);
 *   if (!review) return <WriteReviewButton />;
 *   return <ReviewCard review={review} />;
 * }
 * ```
 */
export function useReviewForBooking(bookingId: string) {
  return useGetReviewForBookingApiV1ReviewsBookingBookingIdGet(bookingId, {
    query: {
      enabled: !!bookingId,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  });
}

// =============================================================================
// Mutation Hooks - Data modification with React Query
// =============================================================================

/**
 * Submit a new review for a completed booking.
 *
 * Students can submit one review per booking.
 * Optionally include a tip amount for the instructor.
 *
 * @example
 * ```tsx
 * function ReviewForm({ bookingId }: { bookingId: string }) {
 *   const submitReview = useSubmitReview();
 *
 *   const handleSubmit = async (data: ReviewFormData) => {
 *     await submitReview.mutateAsync({
 *       data: {
 *         booking_id: bookingId,
 *         rating: data.rating,
 *         review_text: data.text,
 *         tip_amount_cents: data.tipCents,
 *       },
 *     });
 *   };
 *
 *   return <ReviewFormUI onSubmit={handleSubmit} />;
 * }
 * ```
 */
export function useSubmitReview() {
  return useSubmitReviewApiV1ReviewsPost();
}

/**
 * Check which bookings already have reviews.
 *
 * Returns list of booking IDs that have existing reviews.
 * Only returns reviews for bookings owned by the current student.
 *
 * @example
 * ```tsx
 * function BookingList({ bookingIds }: { bookingIds: string[] }) {
 *   const checkExisting = useCheckExistingReviews();
 *
 *   useEffect(() => {
 *     checkExisting.mutate({ data: bookingIds });
 *   }, [bookingIds]);
 *
 *   const reviewedIds = new Set(checkExisting.data || []);
 *   // ...
 * }
 * ```
 */
export function useCheckExistingReviews() {
  return useGetExistingReviewsForBookingsApiV1ReviewsBookingExistingPost();
}

/**
 * Get ratings for multiple instructors in a single request.
 *
 * Public endpoint - no authentication required.
 *
 * @example
 * ```tsx
 * function InstructorGrid({ instructorIds }: { instructorIds: string[] }) {
 *   const batchRatings = useBatchRatings();
 *
 *   useEffect(() => {
 *     batchRatings.mutate({ data: { instructor_ids: instructorIds } });
 *   }, [instructorIds]);
 *
 *   // Use batchRatings.data?.results
 * }
 * ```
 */
export function useBatchRatings() {
  return useGetRatingsBatchApiV1ReviewsRatingsBatchPost();
}

/**
 * Add an instructor response to a review.
 *
 * Only the instructor who received the review can respond.
 *
 * @example
 * ```tsx
 * function RespondToReview({ reviewId }: { reviewId: string }) {
 *   const respond = useRespondToReview();
 *
 *   const handleRespond = async (text: string) => {
 *     await respond.mutateAsync({
 *       reviewId,
 *       data: { response_text: text },
 *     });
 *   };
 *
 *   return <ResponseForm onSubmit={handleRespond} />;
 * }
 * ```
 */
export function useRespondToReview() {
  return useRespondToReviewApiV1ReviewsReviewIdRespondPost();
}

// =============================================================================
// Imperative API functions for use in useEffect or other non-hook contexts
// =============================================================================

/**
 * Submit a review imperatively.
 */
export { submitReviewApiV1ReviewsPost as submitReviewImperative } from '@/src/api/generated/reviews-v1/reviews-v1';

/**
 * Check existing reviews imperatively.
 */
export { getExistingReviewsForBookingsApiV1ReviewsBookingExistingPost as checkExistingReviewsImperative } from '@/src/api/generated/reviews-v1/reviews-v1';

/**
 * Get instructor ratings imperatively.
 */
export { getInstructorRatingsApiV1ReviewsInstructorInstructorIdRatingsGet as getInstructorRatingsImperative } from '@/src/api/generated/reviews-v1/reviews-v1';

/**
 * Get recent reviews imperatively.
 */
export { getRecentReviewsApiV1ReviewsInstructorInstructorIdRecentGet as getRecentReviewsImperative } from '@/src/api/generated/reviews-v1/reviews-v1';

/**
 * Get search rating imperatively.
 */
export { getSearchRatingApiV1ReviewsInstructorInstructorIdSearchRatingGet as getSearchRatingImperative } from '@/src/api/generated/reviews-v1/reviews-v1';

/**
 * Get batch ratings imperatively.
 */
export { getRatingsBatchApiV1ReviewsRatingsBatchPost as getBatchRatingsImperative } from '@/src/api/generated/reviews-v1/reviews-v1';

/**
 * Respond to review imperatively.
 */
export { respondToReviewApiV1ReviewsReviewIdRespondPost as respondToReviewImperative } from '@/src/api/generated/reviews-v1/reviews-v1';

/**
 * Get review for booking imperatively.
 */
export { getReviewForBookingApiV1ReviewsBookingBookingIdGet as getReviewForBookingImperative } from '@/src/api/generated/reviews-v1/reviews-v1';

// =============================================================================
// Type exports for convenience
// =============================================================================

export type {
  ReviewSubmitRequest,
  ReviewSubmitResponse,
  InstructorRatingsResponse,
  ReviewListPageResponse,
  ReviewItem,
  SearchRatingResponse,
  ExistingReviewIdsResponse,
  RatingsBatchRequest,
  RatingsBatchResponse,
  ReviewResponseModel,
} from '@/src/api/generated/instructly.schemas';
