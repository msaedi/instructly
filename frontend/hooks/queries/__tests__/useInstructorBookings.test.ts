import { renderHook } from '@testing-library/react';
import { useInstructorBookings } from '../useInstructorBookings';
import {
  useInstructorBookingsList,
  useInstructorUpcomingBookings,
  useInstructorCompletedBookings,
} from '@/src/api/services/instructor-bookings';

jest.mock('@/src/api/services/instructor-bookings', () => ({
  useInstructorBookingsList: jest.fn(),
  useInstructorUpcomingBookings: jest.fn(),
  useInstructorCompletedBookings: jest.fn(),
}));

const listMock = useInstructorBookingsList as jest.Mock;
const upcomingMock = useInstructorUpcomingBookings as jest.Mock;
const completedMock = useInstructorCompletedBookings as jest.Mock;

const baseResult = {
  data: {
    items: [],
    total: 0,
    page: 1,
    per_page: 50,
    has_next: false,
    has_prev: false,
  },
  isLoading: false,
  isError: false,
  error: null,
  refetch: jest.fn(),
};

describe('useInstructorBookings', () => {
  beforeEach(() => {
    listMock.mockReset();
    upcomingMock.mockReset();
    completedMock.mockReset();
    listMock.mockReturnValue(baseResult);
    upcomingMock.mockReturnValue(baseResult);
    completedMock.mockReturnValue(baseResult);
  });

  it('returns empty page when disabled', () => {
    const { result } = renderHook(() => useInstructorBookings({ enabled: false }));

    expect(result.current.data?.items).toEqual([]);
    expect(result.current.isLoading).toBe(false);
  });

  it('uses upcoming bookings endpoint for confirmed upcoming', () => {
    upcomingMock.mockReturnValue({
      ...baseResult,
      data: {
        items: [{ id: 'b1' }],
        total: 1,
        page: 2,
        per_page: 10,
        has_next: true,
        has_prev: false,
      },
    });

    const { result } = renderHook(() =>
      useInstructorBookings({ status: 'CONFIRMED', upcoming: true, page: 2, perPage: 10 })
    );

    expect(upcomingMock).toHaveBeenCalledWith(2, 10, { enabled: true });
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.page).toBe(2);
  });

  it('uses completed bookings endpoint for completed past', () => {
    completedMock.mockReturnValue({
      ...baseResult,
      data: {
        items: [{ id: 'b2' }],
        total: 1,
        page: 1,
        per_page: 50,
        has_next: false,
        has_prev: false,
      },
    });

    const { result } = renderHook(() =>
      useInstructorBookings({ status: 'COMPLETED', upcoming: false })
    );

    expect(completedMock).toHaveBeenCalledWith(1, 50, { enabled: true });
    expect(result.current.data?.items[0]?.id).toBe('b2');
  });

  it('uses list endpoint for other filters and caps perPage', () => {
    listMock.mockReturnValue({
      ...baseResult,
      data: {
        items: [{ id: 'b3' }],
        total: 1,
        page: 1,
        per_page: 100,
        has_next: false,
        has_prev: false,
      },
    });

    const { result } = renderHook(() =>
      useInstructorBookings({ status: 'PENDING', upcoming: true, perPage: 150, excludeFutureConfirmed: true })
    );

    expect(listMock).toHaveBeenCalledWith(
      {
        status: 'PENDING',
        upcoming: true,
        exclude_future_confirmed: true,
        page: 1,
        per_page: 100,
      },
      { enabled: true }
    );
    expect(result.current.data?.per_page).toBe(100);
  });
});
