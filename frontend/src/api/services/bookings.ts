/**
 * Bookings Service Layer
 *
 * Domain-friendly wrappers around Orval-generated bookings v1 hooks.
 * This is the ONLY layer that should directly import from generated/bookings-v1.
 *
 * Components should use these hooks, not the raw Orval-generated ones.
 */

import { queryKeys } from '@/src/api/queryKeys';
import {
  useGetUpcomingBookingsApiV1BookingsUpcomingGet,
  useGetBookingsApiV1BookingsGet,
  useGetBookingDetailsApiV1BookingsBookingIdGet,
  useGetBookingPreviewApiV1BookingsBookingIdPreviewGet,
  useCreateBookingApiV1BookingsPost,
  useCancelBookingApiV1BookingsBookingIdCancelPost,
  useConfirmBookingPaymentApiV1BookingsBookingIdConfirmPaymentPost,
  useCheckAvailabilityApiV1BookingsCheckAvailabilityPost,
  useRescheduleBookingApiV1BookingsBookingIdReschedulePost,
  useCompleteBookingApiV1BookingsBookingIdCompletePost,
  useReportNoShowApiV1BookingsBookingIdNoShowPost,
} from '@/src/api/generated/bookings-v1/bookings-v1';
import type {
  GetBookingsApiV1BookingsGetParams,
  BookingCreate,
  BookingCancel,
  BookingConfirmPayment,
  AvailabilityCheckRequest,
} from '@/src/api/generated/instructly.schemas';

/**
 * Get upcoming bookings for dashboard widget.
 *
 * Returns a limited number of upcoming confirmed bookings.
 *
 * @param limit - Maximum number of bookings to return (1-20)
 * @param options - Optional query configuration (e.g., enabled)
 * @example
 * ```tsx
 * function UpcomingBookingsWidget() {
 *   const { data, isLoading } = useUpcomingBookings(5);
 *
 *   if (isLoading) return <div>Loading...</div>;
 *
 *   return <div>{data?.items.length} upcoming bookings</div>;
 * }
 * ```
 */
export function useUpcomingBookings(
  limit: number = 5,
  options?: { enabled?: boolean }
) {
  return useGetUpcomingBookingsApiV1BookingsUpcomingGet(
    { limit },
    {
      query: {
        queryKey: queryKeys.bookings.student({ status: 'upcoming', limit }),
        staleTime: 1000 * 60 * 5, // 5 minutes
        // Only include enabled when explicitly set (exactOptionalPropertyTypes compliance)
        ...(options?.enabled !== undefined && { enabled: options.enabled }),
      },
    }
  );
}

/**
 * List bookings with optional filters.
 *
 * @param params - Filter parameters
 * @example
 * ```tsx
 * function BookingsList() {
 *   const { data, isLoading } = useBookingsList({
 *     status: 'CONFIRMED',
 *     page: 1,
 *     per_page: 20
 *   });
 *
 *   if (isLoading) return <div>Loading...</div>;
 *
 *   return <div>{data?.items.length} bookings</div>;
 * }
 * ```
 */
export function useBookingsList(params?: GetBookingsApiV1BookingsGetParams) {
  // Build query params that satisfy exactOptionalPropertyTypes
  const queryParams: {
    status?: string;
    page?: number;
    per_page?: number;
    upcoming_only?: boolean;
    exclude_future_confirmed?: boolean;
  } = {};

  if (params?.status !== undefined && params.status !== null) {
    queryParams.status = params.status.toString();
  }
  if (params?.page !== undefined) {
    queryParams.page = params.page;
  }
  if (params?.per_page !== undefined) {
    queryParams.per_page = params.per_page;
  }
  if (params?.upcoming_only !== undefined && params.upcoming_only !== null) {
    queryParams.upcoming_only = params.upcoming_only;
  }
  if (params?.exclude_future_confirmed !== undefined && params.exclude_future_confirmed !== null) {
    queryParams.exclude_future_confirmed = params.exclude_future_confirmed;
  }

  return useGetBookingsApiV1BookingsGet(params, {
    query: {
      queryKey: queryKeys.bookings.student(
        Object.keys(queryParams).length ? queryParams : undefined
      ),
      staleTime: 1000 * 60 * 5, // 5 minutes
    },
  });
}

/**
 * Get full booking details by ID.
 *
 * @param bookingId - ULID of the booking
 * @example
 * ```tsx
 * function BookingDetails({ bookingId }: { bookingId: string }) {
 *   const { data: booking, isLoading } = useBooking(bookingId);
 *
 *   if (isLoading) return <div>Loading...</div>;
 *   if (!booking) return <div>Booking not found</div>;
 *
 *   return <div>{booking.service_name}</div>;
 * }
 * ```
 */
export function useBooking(bookingId: string) {
  return useGetBookingDetailsApiV1BookingsBookingIdGet(bookingId, {
    query: {
      queryKey: queryKeys.bookings.detail(bookingId),
      staleTime: 1000 * 60 * 5, // 5 minutes
    },
  });
}

/**
 * Get booking preview by ID (lightweight, for calendar display).
 *
 * @param bookingId - ULID of the booking
 * @example
 * ```tsx
 * function BookingPreview({ bookingId }: { bookingId: string }) {
 *   const { data: preview } = useBookingPreview(bookingId);
 *
 *   if (!preview) return null;
 *
 *   return <div>{preview.service_name} on {preview.booking_date}</div>;
 * }
 * ```
 */
export function useBookingPreview(bookingId: string) {
  return useGetBookingPreviewApiV1BookingsBookingIdPreviewGet(bookingId, {
    query: {
      queryKey: queryKeys.bookings.detail(bookingId),
      staleTime: 1000 * 60 * 5, // 5 minutes
    },
  });
}

/**
 * Create booking mutation.
 *
 * @example
 * ```tsx
 * function CreateBookingForm() {
 *   const createBooking = useCreateBooking();
 *
 *   const handleSubmit = async (data: BookingCreate) => {
 *     const result = await createBooking.mutateAsync({ data });
 *     // Handle setup_intent_client_secret for payment
 *   };
 *
 *   return <form onSubmit={handleSubmit}>...</form>;
 * }
 * ```
 */
export function useCreateBooking() {
  return useCreateBookingApiV1BookingsPost();
}

/**
 * Cancel booking mutation.
 *
 * @example
 * ```tsx
 * function CancelBookingButton({ bookingId }: { bookingId: string }) {
 *   const cancelBooking = useCancelBooking();
 *
 *   const handleCancel = async () => {
 *     await cancelBooking.mutateAsync({
 *       bookingId,
 *       data: { reason: 'Schedule conflict' }
 *     });
 *   };
 *
 *   return <button onClick={handleCancel}>Cancel Booking</button>;
 * }
 * ```
 */
export function useCancelBooking() {
  return useCancelBookingApiV1BookingsBookingIdCancelPost();
}

/**
 * Confirm payment for booking mutation.
 *
 * @example
 * ```tsx
 * function ConfirmPaymentButton({ bookingId, paymentMethodId }: Props) {
 *   const confirmPayment = useConfirmBookingPayment();
 *
 *   const handleConfirm = async () => {
 *     await confirmPayment.mutateAsync({
 *       bookingId,
 *       data: { payment_method_id: paymentMethodId, save_payment_method: true }
 *     });
 *   };
 *
 *   return <button onClick={handleConfirm}>Confirm Payment</button>;
 * }
 * ```
 */
export function useConfirmBookingPayment() {
  return useConfirmBookingPaymentApiV1BookingsBookingIdConfirmPaymentPost();
}

/**
 * Check availability mutation.
 *
 * @example
 * ```tsx
 * function AvailabilityChecker() {
 *   const checkAvailability = useCheckAvailability();
 *
 *   const handleCheck = async (data: AvailabilityCheckRequest) => {
 *     const result = await checkAvailability.mutateAsync({ data });
 *     if (result.available) {
 *       // Proceed with booking
 *     }
 *   };
 *
 *   return <form onSubmit={handleCheck}>...</form>;
 * }
 * ```
 */
export function useCheckAvailability() {
  return useCheckAvailabilityApiV1BookingsCheckAvailabilityPost();
}

/**
 * Get booking history (completed, cancelled, past lessons).
 *
 * Uses exclude_future_confirmed to filter out upcoming confirmed bookings.
 *
 * @param page - Page number (1-based)
 * @param perPage - Items per page
 * @example
 * ```tsx
 * function BookingHistory() {
 *   const { data, isLoading } = useBookingsHistory(1, 50);
 *
 *   if (isLoading) return <div>Loading...</div>;
 *
 *   return <div>{data?.items.length} past bookings</div>;
 * }
 * ```
 */
export function useBookingsHistory(page: number = 1, perPage: number = 50) {
  return useGetBookingsApiV1BookingsGet(
    {
      exclude_future_confirmed: true,
      page,
      per_page: perPage,
    },
    {
      query: {
        queryKey: queryKeys.bookings.student({
          status: 'history',
          exclude_future_confirmed: true,
          page,
          per_page: perPage,
        }),
        staleTime: 1000 * 60 * 15, // 15 minutes for history
      },
    }
  );
}

/**
 * Get cancelled bookings only.
 *
 * @param page - Page number (1-based)
 * @param perPage - Items per page
 * @example
 * ```tsx
 * function CancelledBookings() {
 *   const { data, isLoading } = useCancelledBookings(1, 20);
 *
 *   if (isLoading) return <div>Loading...</div>;
 *
 *   return <div>{data?.items.length} cancelled bookings</div>;
 * }
 * ```
 */
export function useCancelledBookings(page: number = 1, perPage: number = 20) {
  return useGetBookingsApiV1BookingsGet(
    {
      status: 'CANCELLED',
      upcoming_only: false,
      page,
      per_page: perPage,
    },
    {
      query: {
        queryKey: queryKeys.bookings.student({
          status: 'CANCELLED',
          upcoming_only: false,
          page,
          per_page: perPage,
        }),
        staleTime: 1000 * 60 * 15, // 15 minutes for cancelled
      },
    }
  );
}

/**
 * Reschedule booking mutation.
 *
 * @example
 * ```tsx
 * function RescheduleButton({ bookingId }: { bookingId: string }) {
 *   const rescheduleBooking = useRescheduleBooking();
 *
 *   const handleReschedule = async () => {
 *     await rescheduleBooking.mutateAsync({
 *       bookingId,
 *       data: {
 *         booking_date: '2025-01-15',
 *         start_time: '10:00:00',
 *         selected_duration: 60
 *       }
 *     });
 *   };
 *
 *   return <button onClick={handleReschedule}>Reschedule</button>;
 * }
 * ```
 */
export function useRescheduleBooking() {
  return useRescheduleBookingApiV1BookingsBookingIdReschedulePost();
}

/**
 * Complete booking mutation (instructor only).
 *
 * @example
 * ```tsx
 * function CompleteButton({ bookingId }: { bookingId: string }) {
 *   const completeBooking = useCompleteBooking();
 *
 *   const handleComplete = async () => {
 *     await completeBooking.mutateAsync({ bookingId });
 *   };
 *
 *   return <button onClick={handleComplete}>Mark Complete</button>;
 * }
 * ```
 */
export function useCompleteBooking() {
  return useCompleteBookingApiV1BookingsBookingIdCompletePost();
}

/**
 * Report booking no-show mutation.
 *
 * Reports a booking no-show with the required no_show_type payload.
 *
 * @example
 * ```tsx
 * function NoShowButton({ bookingId }: { bookingId: string }) {
 *   const markNoShow = useMarkBookingNoShow();
 *
 *   const handleNoShow = async () => {
 *     await markNoShow.mutateAsync({
 *       bookingId,
 *       data: { no_show_type: 'student' }
 *     });
 *   };
 *
 *   return <button onClick={handleNoShow}>Mark No-Show</button>;
 * }
 * ```
 */
export function useMarkBookingNoShow() {
  return useReportNoShowApiV1BookingsBookingIdNoShowPost();
}

/**
 * Imperative API functions for use in useEffect or other non-hook contexts.
 *
 * Use these when you need to call the API directly without React Query hooks.
 */

/**
 * Fetch bookings list imperatively.
 *
 * @example
 * ```tsx
 * const data = await fetchBookingsList({ upcoming_only: true, per_page: 25 });
 * setBookings(data.items);
 * ```
 */
export { getBookingsApiV1BookingsGet as fetchBookingsList } from '@/src/api/generated/bookings-v1/bookings-v1';

/**
 * Fetch single booking details imperatively.
 *
 * @example
 * ```tsx
 * const booking = await fetchBookingDetails('01ABC...');
 * ```
 */
export { getBookingDetailsApiV1BookingsBookingIdGet as fetchBookingDetails } from '@/src/api/generated/bookings-v1/bookings-v1';

/**
 * Create a new booking imperatively.
 *
 * @example
 * ```tsx
 * const booking = await createBookingImperative({
 *   instructor_id: 'abc',
 *   instructor_service_id: 'def',
 *   booking_date: '2025-01-01',
 *   start_time: '10:00',
 *   selected_duration: 60
 * });
 * ```
 */
export { createBookingApiV1BookingsPost as createBookingImperative } from '@/src/api/generated/bookings-v1/bookings-v1';

/**
 * Cancel a booking imperatively.
 *
 * @example
 * ```tsx
 * await cancelBookingImperative('01ABC...', { reason: 'Schedule conflict' });
 * ```
 */
export { cancelBookingApiV1BookingsBookingIdCancelPost as cancelBookingImperative } from '@/src/api/generated/bookings-v1/bookings-v1';

/**
 * Reschedule a booking imperatively.
 *
 * @example
 * ```tsx
 * const rescheduled = await rescheduleBookingImperative('01ABC...', {
 *   booking_date: '2025-01-15',
 *   start_time: '10:00',
 *   selected_duration: 60
 * });
 * ```
 */
export { rescheduleBookingApiV1BookingsBookingIdReschedulePost as rescheduleBookingImperative } from '@/src/api/generated/bookings-v1/bookings-v1';

/**
 * Mark a booking as no-show imperatively.
 *
 * @example
 * ```tsx
 * await markBookingNoShowImperative('01ABC...', { no_show_type: 'student' });
 * ```
 */
export { reportNoShowApiV1BookingsBookingIdNoShowPost as markBookingNoShowImperative } from '@/src/api/generated/bookings-v1/bookings-v1';

/**
 * Type exports for convenience
 */
export type {
  BookingCreate,
  BookingCancel,
  BookingConfirmPayment,
  AvailabilityCheckRequest,
  GetBookingsApiV1BookingsGetParams as BookingsListParams,
};
