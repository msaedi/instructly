import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys, CACHE_TIMES } from '@/lib/react-query/queryClient';
import { queryFn, mutationFn } from '@/lib/react-query/api';
import { bookingsApi } from '@/lib/api/bookings';
import type {
  BookingListResponse,
  Booking,
  CancelBookingRequest,
  BookingStatus,
} from '@/types/booking';

/**
 * Hook to fetch current/upcoming lessons
 * Only shows CONFIRMED lessons that are in the future
 * Uses 5-minute cache as these may change with new bookings
 */
export function useCurrentLessons() {
  return useQuery<BookingListResponse>({
    queryKey: queryKeys.bookings.upcoming,
    queryFn: queryFn('/bookings/', {
      params: {
        status: 'CONFIRMED',
        upcoming_only: true,
        per_page: 50,
      },
      requireAuth: true,
    }),
    staleTime: CACHE_TIMES.FREQUENT, // 5 minutes for upcoming lessons
    refetchInterval: false, // Don't poll, rely on invalidation
  });
}

/**
 * Hook to fetch lesson history (completed, cancelled, no-show, and past lessons)
 * This includes all lessons that are not upcoming confirmed lessons
 * Uses 15-minute cache as these rarely change
 */
export function useCompletedLessons(page: number = 1) {
  return useQuery<BookingListResponse>({
    queryKey: queryKeys.bookings.history(page),
    queryFn: async (context) => {
      // Fetch all bookings and filter client-side
      // This is because the backend doesn't support fetching multiple statuses at once
      const fetchFn = queryFn('/bookings/', {
        params: {
          upcoming_only: false,
          page,
          per_page: 50, // Increase to match BookAgain component
        },
        requireAuth: true,
      });

      const response = await fetchFn(context);

      // Filter out only confirmed future lessons (those belong in upcoming)
      if (response && response.bookings) {
        const now = new Date();
        response.bookings = response.bookings.filter((booking: Booking) => {
          const bookingDate = new Date(`${booking.booking_date}T${booking.start_time}`);
          // Include in history if: not confirmed OR in the past
          return booking.status !== 'CONFIRMED' || bookingDate < now;
        });
      }

      return response;
    },
    staleTime: CACHE_TIMES.SLOW, // 15 minutes for history lessons
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
export function useLessonDetails(lessonId: string | number) {
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
    { lessonId: number; reason: string },
    { previousData?: BookingListResponse }
  >({
    mutationFn: ({ lessonId, reason }) =>
      mutationFn(`/bookings/${lessonId}/cancel`, {
        method: 'POST',
        requireAuth: true,
      })({ reason }),

    onMutate: async ({ lessonId }) => {
      // Cancel any in-flight queries
      await queryClient.cancelQueries({ queryKey: queryKeys.bookings.all });

      // Optimistically update the lesson status
      const previousData = queryClient.getQueryData<BookingListResponse>(
        queryKeys.bookings.upcoming
      );

      if (previousData) {
        queryClient.setQueryData<BookingListResponse>(queryKeys.bookings.upcoming, {
          ...previousData,
          bookings: previousData.bookings.filter((lesson) => lesson.id !== lessonId),
        });
      }

      return { previousData };
    },

    onError: (err, variables, context) => {
      // Rollback on error
      if (context?.previousData) {
        queryClient.setQueryData(queryKeys.bookings.upcoming, context.previousData);
      }
    },

    onSettled: () => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
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
    { lessonId: number; newDate: string; newStartTime: string; newEndTime: string },
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
      }),

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

      return { previousDetail };
    },

    onError: (err, variables, context) => {
      // Rollback on error
      if (context?.previousDetail) {
        const detailKey = queryKeys.bookings.detail(String(variables.lessonId));
        queryClient.setQueryData(detailKey, context.previousDetail);
      }
    },

    onSettled: () => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
    },
  });
}

/**
 * Hook to complete a lesson (instructor only)
 */
export function useCompleteLesson() {
  const queryClient = useQueryClient();

  return useMutation<Booking, Error, number>({
    mutationFn: (lessonId) => bookingsApi.completeBooking(lessonId),

    onSuccess: (data) => {
      // Update cache
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(String(data.id)) });
    },
  });
}

/**
 * Hook to mark a lesson as no-show (instructor only)
 */
export function useMarkNoShow() {
  const queryClient = useQueryClient();

  return useMutation<Booking, Error, number>({
    mutationFn: (lessonId) => bookingsApi.markNoShow(lessonId),

    onSuccess: (data) => {
      // Update cache
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming });
      queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(String(data.id)) });
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
