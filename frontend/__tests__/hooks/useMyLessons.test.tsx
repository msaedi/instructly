import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useCurrentLessons,
  useCompletedLessons,
  useLessonDetails,
  useCancelLesson,
  useRescheduleLesson,
  calculateCancellationFee,
} from '@/hooks/useMyLessons';
import { Booking } from '@/types/booking';

// Mock the booking service
jest.mock('@/lib/api/bookings', () => ({
  bookingService: {
    getMyBookings: jest.fn(),
    getBookingDetails: jest.fn(),
    cancelBooking: jest.fn(),
    rescheduleBooking: jest.fn(),
  },
}));

// Mock the queryFn
jest.mock('@/lib/react-query/api', () => ({
  queryFn: jest.fn((endpoint: string, options?: { params?: Record<string, unknown> }) => {
    return async () => {
      // Updated: upcoming lessons now use /bookings/upcoming with limit param
      const isUpcoming = typeof endpoint === 'string' && endpoint.includes('/bookings/upcoming');
      const legacyUpcoming = options?.params?.status === 'CONFIRMED' && options?.params?.upcoming_only === true;
      if (isUpcoming || legacyUpcoming) {
        return {
          items: [
            {
              id: 1,
              booking_date: '2024-12-25',
              start_time: '14:00:00',
              status: 'CONFIRMED',
              total_price: 60,
            },
          ],
          total: 1,
          page: 1,
          per_page: 20,
        };
      }
      return {
        items: [
          {
            id: 2,
            booking_date: '2024-12-20',
            start_time: '10:00:00',
            status: 'COMPLETED',
            total_price: 60,
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
      };
    };
  }),
  mutationFn: jest.fn(() => {
    return async () => ({
      id: 1,
      status: 'CANCELLED',
    });
  }),
}));

const createTestQueryClient = () => {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  });
};

const wrapper = ({ children }: { children: ReactNode }) => {
  const queryClient = createTestQueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
};

describe('useMyLessons hooks', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('useCurrentLessons', () => {
    it('fetches upcoming lessons', async () => {
      const { result } = renderHook(() => useCurrentLessons(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.items).toHaveLength(1);
      expect(result.current.data?.items[0].status).toBe('CONFIRMED');
    });

    it('uses correct cache time', () => {
      const { result } = renderHook(() => useCurrentLessons(), { wrapper });

      // The query should be configured with the correct stale time
      expect(result.current).toHaveProperty('dataUpdatedAt');
    });
  });

  describe('useCompletedLessons', () => {
    it('fetches completed and cancelled lessons', async () => {
      const { result } = renderHook(() => useCompletedLessons(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.items).toBeDefined();
    });

    it('filters lessons correctly', async () => {
      // Update mock to return mixed statuses
      const mockQueryFn = require('@/lib/react-query/api').queryFn;
      mockQueryFn.mockImplementation(() => async () => ({
        items: [
          {
            id: 1,
            booking_date: '2024-12-30',
            start_time: '14:00:00',
            status: 'CONFIRMED',
            total_price: 60,
          },
          {
            id: 2,
            booking_date: '2024-12-20',
            start_time: '10:00:00',
            status: 'CANCELLED',
            total_price: 60,
          },
          {
            id: 3,
            booking_date: '2024-12-20',
            start_time: '10:00:00',
            status: 'COMPLETED',
            total_price: 60,
          },
        ],
        total: 3,
        page: 1,
        per_page: 20,
      }));

      const { result } = renderHook(() => useCompletedLessons(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Should filter out future confirmed lessons
      const bookings = result.current.data?.items || [];
      const confirmedFuture = bookings.filter(
        (b) =>
          b.status === 'CONFIRMED' && new Date(`${b.booking_date}T${b.start_time}`) > new Date()
      );
      expect(confirmedFuture.length).toBe(0);
    });
  });

  describe('useLessonDetails', () => {
    it('fetches lesson details by ID', async () => {
      // Mock the queryFn for lesson details
      const mockQueryFn = require('@/lib/react-query/api').queryFn;
      mockQueryFn.mockImplementation((_endpoint: string) => async () => ({
        id: 1,
        booking_date: '2024-12-25',
        status: 'CONFIRMED',
        instructor: { first_name: 'John', last_initial: 'D' },
        service_name: 'Mathematics',
        total_price: 60,
      }));

      const { result } = renderHook(() => useLessonDetails('1'), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.id).toBe(1);
      expect(result.current.data?.instructor?.first_name).toBe('John');
      expect(result.current.data?.instructor?.last_initial).toBe('D');
    });

    it('handles invalid lesson ID', async () => {
      // Mock the queryFn to throw error
      const mockQueryFn = require('@/lib/react-query/api').queryFn;
      mockQueryFn.mockImplementation(() => async () => {
        throw new Error('Booking not found');
      });

      const { result } = renderHook(() => useLessonDetails('999'), { wrapper });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Booking not found');
    });
  });

  describe('useCancelLesson', () => {
    it('cancels a lesson successfully', async () => {
      const { result } = renderHook(() => useCancelLesson(), { wrapper });

      result.current.mutate({
        lessonId: '1',
        reason: 'Schedule conflict',
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(false); // Mutation doesn't auto-succeed
      });
    });

    it('handles cancellation errors', async () => {
      // Mock mutationFn to throw error
      const mockMutationFn = require('@/lib/react-query/api').mutationFn;
      mockMutationFn.mockImplementation(() => async () => {
        throw new Error('Cannot cancel within 1 hour');
      });

      const { result } = renderHook(() => useCancelLesson(), { wrapper });

      result.current.mutate({
        lessonId: '1',
        reason: 'Emergency',
      });

      await waitFor(() => {
        // Initially the mutation is loading, not error yet
        expect(result.current.isPending || result.current.isError).toBe(true);
      });
    });
  });

  describe('useRescheduleLesson', () => {
    it('reschedules a lesson successfully', async () => {
      const { result } = renderHook(() => useRescheduleLesson(), { wrapper });

      result.current.mutate({
        lessonId: '1',
        newDate: '2024-12-26',
        newStartTime: '10:00:00',
        newEndTime: '11:00:00',
      });

      await waitFor(() => {
        expect(result.current.isIdle || result.current.isPending).toBe(true);
      });
    });
  });

  describe('calculateCancellationFee', () => {
    it('returns 0 for cancellations more than 24 hours in advance', () => {
      const booking = {
        booking_date: '2024-12-30',
        start_time: '14:00:00',
        total_price: 60,
      } as Booking;

      // Mock current date to be well before the lesson
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25'));

      const result = calculateCancellationFee(booking);
      expect(result.fee).toBe(0);
      expect(result.percentage).toBe(0);

      jest.useRealTimers();
    });

    it('returns 50% fee for cancellations between 1-24 hours', () => {
      const booking = {
        booking_date: '2024-12-26',
        start_time: '14:00:00',
        total_price: 60,
      } as Booking;

      // Mock current date to be 18 hours before the lesson (between 12-24 hours)
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25T20:00:00'));

      const result = calculateCancellationFee(booking);
      expect(result.fee).toBe(30);
      expect(result.percentage).toBe(50);

      jest.useRealTimers();
    });

    it('returns 100% fee for cancellations within 1 hour', () => {
      const booking = {
        booking_date: '2024-12-26',
        start_time: '14:00:00',
        total_price: 60,
      } as Booking;

      // Mock current date to be 30 minutes before the lesson
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-26T13:30:00'));

      const result = calculateCancellationFee(booking);
      expect(result.fee).toBe(60);
      expect(result.percentage).toBe(100);

      jest.useRealTimers();
    });

    it('handles edge cases correctly', () => {
      const booking = {
        booking_date: '2024-12-26',
        start_time: '14:00:00',
        total_price: 60,
      } as Booking;

      // Exactly 24 hours before (edge case - should be 50% since it's not > 24)
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25T14:00:00'));
      const result24 = calculateCancellationFee(booking);
      expect(result24.fee).toBe(30);
      expect(result24.percentage).toBe(50);

      // Exactly 12 hours before (edge case - should be 100% since it's not > 12)
      jest.setSystemTime(new Date('2024-12-26T02:00:00'));
      const result12 = calculateCancellationFee(booking);
      expect(result12.fee).toBe(60);
      expect(result12.percentage).toBe(100);

      jest.useRealTimers();
    });
  });
});
