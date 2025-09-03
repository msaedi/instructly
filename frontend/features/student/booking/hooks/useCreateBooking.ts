// frontend/features/student/booking/hooks/useCreateBooking.ts
import { useState } from 'react';
import { protectedApi, CreateBookingRequest, Booking } from '@/features/shared/api/client';
import { logger } from '@/lib/logger';

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
      serviceId: data.instructor_service_id || (data as unknown as { service_id?: string }).service_id,
      startDate: data.booking_date,
      startTime: data.start_time,
    });

    try {
      const payload = {
        ...data,
        instructor_service_id:
          (data as unknown as { instructor_service_id?: string }).instructor_service_id ||
          (data as unknown as { service_id?: string }).service_id,
        selected_duration:
          (data as unknown as { selected_duration?: number }).selected_duration ||
          (() => {
            // If not provided, infer from start/end when possible
            try {
              const [shStr, smStr] = String(data.start_time).split(':');
              const [ehStr, emStr] = String(data.end_time).split(':');
              const sh = parseInt(shStr ?? '0', 10);
              const sm = parseInt(smStr ?? '0', 10);
              const eh = parseInt(ehStr ?? '0', 10);
              const em = parseInt(emStr ?? '0', 10);
              const mins = eh * 60 + em - (sh * 60 + sm);
              return Number.isFinite(mins) && mins > 0 ? mins : undefined;
            } catch {
              return undefined;
            }
          })(),
      } as CreateBookingRequest;

      const response = await protectedApi.createBooking(payload);

      if (response.error) {
        // Handle specific error scenarios
        let errorMessage = 'Failed to create booking';

        // Extract message from error object if it's an object
        const errorText =
          typeof response.error === 'object' && response.error && 'message' in response.error
            ? (response.error as { message: string }).message
            : response.error;

        if (response.status === 401) {
          errorMessage = 'You must be logged in to book lessons';
        } else if (response.status === 409) {
          // Conflict - check if it's a student double-booking or instructor conflict
          if (typeof errorText === 'string' && errorText.includes('already have a booking')) {
            errorMessage =
              'You already have a booking scheduled at this time. Please select a different time slot.';
          } else {
            errorMessage = 'This time slot is no longer available. Please select another time.';
          }
        } else if (response.status === 400 || response.status === 422) {
          // Validation error
          if (typeof errorText === 'string') {
            if (errorText.includes('advance booking') || errorText.includes('24 hours')) {
              errorMessage =
                'This instructor requires advance booking. Please select a time at least 24 hours in advance.';
            } else if (errorText.includes('outside availability')) {
              errorMessage = "The selected time is outside the instructor's availability.";
            } else {
              errorMessage = errorText;
            }
          } else {
            errorMessage = 'Invalid booking request. Please check your selection.';
          }
        } else if (response.status === 404) {
          errorMessage = 'Instructor or service not found';
        } else {
          errorMessage = typeof errorText === 'string' ? errorText : 'An unexpected error occurred';
        }

        logger.error('Booking creation failed', undefined, {
          status: response.status,
          error: response.error,
          errorMessage,
        });

        setError(errorMessage);
        return null;
      }

      if (response.data) {
        logger.info('Booking created successfully', {
          bookingId: response.data.id,
          status: response.data.status,
        });
        setBooking(response.data);
        return response.data;
      }

      // Unexpected case - no error but no data
      setError('Unexpected response from server');
      return null;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Network error occurred';
      logger.error('Booking creation error', err as Error);
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
