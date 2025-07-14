// features/student/booking/hooks/__tests__/useCreateBooking.test.ts
import { renderHook, act } from '@testing-library/react';
import { useCreateBooking } from '../useCreateBooking';
import * as studentApi from '@/features/student/api/studentApi';

// Mock the API module
jest.mock('@/features/student/api/studentApi');

describe('useCreateBooking', () => {
  const mockCreateBooking = studentApi.protectedApi.createBooking as jest.MockedFunction<
    typeof studentApi.protectedApi.createBooking
  >;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Error Handling', () => {
    it('should handle 409 conflict error for student double-booking', async () => {
      // Mock API response for student conflict
      mockCreateBooking.mockResolvedValueOnce({
        data: null,
        error: { message: 'You already have a booking scheduled at this time' },
        status: 409,
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: 1,
          service_id: 1,
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          meeting_location: 'Online',
          location_type: 'online',
        });
      });

      expect(result.current.error).toBe(
        'You already have a booking scheduled at this time. Please select a different time slot.'
      );
      expect(result.current.isLoading).toBe(false);
    });

    it('should handle 409 conflict error for instructor unavailability', async () => {
      // Mock API response for instructor conflict
      mockCreateBooking.mockResolvedValueOnce({
        data: null,
        error: { message: 'This time slot conflicts with an existing booking' },
        status: 409,
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: 1,
          service_id: 1,
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          meeting_location: 'Online',
          location_type: 'online',
        });
      });

      expect(result.current.error).toBe(
        'This time slot is no longer available. Please select another time.'
      );
      expect(result.current.isLoading).toBe(false);
    });

    it('should handle 401 unauthorized error', async () => {
      mockCreateBooking.mockResolvedValueOnce({
        data: null,
        error: 'Unauthorized',
        status: 401,
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: 1,
          service_id: 1,
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          meeting_location: 'Online',
          location_type: 'online',
        });
      });

      expect(result.current.error).toBe('You must be logged in to book lessons');
    });

    it('should handle validation errors with advance booking message', async () => {
      mockCreateBooking.mockResolvedValueOnce({
        data: null,
        error: 'Bookings must be made at least 24 hours in advance',
        status: 400,
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: 1,
          service_id: 1,
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          meeting_location: 'Online',
          location_type: 'online',
        });
      });

      expect(result.current.error).toBe(
        'This instructor requires advance booking. Please select a time at least 24 hours in advance.'
      );
    });

    it('should reset error when calling reset', () => {
      const { result } = renderHook(() => useCreateBooking());

      // Set an error state
      act(() => {
        result.current.error = 'Some error';
      });

      // Reset
      act(() => {
        result.current.reset();
      });

      expect(result.current.error).toBeNull();
      expect(result.current.booking).toBeNull();
    });
  });

  describe('Successful Booking', () => {
    it('should create booking successfully', async () => {
      const mockBooking = {
        id: 123,
        instructor_id: 1,
        service_id: 1,
        booking_date: '2024-01-15',
        start_time: '14:00:00',
        end_time: '15:00:00',
        status: 'confirmed',
      };

      mockCreateBooking.mockResolvedValueOnce({
        data: mockBooking,
        error: null,
        status: 200,
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: 1,
          service_id: 1,
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          meeting_location: 'Online',
          location_type: 'online',
        });
      });

      expect(result.current.booking).toEqual(mockBooking);
      expect(result.current.error).toBeNull();
      expect(result.current.isLoading).toBe(false);
    });
  });
});
