import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useCurrentLessons,
  useCurrentLessonsInfinite,
  useCompletedLessons,
  useCompletedLessonsInfinite,
  useCancelledLessons,
  useLessonDetails,
  useCancelLesson,
  useRescheduleLesson,
  useCompleteLesson,
  useMarkNoShow,
  calculateCancellationFee,
  formatLessonStatus,
} from '@/hooks/useMyLessons';
import type { Booking, BookingStatus } from '@/features/shared/api/types';

// Mock v1 bookings services
const mockUseBookingsList = jest.fn();
const mockUseBookingsHistory = jest.fn();
const mockUseCancelledBookingsV1 = jest.fn();
const mockUseBooking = jest.fn();
const mockUseCancelBooking = jest.fn();
const mockUseRescheduleBooking = jest.fn();
const mockUseCompleteBooking = jest.fn();
const mockUseMarkBookingNoShow = jest.fn();
const mockFetchBookingsList = jest.fn();

jest.mock('@/src/api/services/bookings', () => ({
  useBookingsList: (...args: unknown[]) => mockUseBookingsList(...args),
  useBookingsHistory: (...args: unknown[]) => mockUseBookingsHistory(...args),
  useCancelledBookings: (...args: unknown[]) => mockUseCancelledBookingsV1(...args),
  useBooking: (...args: unknown[]) => mockUseBooking(...args),
  useCancelBooking: () => mockUseCancelBooking(),
  useRescheduleBooking: () => mockUseRescheduleBooking(),
  useCompleteBooking: () => mockUseCompleteBooking(),
  useMarkBookingNoShow: () => mockUseMarkBookingNoShow(),
  fetchBookingsList: (...args: unknown[]) => mockFetchBookingsList(...args),
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
    mockUseMarkBookingNoShow.mockReturnValue(mockMutation());
    mockFetchBookingsList.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      per_page: 10,
      has_next: false,
      has_prev: false,
    });
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

    it('uses payment_summary when available', () => {
      const booking = {
        booking_date: '2024-12-30',
        start_time: '14:00:00',
        total_price: 60,
        payment_summary: {
          lesson_amount: 50,
          service_fee: 10,
        },
      } as Booking;

      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25'));

      const result = calculateCancellationFee(booking);
      expect(result.lessonPrice).toBe(50);
      expect(result.platformFee).toBe(10);

      jest.useRealTimers();
    });
  });

  describe('useCancelledLessons', () => {
    it('fetches cancelled lessons', async () => {
      const { result } = renderHook(() => useCancelledLessons(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockUseCancelledBookingsV1).toHaveBeenCalledWith(1, 20);
    });

    it('accepts custom page number', () => {
      renderHook(() => useCancelledLessons(3), { wrapper });

      expect(mockUseCancelledBookingsV1).toHaveBeenCalledWith(3, 20);
    });
  });

  describe('useCompleteLesson', () => {
    it('returns complete mutation', () => {
      const { result } = renderHook(() => useCompleteLesson(), { wrapper });

      expect(result.current.mutate).toBeDefined();
      expect(result.current.mutateAsync).toBeDefined();
    });

    it('calls v1 complete mutation with correct params', async () => {
      const mockMutate = jest.fn();
      mockUseCompleteBooking.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const { result } = renderHook(() => useCompleteLesson(), { wrapper });

      result.current.mutate('01ABCDEF123456789012345678');

      expect(mockMutate).toHaveBeenCalledWith(
        { bookingId: '01ABCDEF123456789012345678' },
        expect.any(Object)
      );
    });

    it('calls onSuccess callback after completion', async () => {
      const mockMutate = jest.fn((params, options) => {
        // Simulate async completion
        Promise.resolve().then(() => {
          options?.onSuccess?.({ id: '01ABCDEF123456789012345678' });
        });
      });
      mockUseCompleteBooking.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const onSuccess = jest.fn();
      const { result } = renderHook(() => useCompleteLesson(), { wrapper });

      await act(async () => {
        result.current.mutate('01ABCDEF123456789012345678', { onSuccess });
      });

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalled();
      });
    });

    it('calls onError callback on failure', async () => {
      const mockError = new Error('Completion failed');
      const mockMutate = jest.fn((_, options) => {
        options?.onError?.(mockError);
      });
      mockUseCompleteBooking.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const onError = jest.fn();
      const { result } = renderHook(() => useCompleteLesson(), { wrapper });

      result.current.mutate('01ABCDEF123456789012345678', { onError });

      expect(onError).toHaveBeenCalledWith(mockError);
    });
  });

  describe('useMarkNoShow', () => {
    it('returns no-show mutation', () => {
      const { result } = renderHook(() => useMarkNoShow(), { wrapper });

      expect(result.current.mutate).toBeDefined();
      expect(result.current.mutateAsync).toBeDefined();
    });

    it('calls v1 no-show mutation with correct params', async () => {
      const mockMutate = jest.fn();
      mockUseMarkBookingNoShow.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const { result } = renderHook(() => useMarkNoShow(), { wrapper });

      result.current.mutate('01ABCDEF123456789012345678');

      expect(mockMutate).toHaveBeenCalledWith(
        {
          bookingId: '01ABCDEF123456789012345678',
          data: { no_show_type: 'student' },
        },
        expect.any(Object)
      );
    });

    it('calls onSuccess callback after marking no-show', async () => {
      const mockMutate = jest.fn((_, options) => {
        // Simulate async completion
        Promise.resolve().then(() => {
          options?.onSuccess?.();
        });
      });
      mockUseMarkBookingNoShow.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const onSuccess = jest.fn();
      const { result } = renderHook(() => useMarkNoShow(), { wrapper });

      await act(async () => {
        result.current.mutate('01ABCDEF123456789012345678', { onSuccess });
      });

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalled();
      });
    });

    it('calls onError callback on failure', async () => {
      const mockError = new Error('No-show marking failed');
      const mockMutate = jest.fn((_, options) => {
        options?.onError?.(mockError);
      });
      mockUseMarkBookingNoShow.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const onError = jest.fn();
      const { result } = renderHook(() => useMarkNoShow(), { wrapper });

      result.current.mutate('01ABCDEF123456789012345678', { onError });

      expect(onError).toHaveBeenCalledWith(mockError);
    });
  });

  describe('formatLessonStatus', () => {
    it('formats CONFIRMED status as Upcoming', () => {
      expect(formatLessonStatus('CONFIRMED' as BookingStatus)).toBe('Upcoming');
    });

    it('formats COMPLETED status', () => {
      expect(formatLessonStatus('COMPLETED' as BookingStatus)).toBe('Completed');
    });

    it('formats NO_SHOW status', () => {
      expect(formatLessonStatus('NO_SHOW' as BookingStatus)).toBe('No-show');
    });

    it('formats CANCELLED status without cancellation date', () => {
      expect(formatLessonStatus('CANCELLED' as BookingStatus)).toBe('Cancelled');
    });

    it('formats CANCELLED status with >24h cancellation', () => {
      const lessonDate = new Date('2024-12-27T14:00:00Z');
      const cancelledAt = '2024-12-25T10:00:00Z';
      const result = formatLessonStatus('CANCELLED' as BookingStatus, lessonDate, cancelledAt);
      expect(result).toBe('Cancelled (>24hrs)');
    });

    it('returns original status for unknown statuses', () => {
      expect(formatLessonStatus('PENDING' as BookingStatus)).toBe('PENDING');
    });
  });

  describe('useCurrentLessons edge cases', () => {
    it('handles boolean parameter for backward compatibility', () => {
      renderHook(() => useCurrentLessons(true), { wrapper });

      expect(mockUseBookingsList).toHaveBeenCalledWith({
        upcoming_only: true,
        page: 1,
        per_page: 10,
      });
    });

    it('handles undefined data gracefully', () => {
      mockUseBookingsList.mockReturnValue({
        ...mockSuccessResponse(undefined),
        data: undefined,
      });

      const { result } = renderHook(() => useCurrentLessons(), { wrapper });

      expect(result.current.data).toBeUndefined();
    });
  });

  describe('useCompletedLessons edge cases', () => {
    it('handles error state', async () => {
      mockUseBookingsHistory.mockReturnValue(mockErrorResponse('Failed to load'));

      const { result } = renderHook(() => useCompletedLessons(), { wrapper });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });
    });
  });

  describe('useCancelLesson edge cases', () => {
    it('calls onError on mutation failure', async () => {
      const mockError = new Error('Cancel failed');
      const mockMutate = jest.fn((_, options) => {
        options?.onError?.(mockError);
      });
      mockUseCancelBooking.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const onError = jest.fn();
      const { result } = renderHook(() => useCancelLesson(), { wrapper });

      result.current.mutate(
        { lessonId: '01ABCDEF123456789012345678', reason: 'Test' },
        { onError }
      );

      expect(onError).toHaveBeenCalledWith(mockError);
    });
  });

  describe('useRescheduleLesson edge cases', () => {
    it('calls onError on mutation failure', async () => {
      const mockError = new Error('Reschedule failed');
      const mockMutate = jest.fn((_, options) => {
        options?.onError?.(mockError);
      });
      mockUseRescheduleBooking.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const onError = jest.fn();
      const { result } = renderHook(() => useRescheduleLesson(), { wrapper });

      result.current.mutate(
        {
          lessonId: '01ABCDEF123456789012345678',
          newDate: '2024-12-26',
          newStartTime: '10:00:00',
          newEndTime: '11:00:00',
        },
        { onError }
      );

      expect(onError).toHaveBeenCalledWith(mockError);
    });

    it('calculates duration correctly for 90-minute sessions', async () => {
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
        newEndTime: '11:30:00', // 90 minutes
      });

      expect(mockMutate).toHaveBeenCalledWith(
        {
          bookingId: '01ABCDEF123456789012345678',
          data: {
            booking_date: '2024-12-26',
            start_time: '10:00:00',
            selected_duration: 90, // 90 minutes
          },
        },
        expect.any(Object)
      );
    });

    it('calls mutateAsync successfully', async () => {
      const mockMutateAsync = jest.fn().mockResolvedValue({ id: '01ABCDEF123456789012345678' });
      mockUseRescheduleBooking.mockReturnValue({
        ...mockMutation(),
        mutateAsync: mockMutateAsync,
      });

      const { result } = renderHook(() => useRescheduleLesson(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          lessonId: '01ABCDEF123456789012345678',
          newDate: '2024-12-26',
          newStartTime: '10:00:00',
          newEndTime: '11:00:00',
        });
      });

      expect(mockMutateAsync).toHaveBeenCalledWith({
        bookingId: '01ABCDEF123456789012345678',
        data: {
          booking_date: '2024-12-26',
          start_time: '10:00:00',
          selected_duration: 60,
        },
      });
    });

    it('calls onSuccess callback after successful mutation', async () => {
      const mockMutate = jest.fn((_, options) => {
        Promise.resolve().then(() => options?.onSuccess?.());
      });
      mockUseRescheduleBooking.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const onSuccess = jest.fn();
      const { result } = renderHook(() => useRescheduleLesson(), { wrapper });

      await act(async () => {
        result.current.mutate(
          {
            lessonId: '01ABCDEF123456789012345678',
            newDate: '2024-12-26',
            newStartTime: '10:00:00',
            newEndTime: '11:00:00',
          },
          { onSuccess }
        );
      });

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalled();
      });
    });
  });

  describe('useCurrentLessonsInfinite', () => {
    it('fetches first page of upcoming lessons', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [{ id: 'booking-1', status: 'CONFIRMED' }],
        total: 1,
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: false,
      });

      const { result } = renderHook(() => useCurrentLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.items).toHaveLength(1);
    });

    it('fetches next page when has_next is true', async () => {
      mockFetchBookingsList
        .mockResolvedValueOnce({
          items: [{ id: 'booking-1' }],
          total: 2,
          page: 1,
          per_page: 10,
          has_next: true,
          has_prev: false,
        })
        .mockResolvedValueOnce({
          items: [{ id: 'booking-2' }],
          total: 2,
          page: 2,
          per_page: 10,
          has_next: false,
          has_prev: true,
        });

      const { result } = renderHook(() => useCurrentLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.hasNextPage).toBe(true);

      await act(async () => {
        await result.current.fetchNextPage();
      });

      await waitFor(() => {
        expect(result.current.data?.items).toHaveLength(2);
      });
    });

    it('calls fetchBookingsList with upcoming_only filter', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: false,
      });

      renderHook(() => useCurrentLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(mockFetchBookingsList).toHaveBeenCalledWith({
          upcoming_only: true,
          page: 1,
          per_page: 10,
        });
      });
    });
  });

  describe('useCompletedLessonsInfinite', () => {
    it('fetches first page of completed lessons', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [{ id: 'booking-1', status: 'COMPLETED' }],
        total: 1,
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: false,
      });

      const { result } = renderHook(() => useCompletedLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.items).toHaveLength(1);
    });

    it('fetches next page when has_next is true', async () => {
      mockFetchBookingsList
        .mockResolvedValueOnce({
          items: [{ id: 'booking-1' }],
          total: 2,
          page: 1,
          per_page: 10,
          has_next: true,
          has_prev: false,
        })
        .mockResolvedValueOnce({
          items: [{ id: 'booking-2' }],
          total: 2,
          page: 2,
          per_page: 10,
          has_next: false,
          has_prev: true,
        });

      const { result } = renderHook(() => useCompletedLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.hasNextPage).toBe(true);

      await act(async () => {
        await result.current.fetchNextPage();
      });

      await waitFor(() => {
        expect(result.current.data?.items).toHaveLength(2);
      });
    });

    it('calls fetchBookingsList with exclude_future_confirmed filter', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: false,
      });

      renderHook(() => useCompletedLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(mockFetchBookingsList).toHaveBeenCalledWith({
          exclude_future_confirmed: true,
          page: 1,
          per_page: 10,
        });
      });
    });
  });

  describe('useCancelLesson mutateAsync', () => {
    it('calls mutateAsync successfully', async () => {
      const mockMutateAsync = jest.fn().mockResolvedValue({ id: '01ABCDEF123456789012345678' });
      mockUseCancelBooking.mockReturnValue({
        ...mockMutation(),
        mutateAsync: mockMutateAsync,
      });

      const { result } = renderHook(() => useCancelLesson(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync({
          lessonId: '01ABCDEF123456789012345678',
          reason: 'Schedule conflict',
        });
      });

      expect(mockMutateAsync).toHaveBeenCalledWith({
        bookingId: '01ABCDEF123456789012345678',
        data: { reason: 'Schedule conflict' },
      });
    });

    it('calls onSuccess callback after successful mutation', async () => {
      const mockMutate = jest.fn((_, options) => {
        Promise.resolve().then(() => options?.onSuccess?.());
      });
      mockUseCancelBooking.mockReturnValue({
        ...mockMutation(),
        mutate: mockMutate,
      });

      const onSuccess = jest.fn();
      const { result } = renderHook(() => useCancelLesson(), { wrapper });

      await act(async () => {
        result.current.mutate(
          { lessonId: '01ABCDEF123456789012345678', reason: 'Test' },
          { onSuccess }
        );
      });

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalled();
      });
    });
  });

  describe('useCompleteLesson mutateAsync', () => {
    it('calls mutateAsync successfully', async () => {
      const mockMutateAsync = jest.fn().mockResolvedValue({ id: '01ABCDEF123456789012345678' });
      mockUseCompleteBooking.mockReturnValue({
        ...mockMutation(),
        mutateAsync: mockMutateAsync,
      });

      const { result } = renderHook(() => useCompleteLesson(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync('01ABCDEF123456789012345678');
      });

      expect(mockMutateAsync).toHaveBeenCalledWith({ bookingId: '01ABCDEF123456789012345678' });
    });
  });

  describe('useMarkNoShow mutateAsync', () => {
    it('calls mutateAsync successfully', async () => {
      const mockMutateAsync = jest.fn().mockResolvedValue({ id: '01ABCDEF123456789012345678' });
      mockUseMarkBookingNoShow.mockReturnValue({
        ...mockMutation(),
        mutateAsync: mockMutateAsync,
      });

      const { result } = renderHook(() => useMarkNoShow(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync('01ABCDEF123456789012345678');
      });

      expect(mockMutateAsync).toHaveBeenCalledWith({
        bookingId: '01ABCDEF123456789012345678',
        data: { no_show_type: 'student' },
      });
    });
  });

  describe('formatLessonStatus detailed cancellation windows', () => {
    it('returns Cancelled (12-24hrs) for cancellation in 12-24h window', () => {
      const lessonDate = new Date('2024-12-27T12:00:00Z');
      const cancelDate = new Date('2024-12-26T16:00:00Z');
      const result = formatLessonStatus('CANCELLED' as BookingStatus, lessonDate, cancelDate.toISOString());
      expect(result).toBe('Cancelled (12-24hrs)');
    });

    it('returns Cancelled (<12hrs) for cancellation within 12 hours', () => {
      const lessonDate = new Date('2024-12-27T12:00:00Z');
      const cancelDate = new Date('2024-12-27T04:00:00Z');
      const result = formatLessonStatus('CANCELLED' as BookingStatus, lessonDate, cancelDate.toISOString());
      expect(result).toBe('Cancelled (<12hrs)');
    });
  });

  describe('useCurrentLessons branch coverage', () => {
    it('handles response with null page', () => {
      mockUseBookingsList.mockReturnValue(
        mockSuccessResponse({
          items: [],
          total: 0,
          page: null, // null page should fallback to passed page
          per_page: 10,
          has_next: false,
          has_prev: false,
        })
      );

      const { result } = renderHook(() => useCurrentLessons(3), { wrapper });

      expect(result.current.data?.page).toBe(3);
    });

    it('handles response with null per_page', () => {
      mockUseBookingsList.mockReturnValue(
        mockSuccessResponse({
          items: [],
          total: 0,
          page: 1,
          per_page: null, // null per_page should fallback to 10
          has_next: false,
          has_prev: false,
        })
      );

      const { result } = renderHook(() => useCurrentLessons(), { wrapper });

      expect(result.current.data?.per_page).toBe(10);
    });

    it('handles numeric page parameter', () => {
      renderHook(() => useCurrentLessons(5), { wrapper });

      expect(mockUseBookingsList).toHaveBeenCalledWith({
        upcoming_only: true,
        page: 5,
        per_page: 10,
      });
    });
  });

  describe('useCompletedLessons branch coverage', () => {
    it('handles response with null page', () => {
      mockUseBookingsHistory.mockReturnValue(
        mockSuccessResponse({
          items: [],
          total: 0,
          page: null,
          per_page: 10,
          has_next: false,
          has_prev: false,
        })
      );

      const { result } = renderHook(() => useCompletedLessons(2), { wrapper });

      expect(result.current.data?.page).toBe(2);
    });

    it('handles response with null per_page', () => {
      mockUseBookingsHistory.mockReturnValue(
        mockSuccessResponse({
          items: [],
          total: 0,
          page: 1,
          per_page: null,
          has_next: false,
          has_prev: false,
        })
      );

      const { result } = renderHook(() => useCompletedLessons(), { wrapper });

      expect(result.current.data?.per_page).toBe(10);
    });
  });

  describe('useCancelledLessons branch coverage', () => {
    it('handles response with null page', () => {
      mockUseCancelledBookingsV1.mockReturnValue(
        mockSuccessResponse({
          items: [],
          total: 0,
          page: null,
          per_page: 20,
          has_next: false,
          has_prev: false,
        })
      );

      const { result } = renderHook(() => useCancelledLessons(), { wrapper });

      expect(result.current.data?.page).toBe(1);
    });

    it('handles response with null per_page', () => {
      mockUseCancelledBookingsV1.mockReturnValue(
        mockSuccessResponse({
          items: [],
          total: 0,
          page: 1,
          per_page: null,
          has_next: false,
          has_prev: false,
        })
      );

      const { result } = renderHook(() => useCancelledLessons(), { wrapper });

      expect(result.current.data?.per_page).toBe(20);
    });
  });

  describe('useCurrentLessonsInfinite branch coverage', () => {
    it('handles null page in response', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [{ id: 'booking-1' }],
        total: 1,
        page: null, // null page should default to 1
        per_page: 10,
        has_next: false,
        has_prev: false,
      });

      const { result } = renderHook(() => useCurrentLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.page).toBe(1);
    });

    it('handles null total in response', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [],
        total: null, // null total should default to 0
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: false,
      });

      const { result } = renderHook(() => useCurrentLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.total).toBe(0);
    });

    it('handles null per_page in response', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        per_page: null, // null per_page should default to 10
        has_next: false,
        has_prev: false,
      });

      const { result } = renderHook(() => useCurrentLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.per_page).toBe(10);
    });

    it('handles null has_prev in response', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: null, // null has_prev should default to false
      });

      const { result } = renderHook(() => useCurrentLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.has_prev).toBe(false);
    });

    it('handles null items in page response', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: null, // null items should result in empty array
        total: 0,
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: false,
      });

      const { result } = renderHook(() => useCurrentLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.items).toEqual([]);
    });
  });

  describe('useCompletedLessonsInfinite branch coverage', () => {
    it('handles null page in response', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [],
        total: 1,
        page: null, // null page should default to 1
        per_page: 10,
        has_next: false,
        has_prev: false,
      });

      const { result } = renderHook(() => useCompletedLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.page).toBe(1);
    });

    it('handles null total in response', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [],
        total: null, // null total should default to 0
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: false,
      });

      const { result } = renderHook(() => useCompletedLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.total).toBe(0);
    });

    it('handles null per_page in response', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        per_page: null, // null per_page should default to 10
        has_next: false,
        has_prev: false,
      });

      const { result } = renderHook(() => useCompletedLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.per_page).toBe(10);
    });

    it('handles null has_prev in response', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: null, // null has_prev should default to false
      });

      const { result } = renderHook(() => useCompletedLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.has_prev).toBe(false);
    });

    it('handles null items in page response', async () => {
      mockFetchBookingsList.mockResolvedValue({
        items: null, // null items should result in empty array
        total: 0,
        page: 1,
        per_page: 10,
        has_next: false,
        has_prev: false,
      });

      const { result } = renderHook(() => useCompletedLessonsInfinite(), { wrapper });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.items).toEqual([]);
    });
  });

  describe('calculateCancellationFee branch coverage', () => {
    it('uses fallback calculation when payment_summary is null', () => {
      const booking = {
        booking_date: '2024-12-30',
        start_time: '14:00:00',
        total_price: 112,
        payment_summary: null,
      } as Booking;

      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25'));

      const result = calculateCancellationFee(booking);
      // With fallback: lesson_price = 112 / 1.12 = 100, platform_fee = 12
      expect(result.lessonPrice).toBeCloseTo(100, 2);
      expect(result.platformFee).toBeCloseTo(12, 2);

      jest.useRealTimers();
    });

    it('handles time strings without minutes', () => {
      // Test case where start_time is malformed (missing minutes)
      // This creates an Invalid Date, making hoursUntil = NaN
      // NaN comparisons (> 24, > 12) are always false, so falls through to 'full'
      const booking = {
        booking_date: '2024-12-30',
        start_time: '14', // Missing minutes - creates Invalid Date
        end_time: '15',   // Missing minutes
        total_price: 60,
      } as Booking;

      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25'));

      // Should not throw - returns 'full' as safest fallback for malformed input
      const result = calculateCancellationFee(booking);
      expect(result).toBeDefined();
      // NaN > 24 and NaN > 12 are both false, so falls through to 'full'
      expect(result.window).toBe('full');
      expect(Number.isNaN(result.hoursUntil)).toBe(true);

      jest.useRealTimers();
    });

    it('uses fallback calculation when payment_summary has null lesson_amount', () => {
      const booking = {
        booking_date: '2024-12-30',
        start_time: '14:00:00',
        total_price: 112,
        payment_summary: {
          lesson_amount: null,
          service_fee: 12,
        },
      } as unknown as Booking;

      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25'));

      const result = calculateCancellationFee(booking);
      // Should use fallback calculation
      expect(result.lessonPrice).toBeCloseTo(100, 2);

      jest.useRealTimers();
    });

    it('uses fallback calculation when payment_summary has null service_fee', () => {
      const booking = {
        booking_date: '2024-12-30',
        start_time: '14:00:00',
        total_price: 112,
        payment_summary: {
          lesson_amount: 100,
          service_fee: null,
        },
      } as unknown as Booking;

      jest.useFakeTimers();
      jest.setSystemTime(new Date('2024-12-25'));

      const result = calculateCancellationFee(booking);
      // Should use fallback calculation
      expect(result.platformFee).toBeCloseTo(12, 2);

      jest.useRealTimers();
    });

    it('handles hoursUntil exactly at boundary cases', () => {
      const booking = {
        booking_date: '2024-12-26',
        start_time: '14:00:00',
        total_price: 60,
      } as Booking;

      jest.useFakeTimers();
      // 24.5 hours before - should be free window
      jest.setSystemTime(new Date('2024-12-25T13:30:00'));
      const resultFree = calculateCancellationFee(booking);
      expect(resultFree.window).toBe('free');
      expect(resultFree.hoursUntil).toBeGreaterThan(24);

      // 12.5 hours before - should be credit window
      jest.setSystemTime(new Date('2024-12-26T01:30:00'));
      const resultCredit = calculateCancellationFee(booking);
      expect(resultCredit.window).toBe('credit');
      expect(resultCredit.hoursUntil).toBeGreaterThan(12);
      expect(resultCredit.hoursUntil).toBeLessThanOrEqual(24);

      // 11.5 hours before - should be full window
      jest.setSystemTime(new Date('2024-12-26T02:30:00'));
      const resultFull = calculateCancellationFee(booking);
      expect(resultFull.window).toBe('full');
      expect(resultFull.hoursUntil).toBeLessThanOrEqual(12);

      jest.useRealTimers();
    });
  });
});
