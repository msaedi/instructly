// frontend/lib/api/bookings.ts
import { fetchWithAuth } from '../api';
import { logger } from '../logger';
import {
  Booking,
  BookingListResponse,
  AvailabilityCheckResponse,
  BookingPreview,
  BookingCreate,
  AvailabilityCheckRequest,
} from '@/types/booking';

// Generated types shim is available if needed in future; not required here currently

/**
 * Bookings API Client
 *
 * Updated for time-based booking system without slot IDs.
 * All booking operations now use instructor_id + date + time range.
 *
 * @module bookingsApi
 */

/**
 * Filters for querying bookings
 */
export interface BookingFilters {
  /** Filter by booking status */
  status?: 'CONFIRMED' | 'COMPLETED' | 'CANCELLED' | 'NO_SHOW';
  /** Filter for upcoming bookings only */
  upcoming?: boolean; // This will be converted to upcoming_only in the API call
  /** Exclude future confirmed bookings (for History tab) */
  exclude_future_confirmed?: boolean;
  /** Include past confirmed bookings (for BookAgain) */
  include_past_confirmed?: boolean;
  /** Page number for pagination */
  page?: number;
  /** Number of items per page */
  per_page?: number;
}

/**
 * Request payload for cancelling a booking
 */
export interface CancelBookingRequest {
  /** Reason for cancellation */
  cancellation_reason: string;
}

/**
 * Response for booking statistics
 */
export interface BookingStatsResponse {
  /** Total number of bookings */
  total_bookings: number;
  /** Number of completed bookings */
  completed_bookings: number;
  /** Number of cancelled bookings */
  cancelled_bookings: number;
  /** Number of no-show bookings */
  no_show_bookings: number;
  /** Total earnings */
  total_earnings: number;
  /** This month's bookings */
  monthly_bookings: number;
  /** This week's bookings */
  weekly_bookings: number;
}

/**
 * Main bookings API interface
 *
 * Provides methods for all booking-related operations
 */
export const bookingsApi = {
  /**
   * Check if a time range is available before booking
   *
   * @param data - Availability check request data with time range
   * @returns Promise with availability status
   * @throws Error if the check fails
   *
   * @example
   * ```ts
   * const isAvailable = await bookingsApi.checkAvailability({
   *   instructor_id: 123,
   *   service_id: 456,
   *   booking_date: "2025-07-15",
   *   start_time: "09:00",
   *   end_time: "10:00"
   * });
   * ```
   */
  checkAvailability: async (data: AvailabilityCheckRequest): Promise<AvailabilityCheckResponse> => {
    logger.info('Checking time range availability', {
      instructorId: data.instructor_id,
      serviceId: data.service_id,
      date: data.booking_date,
      startTime: data.start_time,
      endTime: data.end_time,
    });

    const response = await fetchWithAuth('/bookings/check-availability', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      logger.error('Availability check failed', undefined, {
        instructorId: data.instructor_id,
        date: data.booking_date,
        error,
      });
      throw new Error(error.detail || 'Failed to check availability');
    }

    const result = await response.json();
    logger.debug('Availability check successful', {
      instructorId: data.instructor_id,
      available: result.available,
      reason: result.reason,
    });
    return result;
  },

  /**
   * Create an instant booking with time-based information
   *
   * @param data - Booking creation request data with time range
   * @returns Promise with the created booking
   * @throws Error if booking creation fails
   *
   * @example
   * ```ts
   * const booking = await bookingsApi.createBooking({
   *   instructor_id: 123,
   *   service_id: 456,
   *   booking_date: "2025-07-15",
   *   start_time: "09:00",
   *   end_time: "10:00",
   *   student_note: 'First time student'
   * });
   * ```
   */
  createBooking: async (data: BookingCreate): Promise<Booking> => {
    logger.info('Creating time-based booking', {
      instructorId: data.instructor_id,
      serviceId: data.service_id,
      date: data.booking_date,
      startTime: data.start_time,
      endTime: data.end_time,
      hasNotes: !!data.student_note,
    });

    const response = await fetchWithAuth('/bookings/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      logger.error('Booking creation failed', undefined, {
        instructorId: data.instructor_id,
        date: data.booking_date,
        time: `${data.start_time}-${data.end_time}`,
        error,
      });
      throw new Error(error.detail || 'Failed to create booking');
    }

    const booking = await response.json();
    logger.info('Booking created successfully', {
      bookingId: booking.id,
      status: booking.status,
      date: booking.booking_date,
      time: `${booking.start_time}-${booking.end_time}`,
    });
    return booking;
  },

  /**
   * Get current user's bookings (student or instructor)
   *
   * @param filters - Optional filters for the query
   * @returns Promise with paginated booking list
   * @throws Error if fetching fails
   *
   * @example
   * ```ts
   * const bookings = await bookingsApi.getMyBookings({
   *   status: 'CONFIRMED',
   *   upcoming: true,
   *   page: 1,
   *   per_page: 20
   * });
   * ```
   */
  getMyBookings: async (filters?: BookingFilters): Promise<BookingListResponse> => {
    logger.debug('Fetching user bookings', { filters });

    const params = new URLSearchParams();
    if (filters?.status) params.append('status', filters.status);
    if (filters?.upcoming !== undefined) params.append('upcoming', filters.upcoming.toString());
    if (filters?.exclude_future_confirmed !== undefined)
      params.append('exclude_future_confirmed', filters.exclude_future_confirmed.toString());
    if (filters?.include_past_confirmed !== undefined)
      params.append('include_past_confirmed', filters.include_past_confirmed.toString());
    if (filters?.page) params.append('page', filters.page.toString());
    if (filters?.per_page) params.append('per_page', filters.per_page.toString());

    const response = await fetchWithAuth(`/bookings/?${params.toString()}`);
    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to fetch bookings', undefined, { filters, error });
      throw new Error(error.detail || 'Failed to fetch bookings');
    }

    const result = await response.json();
    logger.debug('Bookings fetched successfully', {
      count: result.items.length,
      total: result.total,
    });
    return result;
  },

  /**
   * Get a specific booking by ID
   *
   * @param bookingId - ID of the booking to fetch
   * @returns Promise with booking details
   * @throws Error if booking not found or fetch fails
   *
   * @example
   * ```ts
   * const booking = await bookingsApi.getBooking(123);
   * ```
   */
  getBooking: async (bookingId: string): Promise<Booking> => {
    logger.debug('Fetching booking details', { bookingId });

    const response = await fetchWithAuth(`/bookings/${bookingId}`);
    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to fetch booking', undefined, { bookingId, error });
      throw new Error(error.detail || 'Failed to fetch booking');
    }

    const booking = await response.json();
    logger.debug('Booking fetched successfully', {
      bookingId,
      status: booking.status,
    });
    return booking;
  },

  /**
   * Get booking preview (lightweight version)
   *
   * @param bookingId - ID of the booking to preview
   * @returns Promise with booking preview
   * @throws Error if booking not found or fetch fails
   *
   * @example
   * ```ts
   * const preview = await bookingsApi.getBookingPreview(123);
   * ```
   */
  getBookingPreview: async (bookingId: string): Promise<BookingPreview> => {
    logger.debug('Fetching booking preview', { bookingId });

    const response = await fetchWithAuth(`/bookings/${bookingId}/preview`);
    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to fetch booking preview', undefined, { bookingId, error });
      throw new Error(error.detail || 'Failed to fetch booking preview');
    }

    const preview = await response.json();
    logger.debug('Booking preview fetched successfully', {
      bookingId,
      hasStudentInfo: !!(preview.student_first_name && preview.student_last_name),
    });
    return preview;
  },

  /**
   * Cancel a booking (student or instructor)
   *
   * @param bookingId - ID of the booking to cancel
   * @param data - Cancellation request with reason
   * @returns Promise with updated booking
   * @throws Error if cancellation fails
   *
   * @example
   * ```ts
   * const cancelledBooking = await bookingsApi.cancelBooking(123, {
   *   cancellation_reason: 'Schedule conflict'
   * });
   * ```
   */
  cancelBooking: async (bookingId: string, data: CancelBookingRequest): Promise<Booking> => {
    logger.info('Cancelling booking', {
      bookingId,
      hasReason: !!data.cancellation_reason,
    });

    const response = await fetchWithAuth(`/bookings/${bookingId}/cancel`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        reason: data.cancellation_reason, // Map cancellation_reason to reason
      }),
    });

    if (!response.ok) {
      let errorDetail = 'Failed to cancel booking';
      try {
        const error = await response.json();

        if (error.detail) {
          if (typeof error.detail === 'string') {
            errorDetail = error.detail;
          } else if (Array.isArray(error.detail)) {
            errorDetail = error.detail
              .map((e: { loc: string[]; msg: string }) => `${e.loc.join(' > ')}: ${e.msg}`)
              .join(', ');
          }
        }
      } catch {
        logger.debug('Failed to parse error response');
      }

      logger.error('Booking cancellation failed', undefined, {
        bookingId,
        errorDetail,
      });
      throw new Error(errorDetail);
    }

    const result = await response.json();
    logger.info('Booking cancelled successfully', { bookingId });
    return result;
  },

  /**
   * Mark a booking as complete (instructor only)
   *
   * @param bookingId - ID of the booking to complete
   * @returns Promise with updated booking
   * @throws Error if completion fails
   *
   * @example
   * ```ts
   * const completedBooking = await bookingsApi.completeBooking(123);
   * ```
   */
  completeBooking: async (bookingId: string): Promise<Booking> => {
    logger.info('Marking booking as complete', { bookingId });

    const response = await fetchWithAuth(`/bookings/${bookingId}/complete`, {
      method: 'POST',
    });

    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to complete booking', undefined, { bookingId, error });
      throw new Error(error.detail || 'Failed to complete booking');
    }

    const result = await response.json();
    logger.info('Booking marked as complete', { bookingId });
    return result;
  },

  /**
   * Mark a booking as no-show (instructor only)
   *
   * @param bookingId - ID of the booking to mark as no-show
   * @returns Promise with updated booking
   * @throws Error if marking fails
   *
   * @example
   * ```ts
   * const noShowBooking = await bookingsApi.markNoShow(123);
   * ```
   */
  markNoShow: async (bookingId: string): Promise<Booking> => {
    logger.info('Marking booking as no-show', { bookingId });

    const response = await fetchWithAuth(`/bookings/${bookingId}/no-show`, {
      method: 'POST',
    });

    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to mark as no-show', undefined, { bookingId, error });
      throw new Error(error.detail || 'Failed to mark as no-show');
    }

    const result = await response.json();
    logger.info('Booking marked as no-show', { bookingId });
    return result;
  },

  /**
   * Get booking statistics (instructor only)
   *
   * @returns Promise with booking statistics
   * @throws Error if fetching stats fails
   *
   * @example
   * ```ts
   * const stats = await bookingsApi.getBookingStats();
   * Example: Total bookings: ${stats.total_bookings}
   * ```
   */
  getBookingStats: async (): Promise<BookingStatsResponse> => {
    logger.debug('Fetching booking statistics');

    const response = await fetchWithAuth('/bookings/stats');
    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to fetch booking stats', undefined, { error });
      throw new Error(error.detail || 'Failed to fetch booking stats');
    }

    const stats = await response.json();
    logger.debug('Booking stats fetched', {
      totalBookings: stats.total_bookings,
      completedBookings: stats.completed_bookings,
    });
    return stats;
  },

  /**
   * Get upcoming bookings with limit
   *
   * @param limit - Maximum number of bookings to return (default: 5)
   * @returns Promise with upcoming bookings
   * @throws Error if fetching fails
   *
   * @example
   * ```ts
   * const upcomingBookings = await bookingsApi.getUpcomingBookings(10);
   * ```
   */
  getUpcomingBookings: async (limit: number = 5): Promise<Booking[]> => {
    logger.debug('Fetching upcoming bookings', { limit });

    const response = await fetchWithAuth(`/bookings/upcoming?limit=${limit}`);
    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to fetch upcoming bookings', undefined, { limit, error });
      throw new Error(error.detail || 'Failed to fetch upcoming bookings');
    }

    const data = await response.json();
    logger.debug('Upcoming bookings fetched', {
      count: data.items.length,
      total: data.total,
      requestedLimit: limit,
    });
    // API is standardized - always uses items
    return data.items;
  },

  /**
   * Reschedule a booking to a new time
   *
   * @param bookingId - ID of the booking to reschedule
   * @param data - New date and time information
   * @returns Promise with updated booking
   * @throws Error if rescheduling fails
   *
   * @example
   * ```ts
   * const rescheduledBooking = await bookingsApi.rescheduleBooking(123, {
   *   booking_date: '2025-07-16',
   *   start_time: '10:00',
   *   end_time: '11:00'
   * });
   * ```
   */
  rescheduleBooking: async (
    bookingId: string,
    data: {
      booking_date: string;
      start_time: string;
      end_time: string;
    }
  ): Promise<Booking> => {
    logger.info('Rescheduling booking', {
      bookingId,
      newDate: data.booking_date,
      newTime: `${data.start_time}-${data.end_time}`,
    });

    const response = await fetchWithAuth(`/bookings/${bookingId}/reschedule`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to reschedule booking', undefined, { bookingId, error });
      throw new Error(error.detail || 'Failed to reschedule booking');
    }

    const result = await response.json();
    logger.info('Booking rescheduled successfully', {
      bookingId,
      newDate: result.booking_date,
      newTime: `${result.start_time}-${result.end_time}`,
    });
    return result;
  },
};

/**
 * Availability API interface
 *
 * Additional availability-related API calls for checking instructor schedules
 */
export const availabilityApi = {
  /**
   * Get instructor's availability for a date range
   *
   * @param instructorId - ID of the instructor
   * @param startDate - Start date (ISO format: YYYY-MM-DD)
   * @param endDate - End date (ISO format: YYYY-MM-DD)
   * @returns Promise with availability data
   * @throws Error if fetching fails
   *
   * @example
   * ```ts
   * const availability = await availabilityApi.getInstructorAvailability(
   *   123,
   *   '2025-06-15',
   *   '2025-06-21'
   * );
   * ```
   */
  getInstructorAvailability: async (instructorId: string, startDate: string, endDate: string) => {
    logger.debug('Fetching instructor availability', {
      instructorId,
      startDate,
      endDate,
    });

    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
    });

    const response = await fetchWithAuth(
      `/availability/instructor/${instructorId}?${params.toString()}`
    );
    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to fetch availability', undefined, {
        instructorId,
        dateRange: { startDate, endDate },
        error,
      });
      throw new Error(error.detail || 'Failed to fetch availability');
    }

    const availability = await response.json();
    logger.debug('Availability fetched', {
      instructorId,
      slotsCount: availability.slots.length,
    });
    return availability;
  },

  /**
   * Get available slots for a specific date
   *
   * @param instructorId - ID of the instructor
   * @param date - Date to check (ISO format: YYYY-MM-DD)
   * @param serviceId - Optional service ID to filter by duration
   * @returns Promise with available slots
   * @throws Error if fetching fails
   *
   * @example
   * ```ts
   * const slots = await availabilityApi.getAvailableSlots(
   *   123,
   *   '2025-06-15',
   *   456 // optional service ID
   * );
   * ```
   */
  getAvailableSlots: async (instructorId: string, date: string, serviceId?: string) => {
    logger.debug('Fetching available slots', {
      instructorId,
      date,
      serviceId,
    });

    const params = new URLSearchParams({ date });
    if (serviceId) params.append('service_id', serviceId.toString());

    const response = await fetchWithAuth(
      `/availability/instructor/${instructorId}/slots?${params.toString()}`
    );
    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to fetch available slots', undefined, {
        instructorId,
        date,
        serviceId,
        error,
      });
      throw new Error(error.detail || 'Failed to fetch available slots');
    }

    const slots = await response.json();
    logger.debug('Available slots fetched', {
      instructorId,
      date,
      totalCount: slots.length,
    });
    return slots;
  },
};
