import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';
import type {
  BookingListResponse,
  Booking,
  BookingStatus,
  PaymentSummary,
} from '@/features/shared/api/types';
import {
  useBookingsList,
  useBookingsHistory,
  useCancelledBookings as useCancelledBookingsV1,
  useBooking,
  useCancelBooking,
  useRescheduleBooking,
  useCompleteBooking,
  useMarkBookingNoShow,
  fetchBookingsList,
} from '@/src/api/services/bookings';

/**
 * Hook to fetch current/upcoming lessons
 * Only shows CONFIRMED lessons that are in the future
 * Uses 5-minute cache as these may change with new bookings
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/bookings endpoint with upcoming_only filter
 *
 * @param page - Page number (1-based)
 */
export function useCurrentLessons(page: number = 1) {
  // Use v1 service with upcoming_only filter to get full booking objects
  const result = useBookingsList({
    upcoming_only: true,
    page,
    per_page: 10,
  });

  // Map v1 response to expected shape
  return {
    ...result,
    data: result.data ? {
      items: result.data.items as Booking[],
      total: result.data.total,
      page: result.data.page ?? page,
      per_page: result.data.per_page ?? 10,
      has_next: result.data.has_next,
      has_prev: result.data.has_prev,
    } as BookingListResponse : undefined,
  };
}

/**
 * Hook to fetch current/upcoming lessons with infinite pagination.
 *
 * Uses /api/v1/bookings endpoint with upcoming_only filter.
 */
export function useCurrentLessonsInfinite() {
  const query = useInfiniteQuery({
    queryKey: queryKeys.bookings.upcoming(10),
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      fetchBookingsList({
        upcoming_only: true,
        page: pageParam,
        per_page: 10,
      }),
    getNextPageParam: (lastPage) =>
      lastPage.has_next ? (lastPage.page ?? 1) + 1 : undefined,
    staleTime: 1000 * 60 * 5,
  });

  const data = query.data
    ? ({
      items: query.data.pages.flatMap((page) => page.items ?? []) as Booking[],
      total: query.data.pages[0]?.total ?? 0,
      page: query.data.pages.at(-1)?.page ?? 1,
      per_page: query.data.pages[0]?.per_page ?? 10,
      has_next: query.hasNextPage ?? false,
      has_prev: query.data.pages[0]?.has_prev ?? false,
    } as BookingListResponse)
    : undefined;

  return {
    ...query,
    data,
  };
}

/**
 * Hook to fetch lesson history (completed, cancelled, no-show, and past lessons)
 * This includes all lessons that are not upcoming confirmed lessons
 * Uses 15-minute cache as these rarely change
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/bookings endpoint with exclude_future_confirmed filter
 *
 * @param page - Page number (1-based)
 */
export function useCompletedLessons(page: number = 1) {
  const result = useBookingsHistory(page, 10);

  // Map v1 response to expected shape
  return {
    ...result,
    data: result.data ? {
      items: result.data.items as Booking[],
      total: result.data.total,
      page: result.data.page ?? page,
      per_page: result.data.per_page ?? 10,
      has_next: result.data.has_next,
      has_prev: result.data.has_prev,
    } as BookingListResponse : undefined,
  };
}

/**
 * Hook to fetch lesson history with infinite pagination.
 *
 * Uses /api/v1/bookings endpoint with exclude_future_confirmed filter.
 */
export function useCompletedLessonsInfinite() {
  const query = useInfiniteQuery({
    queryKey: queryKeys.bookings.history(),
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      fetchBookingsList({
        exclude_future_confirmed: true,
        page: pageParam,
        per_page: 10,
      }),
    getNextPageParam: (lastPage) =>
      lastPage.has_next ? (lastPage.page ?? 1) + 1 : undefined,
    staleTime: 1000 * 60 * 15,
  });

  const data = query.data
    ? ({
      items: query.data.pages.flatMap((page) => page.items ?? []) as Booking[],
      total: query.data.pages[0]?.total ?? 0,
      page: query.data.pages.at(-1)?.page ?? 1,
      per_page: query.data.pages[0]?.per_page ?? 10,
      has_next: query.hasNextPage ?? false,
      has_prev: query.data.pages[0]?.has_prev ?? false,
    } as BookingListResponse)
    : undefined;

  return {
    ...query,
    data,
  };
}

/**
 * Hook to fetch cancelled lessons
 * Uses 15-minute cache as these rarely change
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/bookings endpoint with status=CANCELLED filter
 */
export function useCancelledLessons(page: number = 1) {
  const result = useCancelledBookingsV1(page, 20);

  // Map v1 response to expected shape
  return {
    ...result,
    data: result.data ? {
      items: result.data.items as Booking[],
      total: result.data.total,
      page: result.data.page ?? page,
      per_page: result.data.per_page ?? 20,
      has_next: result.data.has_next,
      has_prev: result.data.has_prev,
    } as BookingListResponse : undefined,
  };
}

/**
 * Hook to fetch a single lesson details
 * Uses 5-minute cache consistent with list
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/bookings/{bookingId} endpoint
 */
export function useLessonDetails(lessonId: string) {
  const result = useBooking(lessonId);

  // Map v1 response to expected Booking type
  return {
    ...result,
    data: result.data as Booking | undefined,
  };
}

/**
 * Hook to cancel a lesson with optimistic update
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/bookings/{bookingId}/cancel endpoint
 */
export function useCancelLesson() {
  const queryClient = useQueryClient();
  const cancelMutation = useCancelBooking();

  return {
    ...cancelMutation,
    mutate: (
      { lessonId, reason }: { lessonId: string; reason: string },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      cancelMutation.mutate(
        { bookingId: lessonId, data: { reason } },
        {
          onSuccess: async () => {
            // Invalidate all booking-related queries
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
            await queryClient.invalidateQueries({ queryKey: ['bookings', 'upcoming'] });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
            await queryClient.invalidateQueries({ queryKey: ['bookings'] });
            await queryClient.invalidateQueries({ queryKey: ['bookings', 'student'] });
            // Invalidate availability — cancelled slot should appear available immediately
            await queryClient.invalidateQueries({ queryKey: queryKeys.availability.all });
            options?.onSuccess?.();
          },
          onError: (error) => {
            options?.onError?.(error as Error);
          },
        }
      );
    },
    mutateAsync: async ({ lessonId, reason }: { lessonId: string; reason: string }) => {
      const result = await cancelMutation.mutateAsync({ bookingId: lessonId, data: { reason } });
      // Invalidate all booking-related queries
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'upcoming'] });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
      await queryClient.invalidateQueries({ queryKey: ['bookings'] });
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'student'] });
      // Invalidate availability — cancelled slot should appear available immediately
      await queryClient.invalidateQueries({ queryKey: queryKeys.availability.all });
      return result;
    },
  };
}

/**
 * Helper function to calculate duration in minutes from start and end times
 */
function parseTimeToMinutes(time: string): number | null {
  const parts = time.split(':');
  if (parts.length < 2) {
    return null;
  }
  const hours = Number(parts[0]);
  const minutes = Number(parts[1]);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return null;
  }
  if (hours < 0 || minutes < 0 || minutes >= 60) {
    return null;
  }
  return hours * 60 + minutes;
}

function calculateDurationMinutes(
  startTime: string | null | undefined,
  endTime: string | null | undefined,
): number {
  if (!startTime || !endTime) {
    return 0;
  }
  const startTotalMinutes = parseTimeToMinutes(startTime);
  const endTotalMinutes = parseTimeToMinutes(endTime);
  if (startTotalMinutes === null || endTotalMinutes === null) {
    return 0;
  }
  const duration = endTotalMinutes - startTotalMinutes;
  return duration > 0 ? duration : 0;
}

/**
 * Hook to reschedule a lesson
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/bookings/{bookingId}/reschedule endpoint
 *
 * Note: The v1 API uses selected_duration instead of end_time.
 * This wrapper calculates duration from times for the reschedule API.
 */
export function useRescheduleLesson() {
  const queryClient = useQueryClient();
  const rescheduleMutation = useRescheduleBooking();

  return {
    ...rescheduleMutation,
    mutate: (
      { lessonId, newDate, newStartTime, newEndTime }: { lessonId: string; newDate: string; newStartTime: string; newEndTime: string },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      const selectedDuration = calculateDurationMinutes(newStartTime, newEndTime);

      rescheduleMutation.mutate(
        {
          bookingId: lessonId,
          data: {
            booking_date: newDate,
            start_time: newStartTime,
            selected_duration: selectedDuration,
          },
        },
        {
          onSuccess: async () => {
            // Invalidate all booking-related queries
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
            await queryClient.invalidateQueries({ queryKey: ['bookings', 'upcoming'] });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
            await queryClient.invalidateQueries({ queryKey: ['bookings'] });
            await queryClient.invalidateQueries({ queryKey: ['bookings', 'student'] });
            options?.onSuccess?.();
          },
          onError: (error) => {
            options?.onError?.(error as Error);
          },
        }
      );
    },
    mutateAsync: async ({ lessonId, newDate, newStartTime, newEndTime }: { lessonId: string; newDate: string; newStartTime: string; newEndTime: string }) => {
      const selectedDuration = calculateDurationMinutes(newStartTime, newEndTime);

      const result = await rescheduleMutation.mutateAsync({
        bookingId: lessonId,
        data: {
          booking_date: newDate,
          start_time: newStartTime,
          selected_duration: selectedDuration,
        },
      });

      // Invalidate all booking-related queries
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'upcoming'] });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
      await queryClient.invalidateQueries({ queryKey: ['bookings'] });
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'student'] });

      return result;
    },
  };
}

/**
 * Hook to complete a lesson (instructor only)
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/bookings/{bookingId}/complete endpoint
 */
export function useCompleteLesson() {
  const queryClient = useQueryClient();
  const completeMutation = useCompleteBooking();

  return {
    ...completeMutation,
    mutate: (
      lessonId: string,
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      completeMutation.mutate(
        { bookingId: lessonId },
        {
          onSuccess: async (data) => {
            // Update cache - invalidate ALL booking-related queries
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming() });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(String(data.id)) });
            await queryClient.invalidateQueries({ queryKey: ['bookings'] });
            await queryClient.invalidateQueries({ queryKey: ['bookings', 'student'] });
            await queryClient.invalidateQueries({ queryKey: ['bookings', 'instructor'] });
            options?.onSuccess?.();
          },
          onError: (error) => {
            options?.onError?.(error as Error);
          },
        }
      );
    },
    mutateAsync: async (lessonId: string) => {
      const result = await completeMutation.mutateAsync({ bookingId: lessonId });
      // Update cache - invalidate ALL booking-related queries
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(String(result.id)) });
      await queryClient.invalidateQueries({ queryKey: ['bookings'] });
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'student'] });
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'instructor'] });
      return result;
    },
  };
}

/**
 * Hook to mark a lesson as no-show (instructor only)
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/bookings/{bookingId}/no-show endpoint
 */
export function useMarkNoShow() {
  const queryClient = useQueryClient();
  const markNoShowMutation = useMarkBookingNoShow();

  return {
    ...markNoShowMutation,
    mutate: (
      lessonId: string,
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      markNoShowMutation.mutate(
        { bookingId: lessonId, data: { no_show_type: 'student' } },
        {
          onSuccess: async () => {
            // Update cache - invalidate ALL booking-related queries
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming() });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(lessonId) });
            await queryClient.invalidateQueries({ queryKey: ['bookings'] });
            await queryClient.invalidateQueries({ queryKey: ['bookings', 'instructor'] });
            options?.onSuccess?.();
          },
          onError: (error: unknown) => {
            options?.onError?.(error as Error);
          },
        }
      );
    },
    mutateAsync: async (lessonId: string) => {
      const result = await markNoShowMutation.mutateAsync({
        bookingId: lessonId,
        data: { no_show_type: 'student' },
      });
      // Update cache - invalidate ALL booking-related queries
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(lessonId) });
      await queryClient.invalidateQueries({ queryKey: ['bookings'] });
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'instructor'] });
      return result;
    },
  };
}

/**
 * Fallback platform fee percentage when payment_summary is not available.
 * Only used for bookings without payment_summary populated.
 * @deprecated Use payment_summary.lesson_amount and payment_summary.service_fee instead
 */
const FALLBACK_PLATFORM_FEE_PERCENT = 0.12;

/**
 * Cancellation fee result with clear policy-aligned naming
 */
export interface CancellationFeeResult {
  /** Hours until the lesson starts */
  hoursUntil: number;
  /** The cancellation window: 'free' (>24h), 'credit' (12-24h), or 'full' (<12h) */
  window: 'free' | 'credit' | 'full';
  /** The lesson price (base price without platform fee) */
  lessonPrice: number;
  /** The platform fee (booking protection fee) */
  platformFee: number;
  /** For 12-24h: credit amount (lesson price). For <12h: charge amount (total) */
  creditAmount: number;
  /** Whether the student will receive a credit (only for 12-24h window) */
  willReceiveCredit: boolean;
}

/**
 * Booking fields required for cancellation fee calculation.
 * Prefers payment_summary when available (accurate), falls back to calculation.
 */
type CancellationFeeInput = Pick<Booking, 'booking_date' | 'start_time' | 'total_price'> & {
  payment_summary?: PaymentSummary | null;
};

/**
 * Calculate cancellation policy outcome based on time until lesson.
 *
 * Policy (per docs-stripe-cancellation-policy.md):
 * - >24h before lesson: Full card refund (including platform fee)
 * - 12-24h before lesson: Platform credit for LESSON PRICE only, fee non-refundable
 * - <12h before lesson: No refund, full charge, instructor paid
 *
 * Uses payment_summary from backend when available (accurate).
 * Falls back to calculation for bookings without payment_summary.
 *
 * @param lesson - Booking with required fields
 * @returns Cancellation policy details
 */
export function calculateCancellationFee(lesson: CancellationFeeInput): CancellationFeeResult {
  const now = new Date();
  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);
  const hoursUntil = (lessonDateTime.getTime() - now.getTime()) / (1000 * 60 * 60);

  // Use payment_summary from backend when available (accurate source of truth)
  // Falls back to calculation only for bookings without payment_summary
  let lessonPrice: number;
  let platformFee: number;

  if (lesson.payment_summary?.lesson_amount != null && lesson.payment_summary?.service_fee != null) {
    // Use backend-provided values (accurate)
    lessonPrice = lesson.payment_summary.lesson_amount;
    platformFee = lesson.payment_summary.service_fee;
  } else {
    // Fallback calculation for bookings without payment_summary
    // total_price = lesson_price + platform_fee
    // platform_fee = lesson_price * 0.12
    // total_price = lesson_price * 1.12
    // lesson_price = total_price / 1.12
    lessonPrice = Math.round((lesson.total_price / (1 + FALLBACK_PLATFORM_FEE_PERCENT)) * 100) / 100;
    platformFee = Math.round((lesson.total_price - lessonPrice) * 100) / 100;
  }

  if (hoursUntil > 24) {
    // >24h: Full refund (no charge, no credit)
    return {
      hoursUntil,
      window: 'free',
      lessonPrice,
      platformFee,
      creditAmount: 0,
      willReceiveCredit: false,
    };
  } else if (hoursUntil > 12) {
    // 12-24h: Credit for lesson price only, fee is non-refundable
    return {
      hoursUntil,
      window: 'credit',
      lessonPrice,
      platformFee,
      creditAmount: lessonPrice,
      willReceiveCredit: true,
    };
  } else {
    // <12h: Full charge, no refund
    return {
      hoursUntil,
      window: 'full',
      lessonPrice,
      platformFee,
      creditAmount: 0,
      willReceiveCredit: false,
    };
  }
}

/**
 * Helper to format lesson status display
 */
export function formatLessonStatus(
  status: BookingStatus,
  lessonDate?: Date | string | null,
  cancelledAt?: string,
): string {
  switch (status) {
    case 'CONFIRMED':
      return 'Upcoming';
    case 'COMPLETED':
      return 'Completed';
    case 'CANCELLED':
      if (cancelledAt && lessonDate) {
        const cancelDate = new Date(cancelledAt);
        const lessonDateValue = lessonDate instanceof Date ? lessonDate : new Date(lessonDate);
        if (Number.isFinite(cancelDate.getTime()) && Number.isFinite(lessonDateValue.getTime())) {
          const hoursBeforeLesson =
            (lessonDateValue.getTime() - cancelDate.getTime()) / (1000 * 60 * 60);

          if (hoursBeforeLesson > 24) {
            return 'Cancelled (>24hrs)';
          } else if (hoursBeforeLesson > 12) {
            return 'Cancelled (12-24hrs)';
          } else {
            return 'Cancelled (<12hrs)';
          }
        }
      }
      return 'Cancelled';
    case 'NO_SHOW':
      return 'No-show';
    default:
      return status;
  }
}
