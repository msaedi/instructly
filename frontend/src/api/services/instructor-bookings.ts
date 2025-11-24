/**
 * Instructor Bookings Service Layer
 *
 * Domain-friendly wrappers around Orval-generated instructor-bookings v1 hooks.
 * This is the ONLY layer that should directly import from generated/instructor-bookings-v1.
 *
 * Components should use these hooks, not the raw Orval-generated ones.
 */

import { queryKeys } from '@/src/api/queryKeys';
import {
  useListInstructorBookingsApiV1InstructorBookingsGet,
  useGetPendingCompletionBookingsApiV1InstructorBookingsPendingCompletionGet,
  useGetUpcomingBookingsApiV1InstructorBookingsUpcomingGet,
  useGetCompletedBookingsApiV1InstructorBookingsCompletedGet,
  useMarkLessonCompleteApiV1InstructorBookingsBookingIdCompletePost,
} from '@/src/api/generated/instructor-bookings-v1/instructor-bookings-v1';
import type {
  ListInstructorBookingsApiV1InstructorBookingsGetParams,
} from '@/src/api/generated/instructly.schemas';

/**
 * List instructor bookings with optional filters.
 *
 * @param params - Filter parameters
 * @example
 * ```tsx
 * function InstructorBookingsList() {
 *   const { data, isLoading } = useInstructorBookingsList({
 *     status: 'CONFIRMED',
 *     page: 1
 *   });
 *
 *   if (isLoading) return <div>Loading...</div>;
 *
 *   return <div>{data?.items.length} bookings</div>;
 * }
 * ```
 */
export function useInstructorBookingsList(
  params?: ListInstructorBookingsApiV1InstructorBookingsGetParams
) {
  // Build query params that satisfy exactOptionalPropertyTypes
  const queryParams =
    params?.status !== undefined && params.status !== null
      ? { status: params.status.toString() }
      : undefined;

  return useListInstructorBookingsApiV1InstructorBookingsGet(params, {
    query: {
      queryKey: queryKeys.bookings.instructor(queryParams),
      staleTime: 1000 * 60 * 5, // 5 minutes
    },
  });
}

/**
 * Get bookings pending completion.
 *
 * Returns bookings that have ended but haven't been marked complete yet.
 *
 * @example
 * ```tsx
 * function PendingCompletionList() {
 *   const { data, isLoading } = usePendingCompletionBookings();
 *
 *   if (isLoading) return <div>Loading...</div>;
 *
 *   return <div>{data?.items.length} bookings to complete</div>;
 * }
 * ```
 */
export function usePendingCompletionBookings(page: number = 1, perPage: number = 20) {
  return useGetPendingCompletionBookingsApiV1InstructorBookingsPendingCompletionGet(
    { page, per_page: perPage },
    {
      query: {
        queryKey: queryKeys.bookings.instructor({ status: 'pending-completion' }),
        staleTime: 1000 * 60 * 1, // 1 minute (more fresh for pending items)
      },
    }
  );
}

/**
 * Get upcoming instructor bookings.
 *
 * @example
 * ```tsx
 * function UpcomingBookingsList() {
 *   const { data, isLoading } = useInstructorUpcomingBookings();
 *
 *   if (isLoading) return <div>Loading...</div>;
 *
 *   return <div>{data?.items.length} upcoming bookings</div>;
 * }
 * ```
 */
export function useInstructorUpcomingBookings(page: number = 1, perPage: number = 20) {
  return useGetUpcomingBookingsApiV1InstructorBookingsUpcomingGet(
    { page, per_page: perPage },
    {
      query: {
        queryKey: queryKeys.bookings.instructor({ status: 'upcoming' }),
        staleTime: 1000 * 60 * 5, // 5 minutes
      },
    }
  );
}

/**
 * Get completed instructor bookings.
 *
 * @example
 * ```tsx
 * function CompletedBookingsList() {
 *   const { data, isLoading } = useInstructorCompletedBookings();
 *
 *   if (isLoading) return <div>Loading...</div>;
 *
 *   return <div>{data?.items.length} completed bookings</div>;
 * }
 * ```
 */
export function useInstructorCompletedBookings(page: number = 1, perPage: number = 20) {
  return useGetCompletedBookingsApiV1InstructorBookingsCompletedGet(
    { page, per_page: perPage },
    {
      query: {
        queryKey: queryKeys.bookings.instructor({ status: 'completed' }),
        staleTime: 1000 * 60 * 15, // 15 minutes (completed bookings change rarely)
      },
    }
  );
}

/**
 * Mark lesson complete mutation.
 *
 * @example
 * ```tsx
 * function MarkCompleteButton({ bookingId }: { bookingId: string }) {
 *   const markComplete = useMarkLessonComplete();
 *
 *   const handleComplete = async () => {
 *     await markComplete.mutateAsync({
 *       bookingId,
 *       notes: 'Great lesson!'
 *     });
 *   };
 *
 *   return <button onClick={handleComplete}>Mark Complete</button>;
 * }
 * ```
 */
export function useMarkLessonComplete() {
  return useMarkLessonCompleteApiV1InstructorBookingsBookingIdCompletePost();
}

/**
 * Type exports for convenience
 */
export type {
  ListInstructorBookingsApiV1InstructorBookingsGetParams as InstructorBookingsListParams,
};
