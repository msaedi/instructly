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

  it('returns empty page when disabled', async () => {
    const { result } = renderHook(() => useInstructorBookings({ enabled: false }));

    expect(result.current.data?.items).toEqual([]);
    expect(result.current.isLoading).toBe(false);

    // Verify refetch returns EMPTY_PAGE
    const refetchResult = await result.current.refetch();
    expect(refetchResult.data?.items).toEqual([]);
    expect(refetchResult.data?.total).toBe(0);
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

  it('returns EMPTY_PAGE when upcoming endpoint data is null', () => {
    upcomingMock.mockReturnValue({
      ...baseResult,
      data: null,
    });

    const { result } = renderHook(() =>
      useInstructorBookings({ status: 'CONFIRMED', upcoming: true, page: 3, perPage: 20 })
    );

    expect(result.current.data).toEqual({
      items: [],
      total: 0,
      page: 3,
      per_page: 20,
      has_next: false,
      has_prev: false,
    });
  });

  it('returns EMPTY_PAGE when completed endpoint data is null', () => {
    completedMock.mockReturnValue({
      ...baseResult,
      data: null,
    });

    const { result } = renderHook(() =>
      useInstructorBookings({ status: 'COMPLETED', upcoming: false, page: 2, perPage: 25 })
    );

    expect(result.current.data).toEqual({
      items: [],
      total: 0,
      page: 2,
      per_page: 25,
      has_next: false,
      has_prev: false,
    });
  });

  it('returns EMPTY_PAGE when list endpoint data is null', () => {
    listMock.mockReturnValue({
      ...baseResult,
      data: null,
    });

    const { result } = renderHook(() =>
      useInstructorBookings({ status: 'PENDING', page: 4, perPage: 15 })
    );

    expect(result.current.data).toEqual({
      items: [],
      total: 0,
      page: 4,
      per_page: 15,
      has_next: false,
      has_prev: false,
    });
  });

  it('uses fallback values when API response omits page and per_page fields', () => {
    upcomingMock.mockReturnValue({
      ...baseResult,
      data: {
        items: [{ id: 'b4' }],
        total: 1,
        page: undefined,
        per_page: undefined,
        has_next: false,
        has_prev: false,
      },
    });

    const { result } = renderHook(() =>
      useInstructorBookings({ status: 'CONFIRMED', upcoming: true, page: 5, perPage: 30 })
    );

    // The ?? fallback should use the provided page/perPage values
    expect(result.current.data?.page).toBe(5);
    expect(result.current.data?.per_page).toBe(30);
    expect(result.current.data?.items).toHaveLength(1);
  });

  it('uses fallback values for completed endpoint when page/per_page missing', () => {
    completedMock.mockReturnValue({
      ...baseResult,
      data: {
        items: [],
        total: 0,
        page: undefined,
        per_page: undefined,
        has_next: false,
        has_prev: false,
      },
    });

    const { result } = renderHook(() =>
      useInstructorBookings({ status: 'COMPLETED', upcoming: false, page: 7, perPage: 10 })
    );

    expect(result.current.data?.page).toBe(7);
    expect(result.current.data?.per_page).toBe(10);
  });

  it('uses fallback values for list endpoint when page/per_page missing', () => {
    listMock.mockReturnValue({
      ...baseResult,
      data: {
        items: [{ id: 'b5' }],
        total: 1,
        page: undefined,
        per_page: undefined,
        has_next: false,
        has_prev: false,
      },
    });

    const { result } = renderHook(() =>
      useInstructorBookings({ status: 'PENDING', page: 3, perPage: 40 })
    );

    expect(result.current.data?.page).toBe(3);
    expect(result.current.data?.per_page).toBe(40);
  });

  it('uses list endpoint when only status is set (no upcoming flag)', () => {
    listMock.mockReturnValue({
      ...baseResult,
      data: {
        items: [{ id: 'b6' }],
        total: 1,
        page: 1,
        per_page: 50,
        has_next: false,
        has_prev: false,
      },
    });

    const { result } = renderHook(() =>
      useInstructorBookings({ status: 'CONFIRMED' })
    );

    // Without upcoming=true, CONFIRMED alone should route to the list endpoint
    expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'CONFIRMED' }),
      { enabled: true }
    );
    expect(result.current.data?.items).toHaveLength(1);
  });

  it('omits excludeFutureConfirmed from params when undefined', () => {
    listMock.mockReturnValue(baseResult);

    renderHook(() =>
      useInstructorBookings({ status: 'PENDING', upcoming: true, excludeFutureConfirmed: undefined })
    );

    const listParams = listMock.mock.calls[0]?.[0] as Record<string, unknown> | undefined;
    expect(listParams).not.toHaveProperty('exclude_future_confirmed');
  });
});
