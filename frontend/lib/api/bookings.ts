// frontend/lib/api/bookings.ts
import { fetchWithAuth } from '../api';
import { logger } from '../logger';

/**
 * Bookings API Client
 * 
 * This module provides a centralized interface for all booking-related API calls,
 * including creating bookings, checking availability, managing booking lifecycle,
 * and fetching booking statistics.
 * 
 * @module bookingsApi
 */

/**
 * Request payload for creating a new booking
 */
export interface BookingCreateRequest {
  /** ID of the instructor to book */
  instructor_id: number;
  /** ID of the service being booked */
  service_id: number;
  /** ID of the availability slot to book */
  availability_slot_id: number;
  /** Optional notes from the student */
  notes?: string;
}

/**
 * Filters for querying bookings
 */
export interface BookingFilters {
  /** Filter by booking status */
  status?: 'CONFIRMED' | 'COMPLETED' | 'CANCELLED' | 'NO_SHOW';
  /** Filter for upcoming bookings only */
  upcoming?: boolean;  // This will be converted to upcoming_only in the API call
  /** Page number for pagination */
  page?: number;
  /** Number of items per page */
  per_page?: number;
}

/**
 * Request payload for checking slot availability
 */
export interface AvailabilityCheckRequest {
  /** ID of the availability slot to check */
  availability_slot_id: number;
  /** ID of the service to check against */
  service_id: number;
}

/**
 * Request payload for cancelling a booking
 */
export interface CancelBookingRequest {
  /** Reason for cancellation */
  cancellation_reason: string;
}

/**
 * Main bookings API interface
 * 
 * Provides methods for all booking-related operations
 */
export const bookingsApi = {
  /**
   * Check if a slot is available before booking
   * 
   * @param data - Availability check request data
   * @returns Promise with availability status
   * @throws Error if the check fails
   * 
   * @example
   * ```ts
   * const isAvailable = await bookingsApi.checkAvailability({
   *   availability_slot_id: 123,
   *   service_id: 456
   * });
   * ```
   */
  checkAvailability: async (data: AvailabilityCheckRequest) => {
    logger.info('Checking slot availability', {
      slotId: data.availability_slot_id,
      serviceId: data.service_id
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
        slotId: data.availability_slot_id,
        error 
      });
      throw new Error(error.detail || 'Failed to check availability');
    }
    
    const result = await response.json();
    logger.debug('Availability check successful', { 
      slotId: data.availability_slot_id,
      available: result.available 
    });
    return result;
  },

  /**
   * Create an instant booking
   * 
   * @param data - Booking creation request data
   * @returns Promise with the created booking
   * @throws Error if booking creation fails
   * 
   * @example
   * ```ts
   * const booking = await bookingsApi.createBooking({
   *   instructor_id: 123,
   *   service_id: 456,
   *   availability_slot_id: 789,
   *   notes: 'First time student'
   * });
   * ```
   */
  createBooking: async (data: BookingCreateRequest) => {
    logger.info('Creating booking', {
      instructorId: data.instructor_id,
      serviceId: data.service_id,
      slotId: data.availability_slot_id,
      hasNotes: !!data.notes
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
        slotId: data.availability_slot_id,
        error 
      });
      throw new Error(error.detail || 'Failed to create booking');
    }
    
    const booking = await response.json();
    logger.info('Booking created successfully', { 
      bookingId: booking.id,
      status: booking.status 
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
  getMyBookings: async (filters?: BookingFilters) => {
    logger.debug('Fetching user bookings', { filters });
    
    const params = new URLSearchParams();
    if (filters?.status) params.append('status', filters.status);
    if (filters?.upcoming !== undefined) params.append('upcoming_only', filters.upcoming.toString());
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
      count: result.bookings?.length || 0,
      total: result.total 
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
  getBooking: async (bookingId: number) => {
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
      status: booking.status 
    });
    return booking;
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
  cancelBooking: async (bookingId: number, data: CancelBookingRequest) => {
    logger.info('Cancelling booking', { 
      bookingId,
      hasReason: !!data.cancellation_reason 
    });
    
    const response = await fetchWithAuth(`/bookings/${bookingId}/cancel`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        reason: data.cancellation_reason  // Map cancellation_reason to reason
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
            errorDetail = error.detail.map((e: any) => 
              `${e.loc?.join(' > ') || 'Field'}: ${e.msg}`
            ).join(', ');
          }
        }
      } catch (e) {
        logger.debug('Failed to parse error response');
      }
      
      logger.error('Booking cancellation failed', undefined, { 
        bookingId,
        errorDetail 
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
  completeBooking: async (bookingId: number) => {
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
  markNoShow: async (bookingId: number) => {
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
   * console.log(`Total bookings: ${stats.total_bookings}`);
   * ```
   */
  getBookingStats: async () => {
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
      completedBookings: stats.completed_bookings 
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
  getUpcomingBookings: async (limit: number = 5) => {
    logger.debug('Fetching upcoming bookings', { limit });
    
    const response = await fetchWithAuth(`/bookings/upcoming?limit=${limit}`);
    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to fetch upcoming bookings', undefined, { limit, error });
      throw new Error(error.detail || 'Failed to fetch upcoming bookings');
    }
    
    const bookings = await response.json();
    logger.debug('Upcoming bookings fetched', { 
      count: bookings.length,
      requestedLimit: limit 
    });
    return bookings;
  }
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
  getInstructorAvailability: async (instructorId: number, startDate: string, endDate: string) => {
    logger.debug('Fetching instructor availability', { 
      instructorId,
      startDate,
      endDate 
    });
    
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate
    });
    
    const response = await fetchWithAuth(`/availability/instructor/${instructorId}?${params.toString()}`);
    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to fetch availability', undefined, { 
        instructorId,
        dateRange: { startDate, endDate },
        error 
      });
      throw new Error(error.detail || 'Failed to fetch availability');
    }
    
    const availability = await response.json();
    logger.debug('Availability fetched', { 
      instructorId,
      slotsCount: availability.slots?.length || 0 
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
  getAvailableSlots: async (instructorId: number, date: string, serviceId?: number) => {
    logger.debug('Fetching available slots', { 
      instructorId,
      date,
      serviceId 
    });
    
    const params = new URLSearchParams({ date });
    if (serviceId) params.append('service_id', serviceId.toString());
    
    const response = await fetchWithAuth(`/availability/instructor/${instructorId}/slots?${params.toString()}`);
    if (!response.ok) {
      const error = await response.json();
      logger.error('Failed to fetch available slots', undefined, { 
        instructorId,
        date,
        serviceId,
        error 
      });
      throw new Error(error.detail || 'Failed to fetch available slots');
    }
    
    const slots = await response.json();
    logger.debug('Available slots fetched', { 
      instructorId,
      date,
      availableCount: slots.filter((s: any) => s.is_available).length,
      totalCount: slots.length 
    });
    return slots;
  }
};