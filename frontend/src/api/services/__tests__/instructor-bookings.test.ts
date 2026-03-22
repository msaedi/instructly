import { renderHook } from '@testing-library/react';

import { queryKeys } from '@/src/api/queryKeys';
import {
  useGetCompletedBookingsApiV1InstructorBookingsCompletedGet,
  useGetPendingCompletionBookingsApiV1InstructorBookingsPendingCompletionGet,
  useGetUpcomingBookingsApiV1InstructorBookingsUpcomingGet,
  useListInstructorBookingsApiV1InstructorBookingsGet,
} from '@/src/api/generated/instructor-bookings-v1/instructor-bookings-v1';

import {
  useInstructorBookingsList,
  useInstructorUpcomingBookings,
  useInstructorCompletedBookings,
  usePendingCompletionBookings,
} from '../instructor-bookings';

jest.mock('@/src/api/generated/instructor-bookings-v1/instructor-bookings-v1', () => ({
  useListInstructorBookingsApiV1InstructorBookingsGet: jest.fn(),
  useGetPendingCompletionBookingsApiV1InstructorBookingsPendingCompletionGet: jest.fn(),
  useGetUpcomingBookingsApiV1InstructorBookingsUpcomingGet: jest.fn(),
  useGetCompletedBookingsApiV1InstructorBookingsCompletedGet: jest.fn(),
}));

const baseResult = {
  data: undefined,
  isLoading: false,
  isError: false,
  error: null,
  refetch: jest.fn(),
};

const listHookMock =
  useListInstructorBookingsApiV1InstructorBookingsGet as jest.MockedFunction<
    typeof useListInstructorBookingsApiV1InstructorBookingsGet
  >;
const pendingHookMock =
  useGetPendingCompletionBookingsApiV1InstructorBookingsPendingCompletionGet as jest.MockedFunction<
    typeof useGetPendingCompletionBookingsApiV1InstructorBookingsPendingCompletionGet
  >;
const upcomingHookMock =
  useGetUpcomingBookingsApiV1InstructorBookingsUpcomingGet as jest.MockedFunction<
    typeof useGetUpcomingBookingsApiV1InstructorBookingsUpcomingGet
  >;
const completedHookMock =
  useGetCompletedBookingsApiV1InstructorBookingsCompletedGet as jest.MockedFunction<
    typeof useGetCompletedBookingsApiV1InstructorBookingsCompletedGet
  >;

describe('instructor bookings service query keys', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    listHookMock.mockReturnValue(baseResult as never);
    pendingHookMock.mockReturnValue(baseResult as never);
    upcomingHookMock.mockReturnValue(baseResult as never);
    completedHookMock.mockReturnValue(baseResult as never);
  });

  it('includes all list filters that affect instructor booking results in the query key', () => {
    const params = {
      status: 'CONFIRMED' as const,
      upcoming: false,
      exclude_future_confirmed: true,
      include_past_confirmed: true,
      page: 2,
      per_page: 25,
    };

    renderHook(() => useInstructorBookingsList(params));

    expect(listHookMock).toHaveBeenCalledWith(
      params,
      expect.objectContaining({
        query: expect.objectContaining({
          queryKey: queryKeys.bookings.instructor(params),
        }),
      })
    );
  });

  it('produces distinct cache keys for upcoming and past instructor booking list queries', () => {
    const upcomingParams = { upcoming: true, page: 1, per_page: 50 };
    const pastParams = {
      upcoming: false,
      exclude_future_confirmed: true,
      page: 1,
      per_page: 50,
    };

    renderHook(() => useInstructorBookingsList(upcomingParams));
    renderHook(() => useInstructorBookingsList(pastParams));

    const upcomingKey = listHookMock.mock.calls[0]?.[1]?.query?.queryKey;
    const pastKey = listHookMock.mock.calls[1]?.[1]?.query?.queryKey;

    expect(upcomingKey).toEqual(queryKeys.bookings.instructor(upcomingParams));
    expect(pastKey).toEqual(queryKeys.bookings.instructor(pastParams));
    expect(upcomingKey).not.toEqual(pastKey);
  });

  it('includes pagination in specialized instructor booking query keys', () => {
    renderHook(() => usePendingCompletionBookings(4, 10));
    renderHook(() => useInstructorUpcomingBookings(2, 25));
    renderHook(() => useInstructorCompletedBookings(3, 15));

    expect(pendingHookMock).toHaveBeenCalledWith(
      { page: 4, per_page: 10 },
      expect.objectContaining({
        query: expect.objectContaining({
          queryKey: queryKeys.bookings.instructor({
            status: 'pending-completion',
            page: 4,
            per_page: 10,
          }),
        }),
      })
    );

    expect(upcomingHookMock).toHaveBeenCalledWith(
      { page: 2, per_page: 25 },
      expect.objectContaining({
        query: expect.objectContaining({
          queryKey: queryKeys.bookings.instructor({
            status: 'upcoming',
            page: 2,
            per_page: 25,
          }),
        }),
      })
    );

    expect(completedHookMock).toHaveBeenCalledWith(
      { page: 3, per_page: 15 },
      expect.objectContaining({
        query: expect.objectContaining({
          queryKey: queryKeys.bookings.instructor({
            status: 'completed',
            page: 3,
            per_page: 15,
          }),
        }),
      })
    );
  });
});
