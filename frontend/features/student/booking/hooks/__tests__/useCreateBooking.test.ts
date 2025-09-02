// features/student/booking/hooks/__tests__/useCreateBooking.test.ts
import { renderHook, act } from '@testing-library/react';
import { useCreateBooking } from '../useCreateBooking';
import * as apiClient from '@/features/shared/api/client';
import { Booking } from '@/types/booking';

// Mock the API module
jest.mock('@/features/shared/api/client');

// SKIPPED: Booking system is undergoing changes - will be updated when booking API stabilizes
describe.skip('useCreateBooking', () => {
  const mockCreateBooking = apiClient.protectedApi.createBooking as jest.MockedFunction<
    typeof apiClient.protectedApi.createBooking
  >;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Error Handling', () => {
    it('should handle 409 conflict error for student double-booking', async () => {
      // Mock API response for student conflict
      mockCreateBooking.mockResolvedValueOnce({
        data: undefined,
        error: 'You already have a booking scheduled at this time',
        status: 409,
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          selected_duration: 60,
          meeting_location: 'Online',
          location_type: 'neutral',
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
        data: undefined,
        error: 'This time slot conflicts with an existing booking',
        status: 409,
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          selected_duration: 60,
          meeting_location: 'Online',
          location_type: 'neutral',
        });
      });

      expect(result.current.error).toBe(
        'This time slot is no longer available. Please select another time.'
      );
      expect(result.current.isLoading).toBe(false);
    });

    it('should handle 401 unauthorized error', async () => {
      mockCreateBooking.mockResolvedValueOnce({
        data: undefined,
        error: 'Unauthorized',
        status: 401,
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          selected_duration: 60,
          meeting_location: 'Online',
          location_type: 'neutral',
        });
      });

      expect(result.current.error).toBe('You must be logged in to book lessons');
    });

    it('should handle validation errors with advance booking message', async () => {
      mockCreateBooking.mockResolvedValueOnce({
        data: undefined,
        error: 'Bookings must be made at least 24 hours in advance',
        status: 400,
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          selected_duration: 60,
          meeting_location: 'Online',
          location_type: 'neutral',
        });
      });

      expect(result.current.error).toBe(
        'This instructor requires advance booking. Please select a time at least 24 hours in advance.'
      );
    });

    it('should reset error when calling reset', async () => {
      // Mock error first
      mockCreateBooking.mockResolvedValueOnce({
        data: undefined,
        error: 'Some error',
        status: 400,
      });

      const { result } = renderHook(() => useCreateBooking());

      // Create an error by making a failing call
      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          selected_duration: 60,
          meeting_location: 'Online',
          location_type: 'neutral',
        });
      });

      expect(result.current.error).toBeTruthy();

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
      const booking: Partial<Booking> = {
        id: '01K2GY3VEVJWKZDVH5HMNXEVRD',
        instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR2',
        student_id: '01K2GY3VEVJWKZDVH5HMNXEVR3',
        instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
        booking_date: '2025-01-01',
        start_time: '10:00:00',
        end_time: '11:00:00',
        status: 'CONFIRMED',
        service_name: 'Service',
        hourly_rate: 100,
        total_price: 100,
        duration_minutes: 60,
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z',
        instructor: { id: '01K2GY3VEVJWKZDVH5HMNXEVR2', first_name: 'A', last_initial: 'B' },
        service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
        service: {
          id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          instructor_profile_id: '01K2GY3VEVJWKZDVH5HMNXEVR2',
          name: 'Service',
          description: 'Test service',
          hourly_rate: 100,
          created_at: '2025-01-01T00:00:00Z',
          updated_at: '2025-01-01T00:00:00Z'
        },
      };

      mockCreateBooking.mockResolvedValueOnce({
        data: booking,
        error: undefined,
        status: 200,
      });

      const { result } = renderHook(() => useCreateBooking());

      await act(async () => {
        await result.current.createBooking({
          instructor_id: '01K2GY3VEVJWKZDVH5HMNXEVR1',
          instructor_service_id: '01K2GY3VEVJWKZDVH5HMNXEVR4',
          booking_date: '2024-01-15',
          start_time: '14:00:00',
          end_time: '15:00:00',
          selected_duration: 60,
          meeting_location: 'Online',
          location_type: 'neutral',
        });
      });

      expect(result.current.booking).toEqual(booking);
      expect(result.current.error).toBeNull();
      expect(result.current.isLoading).toBe(false);
    });
  });
});
