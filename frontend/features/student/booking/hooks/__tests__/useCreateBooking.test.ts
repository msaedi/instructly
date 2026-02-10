// features/student/booking/hooks/__tests__/useCreateBooking.test.ts
import { renderHook, act } from '@testing-library/react';
import { useCreateBooking } from '../useCreateBooking';
import type { BookingResponse } from '@/src/api/generated/instructly.schemas';

// Mock the v1 bookings service
const mockCreateBookingImperative = jest.fn();
jest.mock('@/src/api/services/bookings', () => ({
  createBookingImperative: (...args: unknown[]) => mockCreateBookingImperative(...args),
}));

describe('useCreateBooking', () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  describe('Error Handling', () => {
    it('should handle 409 conflict error for student double-booking', async () => {
      mockCreateBookingImperative.mockRejectedValueOnce(
        new Error('409: You already have a booking scheduled at this time')
      );

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.error).toBe(
        'You already have a booking scheduled at this time. Please select a different time slot.'
      );
      expect(result.current.isLoading).toBe(false);
    });

    it('should handle 409 conflict error for instructor unavailability', async () => {
      mockCreateBookingImperative.mockRejectedValueOnce(
        new Error('409: This time slot conflicts with an existing booking')
      );

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.error).toBe(
        'This time slot is no longer available. Please select another time.'
      );
      expect(result.current.isLoading).toBe(false);
    });

    it('should handle 401 unauthorized error', async () => {
      mockCreateBookingImperative.mockRejectedValueOnce(new Error('401: Unauthorized'));

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.error).toBe('You must be logged in to book lessons');
    });

    it('should handle validation errors with advance booking message', async () => {
      mockCreateBookingImperative.mockRejectedValueOnce(
        new Error('Bookings must be made at least 24 hours in advance')
      );

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.error).toBe(
        'This instructor requires advance booking. Please select a time at least 24 hours in advance.'
      );
    });

    it('should reset error when calling reset', async () => {
      mockCreateBookingImperative.mockRejectedValueOnce(new Error('Some error'));

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.error).toBeTruthy();

      act(() => {
        result.current.reset();
      });

      expect(result.current.error).toBeNull();
      expect(result.current.booking).toBeNull();
    });

    it('should require selected_duration', async () => {
      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 0,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.error).toBe('selected_duration is required to create a booking');
      expect(mockCreateBookingImperative).not.toHaveBeenCalled();
    });
  });

  describe('Successful Booking', () => {
    it('should create booking successfully', async () => {
      const booking = {
        id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
        instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR2',
        student_id: '01K2GY3VEVJWKZDVH5HMNXEVR3',
        instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
        booking_date: '2025-01-01',
        start_time: '10:00:00',
        end_time: '11:00:00',
        duration_minutes: 60,
        status: 'CONFIRMED',
        total_price: 100,
        hourly_rate: 100,
        created_at: '2025-01-01T00:00:00Z',
        instructor: { id: '01K2GY3VEVJWKZDVH5HMNXEVR2', first_name: 'Alice', last_initial: 'B' },
        service_name: 'Math Tutoring',
      } as BookingResponse;

      mockCreateBookingImperative.mockResolvedValueOnce(booking);

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.booking).toEqual(booking);
      expect(result.current.error).toBeNull();
      expect(result.current.isLoading).toBe(false);
    });

    it('should calculate duration from start/end times if selected_duration not provided', async () => {
      const booking = {
        id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
        instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR2',
        student_id: '01K2GY3VEVJWKZDVH5HMNXEVR3',
        instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
        booking_date: '2025-01-01',
        start_time: '10:00:00',
        end_time: '11:30:00',
        duration_minutes: 90,
        status: 'CONFIRMED',
        total_price: 150,
        hourly_rate: 100,
        created_at: '2025-01-01T00:00:00Z',
        instructor: { id: '01K2GY3VEVJWKZDVH5HMNXEVR2', first_name: 'Alice', last_initial: 'B' },
        service_name: 'Math Tutoring',
      } as BookingResponse;

      mockCreateBookingImperative.mockResolvedValueOnce(booking);

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '10:00:00',
          end_time: '11:30:00',
          location_type: 'neutral_location',
        } as Parameters<typeof result.current.createBooking>[0]);
      });

      expect(mockCreateBookingImperative).toHaveBeenCalledWith(
        expect.objectContaining({
          selected_duration: 90,
        })
      );
      expect(result.current.booking).toEqual(booking);
    });
  });

  describe('Payload construction', () => {
    it('includes optional student_note when provided', async () => {
      const booking = {
        id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
        status: 'CONFIRMED',
      } as unknown as Parameters<ReturnType<typeof useCreateBooking>['createBooking']>[0] extends infer T ? T : never;

      mockCreateBookingImperative.mockResolvedValueOnce(booking);

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
          student_note: 'I want to focus on scales',
        });
      });

      expect(mockCreateBookingImperative).toHaveBeenCalledWith(
        expect.objectContaining({
          student_note: 'I want to focus on scales',
        })
      );
    });

    it('includes meeting_location and derives location_address from it', async () => {
      mockCreateBookingImperative.mockResolvedValueOnce({
        id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
        status: 'CONFIRMED',
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
          meeting_location: '123 Main St',
        } as Parameters<typeof result.current.createBooking>[0]);
      });

      expect(mockCreateBookingImperative).toHaveBeenCalledWith(
        expect.objectContaining({
          meeting_location: '123 Main St',
          location_address: '123 Main St', // Derived from meeting_location
        })
      );
    });

    it('prefers location_address over meeting_location when both provided', async () => {
      mockCreateBookingImperative.mockResolvedValueOnce({
        id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
        status: 'CONFIRMED',
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
          meeting_location: '123 Main St',
          location_address: '456 Elm St',
        } as Parameters<typeof result.current.createBooking>[0]);
      });

      expect(mockCreateBookingImperative).toHaveBeenCalledWith(
        expect.objectContaining({
          location_address: '456 Elm St',
        })
      );
    });

    it('includes location_lat, location_lng, and location_place_id', async () => {
      mockCreateBookingImperative.mockResolvedValueOnce({
        id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
        status: 'CONFIRMED',
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
          location_lat: 40.7128,
          location_lng: -74.006,
          location_place_id: 'ChIJOwg_06VPwokRYv534QaPC8g',
        } as Parameters<typeof result.current.createBooking>[0]);
      });

      expect(mockCreateBookingImperative).toHaveBeenCalledWith(
        expect.objectContaining({
          location_lat: 40.7128,
          location_lng: -74.006,
          location_place_id: 'ChIJOwg_06VPwokRYv534QaPC8g',
        })
      );
    });

    it('defaults location_type to online when not provided', async () => {
      mockCreateBookingImperative.mockResolvedValueOnce({
        id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
        status: 'CONFIRMED',
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
        } as Parameters<typeof result.current.createBooking>[0]);
      });

      expect(mockCreateBookingImperative).toHaveBeenCalledWith(
        expect.objectContaining({
          location_type: 'online',
        })
      );
    });
  });

  describe('Duration calculation edge cases', () => {
    it('falls back to 0 when end_time is not provided and selected_duration is undefined', async () => {
      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          location_type: 'neutral_location',
        } as Parameters<typeof result.current.createBooking>[0]);
      });

      // Duration can't be calculated without end_time, falls to 0 -> error
      expect(result.current.error).toBe('selected_duration is required to create a booking');
      expect(mockCreateBookingImperative).not.toHaveBeenCalled();
    });

    it('handles negative duration when end_time is before start_time', async () => {
      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '16:00:00',
          end_time: '14:00:00',
          location_type: 'neutral_location',
        } as Parameters<typeof result.current.createBooking>[0]);
      });

      // Negative duration -> selectedDuration is 0 or negative -> error
      expect(result.current.error).toBe('selected_duration is required to create a booking');
    });
  });

  describe('Loading state management', () => {
    it('sets isLoading to true during booking creation', async () => {
      let resolvePromise: (value: unknown) => void;
      const pendingPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });
      mockCreateBookingImperative.mockReturnValueOnce(pendingPromise);

      const { result } = renderHook(() => useCreateBooking());

      // Start but don't await
      let createPromise: Promise<unknown>;
      act(() => {
        createPromise = result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      // Should be loading
      expect(result.current.isLoading).toBe(true);

      // Resolve
      await act(async () => {
        resolvePromise!({ id: 'booking-1', status: 'CONFIRMED' });
        await createPromise!;
      });

      expect(result.current.isLoading).toBe(false);
    });

    it('returns null on error and sets isLoading to false', async () => {
      mockCreateBookingImperative.mockRejectedValueOnce(new Error('Server error'));

      const { result } = renderHook(() => useCreateBooking());

      let returnValue: unknown;
      await act(async () => {
        returnValue = await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(returnValue).toBeNull();
      expect(result.current.isLoading).toBe(false);
    });
  });

  describe('Additional Error Scenarios', () => {
    it('should handle 404 not found error', async () => {
      mockCreateBookingImperative.mockRejectedValueOnce(
        new Error('404: Instructor not found')
      );

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.error).toBe('Instructor or service not found');
    });

    it('should handle outside availability error', async () => {
      mockCreateBookingImperative.mockRejectedValueOnce(
        new Error('Selected time is outside availability')
      );

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '23:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.error).toBe(
        "The selected time is outside the instructor's availability."
      );
    });

    it('should handle non-Error thrown value', async () => {
      mockCreateBookingImperative.mockRejectedValueOnce('String error');

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.error).toBe('Failed to create booking');
    });

    it('should handle error with empty message', async () => {
      mockCreateBookingImperative.mockRejectedValueOnce(new Error(''));

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          selected_duration: 60,
          location_type: 'neutral_location',
        });
      });

      expect(result.current.error).toBe('An unexpected error occurred');
    });
  });

});

describe('calculateEndTime', () => {
  // Import the function
  const { calculateEndTime } = require('../useCreateBooking');

  it('should calculate end time correctly for 60 minute duration', () => {
    expect(calculateEndTime('10:00', 60)).toBe('11:00');
  });

  it('should calculate end time correctly for 90 minute duration', () => {
    expect(calculateEndTime('10:00', 90)).toBe('11:30');
  });

  it('should calculate end time correctly for 30 minute duration', () => {
    expect(calculateEndTime('14:30', 30)).toBe('15:00');
  });

  it('should handle times with seconds', () => {
    expect(calculateEndTime('10:00:00', 60)).toBe('11:00');
  });

  it('should wrap around midnight correctly', () => {
    expect(calculateEndTime('23:30', 60)).toBe('00:30');
  });

  it('should throw error for empty start time', () => {
    expect(() => calculateEndTime('', 60)).toThrow('Start time is required');
  });

  it('should throw error for invalid time format', () => {
    expect(() => calculateEndTime('invalid', 60)).toThrow('Invalid time format');
  });

  it('should handle single digit hours and minutes', () => {
    expect(calculateEndTime('9:5', 60)).toBe('10:05');
  });
});
