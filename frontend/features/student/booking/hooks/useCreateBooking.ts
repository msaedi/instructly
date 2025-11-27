// frontend/features/student/booking/hooks/useCreateBooking.ts
import { useState } from 'react';
import { createBookingImperative } from '@/src/api/services/bookings';
import type { BookingCreate, BookingResponse } from '@/src/api/generated/instructly.schemas';
import { logger } from '@/lib/logger';

// Re-export types for backward compatibility
type CreateBookingRequest = BookingCreate;
type Booking = BookingResponse;

interface UseCreateBookingReturn {
  createBooking: (data: CreateBookingRequest) => Promise<Booking | null>;
  isLoading: boolean;
  error: string | null;
  booking: Booking | null;
  reset: () => void;
}

/**
 * Hook for creating bookings with error handling and loading states
 *
 * Features:
 * - Handles API calls to create bookings
 * - Manages loading and error states
 * - Provides detailed error messages for different scenarios
 * - Includes logging for debugging
 *
 * @returns {UseCreateBookingReturn} Booking creation utilities
 */
export function useCreateBooking(): UseCreateBookingReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [booking, setBooking] = useState<Booking | null>(null);

  const createBooking = async (data: CreateBookingRequest): Promise<Booking | null> => {
    setIsLoading(true);
    setError(null);

    logger.info('Creating booking', {
      instructorId: data.instructor_id,
      serviceId: data.instructor_service_id,
      startDate: data.booking_date,
      startTime: data.start_time,
    });

    try {
      // Calculate duration from start/end time if not provided
      const selectedDuration =
        data.selected_duration ??
        (() => {
          try {
            const startParts = String(data.start_time).split(':');
            const endParts = String((data as { end_time?: string }).end_time ?? '').split(':');
            const sh = parseInt(startParts[0] ?? '0', 10);
            const sm = parseInt(startParts[1] ?? '0', 10);
            const eh = parseInt(endParts[0] ?? '0', 10);
            const em = parseInt(endParts[1] ?? '0', 10);
            const mins = eh * 60 + em - (sh * 60 + sm);
            return Number.isFinite(mins) && mins > 0 ? mins : 0;
          } catch {
            return 0;
          }
        })();

      if (!selectedDuration || selectedDuration <= 0) {
        throw new Error('selected_duration is required to create a booking');
      }

      // Build payload for v1 API (handle exactOptionalPropertyTypes)
      const payload: BookingCreate = {
        instructor_id: data.instructor_id,
        instructor_service_id: data.instructor_service_id,
        booking_date: data.booking_date,
        start_time: data.start_time,
        selected_duration: selectedDuration,
        location_type: data.location_type ?? 'neutral',
        ...(data.student_note !== undefined ? { student_note: data.student_note } : {}),
        ...(data.meeting_location !== undefined ? { meeting_location: data.meeting_location } : {}),
      };

      // Use v1 bookings service
      const booking = await createBookingImperative(payload);

      logger.info('Booking created successfully', {
        bookingId: booking.id,
        status: booking.status,
      });
      setBooking(booking);
      return booking;
    } catch (err) {
      // Handle API errors
      let errorMessage = 'Failed to create booking';

      if (err instanceof Error) {
        const errMsg = err.message.toLowerCase();

        if (errMsg.includes('401') || errMsg.includes('unauthorized')) {
          errorMessage = 'You must be logged in to book lessons';
        } else if (errMsg.includes('409') || errMsg.includes('conflict')) {
          if (errMsg.includes('already have a booking')) {
            errorMessage =
              'You already have a booking scheduled at this time. Please select a different time slot.';
          } else {
            errorMessage = 'This time slot is no longer available. Please select another time.';
          }
        } else if (errMsg.includes('advance booking') || errMsg.includes('24 hours')) {
          errorMessage =
            'This instructor requires advance booking. Please select a time at least 24 hours in advance.';
        } else if (errMsg.includes('outside availability')) {
          errorMessage = "The selected time is outside the instructor's availability.";
        } else if (errMsg.includes('404') || errMsg.includes('not found')) {
          errorMessage = 'Instructor or service not found';
        } else {
          errorMessage = err.message || 'An unexpected error occurred';
        }
      }

      logger.error('Booking creation failed', err as Error, { errorMessage });
      setError(errorMessage);
      return null;
    } finally {
      setIsLoading(false);
    }
  };

  const reset = () => {
    setError(null);
    setBooking(null);
    setIsLoading(false);
  };

  return {
    createBooking,
    isLoading,
    error,
    booking,
    reset,
  };
}

/**
 * Helper function to calculate end time based on start time and duration
 *
 * @param startTime - Start time in HH:MM or HH:MM:SS format
 * @param durationMinutes - Duration in minutes
 * @returns End time in HH:MM format
 */
export function calculateEndTime(startTime: string, durationMinutes: number): string {
  if (!startTime) {
    throw new Error('Start time is required');
  }

  // Extract just hours and minutes, ignore seconds if present
  const timeParts = startTime.split(':');
  if (timeParts.length < 2) {
    throw new Error('Invalid time format. Expected HH:MM');
  }

  const hours = parseInt(timeParts[0] || '0') || 0;
  const minutes = parseInt(timeParts[1] || '0') || 0;

  const totalMinutes = hours * 60 + minutes + durationMinutes;

  const endHours = Math.floor(totalMinutes / 60) % 24;
  const endMinutes = totalMinutes % 60;

  return `${endHours.toString().padStart(2, '0')}:${endMinutes.toString().padStart(2, '0')}`;
}
