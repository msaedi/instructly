import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { queryFn, mutationFn } from '@/lib/react-query/api';
import { bookingsApi } from '@/lib/api/bookings';
import type {
  BookingListResponse,
  Booking,
  BookingStatus,
} from '@/types/booking';

/**
 * Hook to fetch current/upcoming lessons
 * Only shows CONFIRMED lessons that are in the future
 * Uses 5-minute cache as these may change with new bookings
 */
export function useCurrentLessons(enabled: boolean = true) {
  return useQuery<BookingListResponse>({
    queryKey: queryKeys.bookings.all,
    queryFn: queryFn('/bookings/upcoming', {
      params: {
        limit: 20,
      },
      requireAuth: true,
    }),
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes for upcoming lessons
    refetchInterval: false, // Don't poll, rely on invalidation
    enabled,
  });
}

/**
 * Hook to fetch lesson history (completed, cancelled, no-show, and past lessons)
 * This includes all lessons that are not upcoming confirmed lessons
 * Uses 15-minute cache as these rarely change
 */
export function useCompletedLessons(page: number = 1, enabled: boolean = true) {
  return useQuery<BookingListResponse>({
    queryKey: queryKeys.bookings.history(page),
    queryFn: queryFn('/bookings/', {
      params: {
        exclude_future_confirmed: true, // Use new backend parameter
        page,
        per_page: 50, // Increase to match BookAgain component
      },
      requireAuth: true,
    }),
    staleTime: CACHE_TIMES.SLOW, // 15 minutes for history lessons
    enabled,
  });
}

/**
 * Hook to fetch cancelled lessons
 * Uses 30-minute cache as these rarely change
 */
export function useCancelledLessons(page: number = 1) {
  return useQuery<BookingListResponse>({
    queryKey: ['bookings', 'cancelled', { page }],
    queryFn: queryFn('/bookings/', {
      params: {
        status: 'CANCELLED',
        upcoming_only: false,
        page,
        per_page: 20,
      },
      requireAuth: true,
    }),
    staleTime: CACHE_TIMES.SLOW, // 15 minutes for cancelled lessons
  });
}

/**
 * Hook to fetch a single lesson details
 * Uses 10-minute cache consistent with list
 */
export function useLessonDetails(lessonId: string) {
  return useQuery<Booking>({
    queryKey: queryKeys.bookings.detail(String(lessonId)),
    queryFn: queryFn(`/bookings/${lessonId}`, {
      requireAuth: true,
    }),
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes
    enabled: !!lessonId,
  });
}

/**
 * Hook to cancel a lesson with optimistic update
 */
export function useCancelLesson() {
  const queryClient = useQueryClient();

  return useMutation<
    Booking,
    Error,
    { lessonId: string; reason: string },
    { previousData?: BookingListResponse }
  >({
    mutationFn: ({ lessonId, reason }) =>
      mutationFn(`/bookings/${lessonId}/cancel`, {
        method: 'POST',
        requireAuth: true,
      })({ reason }) as Promise<Booking>,

    onMutate: async ({ lessonId }) => {
      // Cancel any in-flight queries
      await queryClient.cancelQueries({ queryKey: queryKeys.bookings.all });

      // Optimistically update the lesson status
      const previousData = queryClient.getQueryData<BookingListResponse>(queryKeys.bookings.all);

      if (previousData) {
        queryClient.setQueryData<BookingListResponse>(queryKeys.bookings.all, {
          ...previousData,
          items: previousData.items.filter((lesson) => lesson.id !== lessonId),
        });
      }

      return previousData ? { previousData } : undefined;
    },

    onError: (_err, _variables, context) => {
      // Rollback on error
      if (context?.previousData) {
        queryClient.setQueryData(queryKeys.bookings.all, context.previousData);
      }
    },

    onSettled: () => {
      // Refetch to ensure consistency - invalidate ALL booking-related queries
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      // Invalidate all upcoming queries regardless of limit parameter
      queryClient.invalidateQueries({ queryKey: ['bookings', 'upcoming'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
      // Also invalidate the generic 'bookings' queries
      queryClient.invalidateQueries({ queryKey: ['bookings'] });
    },
  });
}

/**
 * Hook to reschedule a lesson
 * Note: This will need backend API support for rescheduling
 */
export function useRescheduleLesson() {
  const queryClient = useQueryClient();

  return useMutation<
    Booking,
    Error,
    { lessonId: string; newDate: string; newStartTime: string; newEndTime: string },
    { previousDetail?: Booking }
  >({
    mutationFn: ({ lessonId, newDate, newStartTime, newEndTime }) =>
      mutationFn(`/bookings/${lessonId}/reschedule`, {
        method: 'POST',
        requireAuth: true,
      })({
        booking_date: newDate,
        start_time: newStartTime,
        end_time: newEndTime,
      }) as Promise<Booking>,

    onMutate: async ({ lessonId, newDate, newStartTime, newEndTime }) => {
      // Cancel any in-flight queries
      await queryClient.cancelQueries({ queryKey: queryKeys.bookings.all });

      // Optimistically update the lesson
      const detailKey = queryKeys.bookings.detail(String(lessonId));
      const previousDetail = queryClient.getQueryData<Booking>(detailKey);

      if (previousDetail) {
        queryClient.setQueryData<Booking>(detailKey, {
          ...previousDetail,
          booking_date: newDate,
          start_time: newStartTime,
          end_time: newEndTime,
        });
      }

      return previousDetail ? { previousDetail } : undefined;
    },

    onError: (_err, _variables, context) => {
      // Rollback on error
      if (context?.previousDetail) {
        const detailKey = queryKeys.bookings.detail(String(_variables.lessonId));
        queryClient.setQueryData(detailKey, context.previousDetail);
      }
    },

    onSettled: () => {
      // Refetch to ensure consistency - invalidate ALL booking-related queries
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      // Invalidate all upcoming queries regardless of limit parameter
      queryClient.invalidateQueries({ queryKey: ['bookings', 'upcoming'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
      // Also invalidate the generic 'bookings' queries
      queryClient.invalidateQueries({ queryKey: ['bookings'] });
    },
  });
}

/**
 * Hook to complete a lesson (instructor only)
 */
export function useCompleteLesson() {
  const queryClient = useQueryClient();

  return useMutation<Booking, Error, string>({
    mutationFn: (lessonId) => bookingsApi.completeBooking(lessonId),

    onSuccess: (data) => {
      // Update cache - invalidate ALL booking-related queries
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming() });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(String(data.id)) });
      queryClient.invalidateQueries({ queryKey: ['bookings'] });
    },
  });
}

/**
 * Hook to mark a lesson as no-show (instructor only)
 */
export function useMarkNoShow() {
  const queryClient = useQueryClient();

  return useMutation<Booking, Error, string>({
    mutationFn: (lessonId) => bookingsApi.markNoShow(lessonId),

    onSuccess: (data) => {
      // Update cache - invalidate ALL booking-related queries
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming() });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(String(data.id)) });
      queryClient.invalidateQueries({ queryKey: ['bookings'] });
    },
  });
}

/**
 * Helper to calculate cancellation fee based on time until lesson
 */
export function calculateCancellationFee(lesson: Booking): {
  fee: number;
  percentage: number;
  hoursUntil: number;
} {
  const now = new Date();
  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);
  const hoursUntil = (lessonDateTime.getTime() - now.getTime()) / (1000 * 60 * 60);

  if (hoursUntil > 24) {
    return { fee: 0, percentage: 0, hoursUntil };
  } else if (hoursUntil > 12) {
    return { fee: lesson.total_price * 0.5, percentage: 50, hoursUntil };
  } else {
    return { fee: lesson.total_price, percentage: 100, hoursUntil };
  }
}

/**
 * Helper to format lesson status display
 */
export function formatLessonStatus(status: BookingStatus, cancelledAt?: string): string {
  switch (status) {
    case 'CONFIRMED':
      return 'Upcoming';
    case 'COMPLETED':
      return 'Completed';
    case 'CANCELLED':
      if (cancelledAt) {
        const cancelDate = new Date(cancelledAt);
        const lessonDate = new Date(); // Would need actual lesson date
        const hoursBeforeLesson = (lessonDate.getTime() - cancelDate.getTime()) / (1000 * 60 * 60);

        if (hoursBeforeLesson > 24) {
          return 'Cancelled (>24hrs)';
        } else if (hoursBeforeLesson > 12) {
          return 'Cancelled (12-24hrs)';
        } else {
          return 'Cancelled (<12hrs)';
        }
      }
      return 'Cancelled';
    case 'NO_SHOW':
      return 'No-show';
    default:
      return status;
  }
}
