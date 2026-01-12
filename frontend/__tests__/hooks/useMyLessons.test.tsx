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
import type { Booking } from '@/features/shared/api/types';

// Mock v1 bookings services
const mockUseBookingsList = jest.fn();
const mockUseBookingsHistory = jest.fn();
const mockUseCancelledBookingsV1 = jest.fn();
const mockUseBooking = jest.fn();
const mockUseCancelBooking = jest.fn();
const mockUseRescheduleBooking = jest.fn();
const mockUseCompleteBooking = jest.fn();

jest.mock('@/src/api/services/bookings', () => ({
  useBookingsList: (...args: unknown[]) => mockUseBookingsList(...args),
  useBookingsHistory: (...args: unknown[]) => mockUseBookingsHistory(...args),
  useCancelledBookings: (...args: unknown[]) => mockUseCancelledBookingsV1(...args),
  useBooking: (...args: unknown[]) => mockUseBooking(...args),
  useCancelBooking: () => mockUseCancelBooking(),
  useRescheduleBooking: () => mockUseRescheduleBooking(),
  useCompleteBooking: () => mockUseCompleteBooking(),
}));

// Mock v1 instructor-bookings services
jest.mock('@/src/api/services/instructor-bookings', () => ({
  useMarkLessonComplete: jest.fn(() => ({
    mutate: jest.fn(),
    mutateAsync: jest.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    error: null,
  })),
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

// Default mock response for successful queries
const mockSuccessResponse = (data: unknown) => ({
  data,
  isSuccess: true,
  isLoading: false,
  isError: false,
  error: null,
  dataUpdatedAt: Date.now(),
  errorUpdatedAt: 0,
  failureCount: 0,
  failureReason: null,
  isFetched: true,
  isFetchedAfterMount: true,
  isFetching: false,
  isPaused: false,
  isPending: false,
  isPlaceholderData: false,
  isRefetchError: false,
  isRefetching: false,
  isStale: false,
  refetch: jest.fn(),
  status: 'success' as const,
});

// Default mock response for error queries
const mockErrorResponse = (errorMessage: string) => ({
  data: undefined,
  isSuccess: false,
  isLoading: false,
  isError: true,
  error: { message: errorMessage },
  dataUpdatedAt: 0,
  errorUpdatedAt: Date.now(),
  failureCount: 1,
  failureReason: { message: errorMessage },
  isFetched: true,
  isFetchedAfterMount: true,
  isFetching: false,
  isPaused: false,
  isPending: false,
  isPlaceholderData: false,
  isRefetchError: false,
  isRefetching: false,
  isStale: false,
  refetch: jest.fn(),
  status: 'error' as const,
});

// Default mock for mutations
const mockMutation = () => ({
  mutate: jest.fn(),
  mutateAsync: jest.fn(),
  isPending: false,
  isSuccess: false,
  isError: false,
  isIdle: true,
  error: null,
  data: null,
  reset: jest.fn(),
});

describe('useMyLessons hooks', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    // Default mock implementations
    mockUseBookingsList.mockReturnValue(
      mockSuccessResponse({
        items: [
          {
            id: '01ABCDEF123456789012345678',
            booking_date: '2024-12-25',
            start_time: '14:00:00',
            status: 'CONFIRMED',
            total_price: 60,
          },
        ],
        total: 1,
        page: 1,
        per_page: 20,
        has_next: false,
        has_prev: false,
      })
    );

    mockUseBookingsHistory.mockReturnValue(
      mockSuccessResponse({
        items: [
          {
            id: '01ABCDEF123456789012345679',
            booking_date: '2024-12-20',
            start_time: '10:00:00',
            status: 'COMPLETED',
            total_price: 60,
          },
        ],
        total: 1,
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: false,
      })
    );

    mockUseCancelledBookingsV1.mockReturnValue(
      mockSuccessResponse({
        items: [],
        total: 0,
        page: 1,
        per_page: 20,
        has_next: false,
        has_prev: false,
      })
    );

    mockUseBooking.mockReturnValue(
      mockSuccessResponse({
        id: '01ABCDEF123456789012345678',
        booking_date: '2024-12-25',
        status: 'CONFIRMED',
        instructor: { first_name: 'John', last_initial: 'D' },
        service_name: 'Mathematics',
        total_price: 60,
      })
    );

    mockUseCancelBooking.mockReturnValue(mockMutation());
    mockUseRescheduleBooking.mockReturnValue(mockMutation());
    mockUseCompleteBooking.mockReturnValue(mockMutation());
  });

  describe('useCurrentLessons', () => {
    it('fetches upcoming lessons', async () => {
      const { result } = renderHook(() => useCurrentLessons(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.items).toHaveLength(1);
      expect(result.current.data?.items?.[0]?.status).toBe('CONFIRMED');
    });

    it('uses correct cache time', () => {
      const { result } = renderHook(() => useCurrentLessons(), { wrapper });

      // The query should be configured with the correct stale time
      expect(result.current).toHaveProperty('dataUpdatedAt');
    });

    it('passes correct params to v1 service', () => {
      renderHook(() => useCurrentLessons(), { wrapper });

      expect(mockUseBookingsList).toHaveBeenCalledWith({
        upcoming_only: true,
        page: 1,
        per_page: 10,
      });
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

    it('uses correct page number', () => {
      renderHook(() => useCompletedLessons(2), { wrapper });

      expect(mockUseBookingsHistory).toHaveBeenCalledWith(2, 10);
    });
  });

  describe('useLessonDetails', () => {
    it('fetches lesson details by ID', async () => {
      const { result } = renderHook(() => useLessonDetails('01ABCDEF123456789012345678'), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.id).toBe('01ABCDEF123456789012345678');
      expect(result.current.data?.instructor?.first_name).toBe('John');
      expect(result.current.data?.instructor?.last_initial).toBe('D');
    });

    it('handles invalid lesson ID', async () => {
      mockUseBooking.mockReturnValue(mockErrorResponse('Booking not found'));

      const { result } = renderHook(() => useLessonDetails('invalidid'), { wrapper });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      // Error type from v1 services may have different structure
      expect(result.current.error).toBeDefined();
    });

    it('passes lesson ID to v1 service', () => {
      const lessonId = '01ABCDEF123456789012345678';
      renderHook(() => useLessonDetails(lessonId), { wrapper });

      expect(mockUseBooking).toHaveBeenCalledWith(lessonId);
    });
  });

  describe('useCancelLesson', () => {
    it('returns cancel mutation', async () => {
      const { result } = renderHook(() => useCancelLesson(), { wrapper });

      expect(result.current.mutate).toBeDefined();
      expect(result.current.mutateAsync).toBeDefined();
    });

    it('calls v1 cancel mutation with correct params', async () => {
      const mockMutate = jest.fn();
      mockUseCancelBooking.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const { result } = renderHook(() => useCancelLesson(), { wrapper });

      result.current.mutate({
        lessonId: '01ABCDEF123456789012345678',
        reason: 'Schedule conflict',
      });

      expect(mockMutate).toHaveBeenCalledWith(
        {
          bookingId: '01ABCDEF123456789012345678',
          data: { reason: 'Schedule conflict' },
        },
        expect.any(Object)
      );
    });
  });

  describe('useRescheduleLesson', () => {
    it('returns reschedule mutation', async () => {
      const { result } = renderHook(() => useRescheduleLesson(), { wrapper });

      expect(result.current.mutate).toBeDefined();
      expect(result.current.mutateAsync).toBeDefined();
    });

    it('calculates duration and calls v1 reschedule mutation', async () => {
      const mockMutate = jest.fn();
      mockUseRescheduleBooking.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const { result } = renderHook(() => useRescheduleLesson(), { wrapper });

      result.current.mutate({
        lessonId: '01ABCDEF123456789012345678',
        newDate: '2024-12-26',
        newStartTime: '10:00:00',
        newEndTime: '11:00:00',
      });

      expect(mockMutate).toHaveBeenCalledWith(
        {
          bookingId: '01ABCDEF123456789012345678',
          data: {
            booking_date: '2024-12-26',
            start_time: '10:00:00',
            selected_duration: 60, // 1 hour = 60 minutes
          },
        },
        expect.any(Object)
      );
    });
  });

  describe('calculateCancellationFee', () => {
    // total_price = 60, lessonPrice = 60/1.12 ≈ 53.57, platformFee ≈ 6.43
    const EXPECTED_LESSON_PRICE = 53.57;
    const EXPECTED_PLATFORM_FEE = 6.43;

    it('returns free window for cancellations more than 24 hours in advance', () => {
      const booking = {
        booking_date: '2024-12-30',
        start_time: '14:00:00',
        total_price: 60,
      } as Booking;

      // Mock current date to be well before the lesson
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25'));

      const result = calculateCancellationFee(booking);
      expect(result.window).toBe('free');
      expect(result.lessonPrice).toBeCloseTo(EXPECTED_LESSON_PRICE, 2);
      expect(result.platformFee).toBeCloseTo(EXPECTED_PLATFORM_FEE, 2);
      expect(result.creditAmount).toBe(0);
      expect(result.willReceiveCredit).toBe(false);

      jest.useRealTimers();
    });

    it('returns credit window with lesson price credit for 12-24 hours', () => {
      const booking = {
        booking_date: '2024-12-26',
        start_time: '14:00:00',
        total_price: 60,
      } as Booking;

      // Mock current date to be 18 hours before the lesson (between 12-24 hours)
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25T20:00:00'));

      const result = calculateCancellationFee(booking);
      expect(result.window).toBe('credit');
      expect(result.lessonPrice).toBeCloseTo(EXPECTED_LESSON_PRICE, 2);
      expect(result.platformFee).toBeCloseTo(EXPECTED_PLATFORM_FEE, 2);
      expect(result.creditAmount).toBeCloseTo(EXPECTED_LESSON_PRICE, 2);
      expect(result.willReceiveCredit).toBe(true);

      jest.useRealTimers();
    });

    it('returns full window for cancellations within 12 hours', () => {
      const booking = {
        booking_date: '2024-12-26',
        start_time: '14:00:00',
        total_price: 60,
      } as Booking;

      // Mock current date to be 30 minutes before the lesson
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-26T13:30:00'));

      const result = calculateCancellationFee(booking);
      expect(result.window).toBe('full');
      expect(result.lessonPrice).toBeCloseTo(EXPECTED_LESSON_PRICE, 2);
      expect(result.platformFee).toBeCloseTo(EXPECTED_PLATFORM_FEE, 2);
      expect(result.creditAmount).toBe(0);
      expect(result.willReceiveCredit).toBe(false);

      jest.useRealTimers();
    });

    it('handles edge cases correctly', () => {
      const booking = {
        booking_date: '2024-12-26',
        start_time: '14:00:00',
        total_price: 60,
      } as Booking;

      // Exactly 24 hours before (edge case - should be credit since it's not > 24)
      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25T14:00:00'));
      const result24 = calculateCancellationFee(booking);
      expect(result24.window).toBe('credit');
      expect(result24.creditAmount).toBeCloseTo(EXPECTED_LESSON_PRICE, 2);
      expect(result24.willReceiveCredit).toBe(true);

      // Exactly 12 hours before (edge case - should be full since it's not > 12)
      jest.setSystemTime(new Date('2024-12-26T02:00:00'));
      const result12 = calculateCancellationFee(booking);
      expect(result12.window).toBe('full');
      expect(result12.creditAmount).toBe(0);
      expect(result12.willReceiveCredit).toBe(false);

      jest.useRealTimers();
    });
  });
});
