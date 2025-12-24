import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/react-query/queryClient';
import type {
  BookingListResponse,
  Booking,
  BookingStatus,
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
} from '@/src/api/services/bookings';

/**
 * Hook to fetch current/upcoming lessons
 * Only shows CONFIRMED lessons that are in the future
 * Uses 5-minute cache as these may change with new bookings
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/bookings endpoint with upcoming_only filter
 *
 * @param _enabled - Legacy parameter kept for backward compatibility but not used (v1 hooks don't support enabled)
 */
export function useCurrentLessons(_enabled: boolean = true) {
  // Use v1 service with upcoming_only filter to get full booking objects
  const result = useBookingsList({
    upcoming_only: true,
    per_page: 20,
  });

  // Map v1 response shape to legacy shape for backward compatibility
  return {
    ...result,
    data: result.data ? {
      items: result.data.items as Booking[],
      total: result.data.total,
      page: result.data.page ?? 1,
      per_page: result.data.per_page ?? 20,
      has_next: result.data.has_next,
      has_prev: result.data.has_prev,
    } as BookingListResponse : undefined,
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
 * @param _enabled - Legacy parameter kept for backward compatibility but not used
 */
export function useCompletedLessons(page: number = 1, _enabled: boolean = true) {
  const result = useBookingsHistory(page, 50);

  // Map v1 response shape to legacy shape for backward compatibility
  return {
    ...result,
    data: result.data ? {
      items: result.data.items as Booking[],
      total: result.data.total,
      page: result.data.page ?? 1,
      per_page: result.data.per_page ?? 50,
      has_next: result.data.has_next,
      has_prev: result.data.has_prev,
    } as BookingListResponse : undefined,
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

  // Map v1 response shape to legacy shape for backward compatibility
  return {
    ...result,
    data: result.data ? {
      items: result.data.items as Booking[],
      total: result.data.total,
      page: result.data.page ?? 1,
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

  // Map v1 response to legacy Booking type for backward compatibility
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
      return result as Booking;
    },
  };
}

/**
 * Helper function to calculate duration in minutes from start and end times
 */
function calculateDurationMinutes(startTime: string, endTime: string): number {
  const [startHours, startMinutes] = startTime.split(':').map(Number);
  const [endHours, endMinutes] = endTime.split(':').map(Number);

  const startTotalMinutes = (startHours ?? 0) * 60 + (startMinutes ?? 0);
  const endTotalMinutes = (endHours ?? 0) * 60 + (endMinutes ?? 0);

  return endTotalMinutes - startTotalMinutes;
}

/**
 * Hook to reschedule a lesson
 *
 * ✅ MIGRATED TO V1 - Uses /api/v1/bookings/{bookingId}/reschedule endpoint
 *
 * Note: The v1 API uses selected_duration instead of end_time.
 * This wrapper maintains backward compatibility by calculating duration from times.
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

      return result as Booking;
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
      return result as Booking;
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
        { bookingId: lessonId },
        {
          onSuccess: async (data) => {
            // Update cache - invalidate ALL booking-related queries
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming() });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
            await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(String(data.id)) });
            await queryClient.invalidateQueries({ queryKey: ['bookings'] });
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
      const result = await markNoShowMutation.mutateAsync({ bookingId: lessonId });
      // Update cache - invalidate ALL booking-related queries
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.all });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.upcoming() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.history() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(String(result.id)) });
      await queryClient.invalidateQueries({ queryKey: ['bookings'] });
      await queryClient.invalidateQueries({ queryKey: ['bookings', 'instructor'] });
      return result as Booking;
    },
  };
}

/**
 * Platform fee percentage (student booking protection fee)
 */
const PLATFORM_FEE_PERCENT = 0.12;

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
 * Calculate cancellation policy outcome based on time until lesson.
 *
 * Policy (per docs-stripe-cancellation-policy.md):
 * - >24h before lesson: Full card refund (including platform fee)
 * - 12-24h before lesson: Platform credit for LESSON PRICE only, fee non-refundable
 * - <12h before lesson: No refund, full charge, instructor paid
 *
 * @param lesson - Booking with required fields
 * @returns Cancellation policy details
 */
export function calculateCancellationFee<
  T extends Pick<Booking, 'booking_date' | 'start_time' | 'total_price'>
>(lesson: T): CancellationFeeResult {
  const now = new Date();
  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);
  const hoursUntil = (lessonDateTime.getTime() - now.getTime()) / (1000 * 60 * 60);

  // Calculate lesson price and platform fee from total_price
  // total_price = lesson_price + platform_fee
  // platform_fee = lesson_price * 0.12
  // total_price = lesson_price * 1.12
  // lesson_price = total_price / 1.12
  const lessonPrice = Math.round((lesson.total_price / (1 + PLATFORM_FEE_PERCENT)) * 100) / 100;
  const platformFee = Math.round((lesson.total_price - lessonPrice) * 100) / 100;

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
