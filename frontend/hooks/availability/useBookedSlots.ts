// frontend/hooks/availability/useBookedSlots.ts

/**
 * useBookedSlots Hook
 *
 * Manages booked slots data for the availability calendar.
 * Provides utilities for checking bookings, caching data, and
 * handling booking-related operations.
 *
 * @module hooks/availability/useBookedSlots
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { BookedSlotPreview } from '@/types/booking';
import { fetchWithAuth, API_ENDPOINTS } from '@/lib/api';
import { formatDateForAPI } from '@/lib/availability/dateHelpers';
// Local lightweight helpers to avoid legacy-patterns dependency
function createBookedHoursMapLocal(booked: BookedSlotPreview[]): Map<string, true> {
  const map = new Map<string, true>();
  for (const b of booked) {
    // Mark each covered hour within the booking range
    const startTimeParts = String(b.start_time).split(':');
    const endTimeParts = String(b.end_time).split(':');
    const startHour = parseInt(startTimeParts[0] || '0');
    const endHour = parseInt(endTimeParts[0] || '0');
    for (let h = startHour; h < endHour; h++) {
      map.set(`${b.date}-${h}`, true);
    }
  }
  return map;
}

function findBookingForSlotLocal(date: string, hour: number, booked: BookedSlotPreview[]): BookedSlotPreview | null {
  for (const b of booked) {
    if (b.date !== date) continue;
    const startTimeParts = String(b.start_time).split(':');
    const endTimeParts = String(b.end_time).split(':');
    const sh = parseInt(startTimeParts[0] || '0');
    const eh = parseInt(endTimeParts[0] || '0');
    if (hour >= sh && hour < eh) return b;
  }
  return null;
}
import { logger } from '@/lib/logger';

/**
 * Hook return type with booking management functionality
 */
export interface UseBookedSlotsReturn {
  // State
  /** Array of booked slots for the current week */
  bookedSlots: BookedSlotPreview[];
  /** Loading state for booking data */
  isLoadingBookings: boolean;
  /** Error state for booking operations */
  bookingError: string | null;
  /** Selected booking ID for preview */
  selectedBookingId: string | null;
  /** Whether booking preview modal is shown */
  showBookingPreview: boolean;

  // Utilities
  /** Check if a specific slot is booked */
  isSlotBooked: (date: string, hour: number) => boolean;
  /** Get booking information for a slot */
  getBookingForSlot: (date: string, hour: number) => BookedSlotPreview | null;
  /** Check if booking exists in a time range */
  hasBookingInRange: (date: string, startHour: number, endHour: number) => boolean;
  /** Get all bookings for a specific date */
  getBookingsForDate: (date: string) => BookedSlotPreview[];

  // Actions
  /** Fetch booked slots for a week */
  fetchBookedSlots: (weekStart: Date) => Promise<void>;
  /** Handle booking slot click */
  handleBookingClick: (bookingId: string) => void;
  /** Close booking preview */
  closeBookingPreview: () => void;
  /** Refresh booking data */
  refreshBookings: (weekStart: Date) => Promise<void>;
}

/**
 * Custom hook for managing booked slots data
 *
 * @param options - Configuration options
 * @returns {UseBookedSlotsReturn} Booking state and utilities
 *
 * @example
 * ```tsx
 * function AvailabilityCalendar({ weekStart }) {
 *   const {
 *     bookedSlots,
 *     isSlotBooked,
 *     handleBookingClick
 *   } = useBookedSlots();
 *
 *   // Check if a slot is booked before allowing modifications
 *   if (isSlotBooked(date, hour)) {
 *     handleBookingClick(booking.id);
 *   }
 * }
 * ```
 */
export function useBookedSlots(
  options: {
    /** Enable caching of booking data */
    enableCache?: boolean;
    /** Cache duration in milliseconds */
    cacheDuration?: number;
  } = {}
): UseBookedSlotsReturn {
  const {
    enableCache = true,
    cacheDuration = 5 * 60 * 1000, // 5 minutes default
  } = options;

  // State
  const [bookedSlots, setBookedSlots] = useState<BookedSlotPreview[]>([]);
  const [isLoadingBookings, setIsLoadingBookings] = useState(false);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [selectedBookingId, setSelectedBookingId] = useState<string | null>(null);
  const [showBookingPreview, setShowBookingPreview] = useState(false);

  // Cache management
  const [cache, setCache] = useState<{
    weekStart: string | null;
    timestamp: number;
    data: BookedSlotPreview[];
  }>({
    weekStart: null,
    timestamp: 0,
    data: [],
  });

  /**
   * Create optimized lookup map for booked hours
   */
  const bookedHoursMap = useMemo(() => {
    return createBookedHoursMapLocal(bookedSlots);
  }, [bookedSlots]);

  /**
   * Fetch booked slots from API
   */
  const fetchBookedSlots = useCallback(
    async (weekStart: Date) => {
      const weekStartStr = formatDateForAPI(weekStart);

      // Check cache if enabled
      if (enableCache && cache.weekStart === weekStartStr) {
        const cacheAge = Date.now() - cache.timestamp;
        if (cacheAge < cacheDuration) {
          logger.debug('Using cached booked slots', {
            weekStart: weekStartStr,
            cacheAge: Math.round(cacheAge / 1000) + 's',
          });
          setBookedSlots(cache.data);
          return;
        }
      }

      setIsLoadingBookings(true);
      setBookingError(null);
      logger.time('fetchBookedSlots');

      try {
        const response = await fetchWithAuth(
          `${API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_WEEK}/booked-slots?start_date=${weekStartStr}`
        );

        if (!response.ok) {
          throw new Error('Failed to fetch booked slots');
        }

        const data = await response.json();
        const slots = data.booked_slots;

        logger.info('Fetched booked slots', {
          weekStart: weekStartStr,
          count: slots.length,
          dates: [...new Set(slots.map((s: BookedSlotPreview) => s.date))].length,
        });

        setBookedSlots(slots);

        // Update cache
        if (enableCache) {
          setCache({
            weekStart: weekStartStr,
            timestamp: Date.now(),
            data: slots,
          });
        }
      } catch (error) {
        logger.error('Failed to fetch booked slots', error);
        setBookingError('Failed to load bookings');
        setBookedSlots([]);
      } finally {
        logger.timeEnd('fetchBookedSlots');
        setIsLoadingBookings(false);
      }
    },
    [enableCache, cache, cacheDuration]
  );

  /**
   * Check if a specific slot is booked (optimized)
   */
  const isSlotBooked = useCallback(
    (date: string, hour: number): boolean => {
      // Use optimized map lookup
      return bookedHoursMap.has(`${date}-${hour}`);
    },
    [bookedHoursMap]
  );

  /**
   * Get booking information for a slot
   */
  const getBookingForSlot = useCallback(
    (date: string, hour: number): BookedSlotPreview | null => {
      return findBookingForSlotLocal(date, hour, bookedSlots);
    },
    [bookedSlots]
  );

  /**
   * Check if any booking exists in a time range
   */
  const hasBookingInRange = useCallback(
    (date: string, startHour: number, endHour: number): boolean => {
      for (let hour = startHour; hour < endHour; hour++) {
        if (isSlotBooked(date, hour)) {
          return true;
        }
      }
      return false;
    },
    [isSlotBooked]
  );

  /**
   * Get all bookings for a specific date
   */
  const getBookingsForDate = useCallback(
    (date: string): BookedSlotPreview[] => {
      return bookedSlots.filter((slot) => slot.date === date);
    },
    [bookedSlots]
  );

  /**
   * Handle booking click event
   */
  const handleBookingClick = useCallback((bookingId: string) => {
    logger.debug('Booking clicked', { bookingId });
    setSelectedBookingId(bookingId);
    setShowBookingPreview(true);
  }, []);

  /**
   * Close booking preview
   */
  const closeBookingPreview = useCallback(() => {
    logger.debug('Closing booking preview');
    setShowBookingPreview(false);
    setSelectedBookingId(null);
  }, []);

  /**
   * Refresh booking data (force cache bypass)
   */
  const refreshBookings = useCallback(
    async (weekStart: Date) => {
      logger.info('Refreshing bookings (bypassing cache)');

      // Clear cache to force refresh
      setCache({
        weekStart: null,
        timestamp: 0,
        data: [],
      });

      await fetchBookedSlots(weekStart);
    },
    [fetchBookedSlots]
  );

  /**
   * Log cache statistics periodically in development
   */
  useEffect(() => {
    if (process.env.NODE_ENV === 'development' && enableCache) {
      const interval = setInterval(() => {
        if (cache.weekStart) {
          const cacheAge = Date.now() - cache.timestamp;
          logger.debug('Booking cache status', {
            weekStart: cache.weekStart,
            ageSeconds: Math.round(cacheAge / 1000),
            itemCount: cache.data.length,
            isExpired: cacheAge > cacheDuration,
          });
        }
      }, 30000); // Log every 30 seconds

      return () => clearInterval(interval);
    }
  }, [cache, cacheDuration, enableCache]);

  return {
    // State
    bookedSlots,
    isLoadingBookings,
    bookingError,
    selectedBookingId,
    showBookingPreview,

    // Utilities
    isSlotBooked,
    getBookingForSlot,
    hasBookingInRange,
    getBookingsForDate,

    // Actions
    fetchBookedSlots,
    handleBookingClick,
    closeBookingPreview,
    refreshBookings,
  };
}
