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
export function useUpcomingBookings(limit: number = 5) {
  return useGetUpcomingBookingsApiV1BookingsUpcomingGet(
    { limit },
    {
      query: {
        queryKey: queryKeys.bookings.student({ status: 'upcoming' }),
        staleTime: 1000 * 60 * 5, // 5 minutes
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
  const queryParams =
    params?.status !== undefined && params.status !== null
      ? { status: params.status.toString() }
      : undefined;

  return useGetBookingsApiV1BookingsGet(params, {
    query: {
      queryKey: queryKeys.bookings.student(queryParams),
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
 * Type exports for convenience
 */
export type {
  BookingCreate,
  BookingCancel,
  BookingConfirmPayment,
  AvailabilityCheckRequest,
  GetBookingsApiV1BookingsGetParams as BookingsListParams,
};
