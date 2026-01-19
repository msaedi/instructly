import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useInstructorAvailability } from '../useInstructorAvailability';
import { publicApi } from '@/features/shared/api/client';
import { queryKeys } from '@/lib/react-query/queryClient';

jest.mock('@/lib/logger', () => ({
  logger: {
    info: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    warn: jest.fn(),
  },
}));

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getInstructorAvailability: jest.fn().mockResolvedValue({
      status: 200,
      data: {
        instructor_id: 'inst-1',
        instructor_first_name: null,
        instructor_last_initial: null,
        availability_by_date: {},
        timezone: 'UTC',
        total_available_slots: 0,
        earliest_available_date: '2025-01-10',
      },
    }),
  },
}));

const mockedGetAvailability = publicApi.getInstructorAvailability as jest.MockedFunction<
  typeof publicApi.getInstructorAvailability
>;

describe('useInstructorAvailability', () => {
  const createWrapper = () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    return { wrapper, queryClient };
  };

  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-10T12:00:00Z'));
  });

  afterEach(() => {
    jest.useRealTimers();
    mockedGetAvailability.mockClear();
  });

  it('uses the provided future start date', async () => {
    const { wrapper, queryClient } = createWrapper();
    const startDate = '2025-01-12';

    renderHook(() => useInstructorAvailability('inst-1', startDate), { wrapper });

    await waitFor(() =>
      expect(mockedGetAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: '2025-01-12',
        end_date: '2025-01-18',
      })
    );

    // Query key now includes daysAhead (default: 7)
    const cached = queryClient
      .getQueryCache()
      .find({ queryKey: [...queryKeys.availability.week('inst-1', '2025-01-12'), 7] });
    expect(cached).toBeTruthy();
  });

  it('clamps past start dates to today', async () => {
    const { wrapper } = createWrapper();

    renderHook(() => useInstructorAvailability('inst-1', '2025-01-05'), { wrapper });

    await waitFor(() =>
      expect(mockedGetAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: '2025-01-10',
        end_date: '2025-01-16',
      })
    );
  });

  it('uses today when no startDate is provided', async () => {
    const { wrapper } = createWrapper();

    renderHook(() => useInstructorAvailability('inst-1'), { wrapper });

    await waitFor(() =>
      expect(mockedGetAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: '2025-01-10',
        end_date: '2025-01-16',
      })
    );
  });

  it('handles invalid startDate by using today', async () => {
    const { wrapper } = createWrapper();

    renderHook(() => useInstructorAvailability('inst-1', 'invalid-date'), { wrapper });

    await waitFor(() =>
      expect(mockedGetAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: '2025-01-10',
        end_date: '2025-01-16',
      })
    );
  });

  it('respects custom daysAhead parameter', async () => {
    const { wrapper, queryClient } = createWrapper();

    renderHook(() => useInstructorAvailability('inst-1', '2025-01-10', 14), { wrapper });

    await waitFor(() =>
      expect(mockedGetAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: '2025-01-10',
        end_date: '2025-01-23',
      })
    );

    // Query key should include daysAhead: 14
    const cached = queryClient
      .getQueryCache()
      .find({ queryKey: [...queryKeys.availability.week('inst-1', '2025-01-10'), 14] });
    expect(cached).toBeTruthy();
  });

  it('caps daysAhead at 30', async () => {
    const { wrapper } = createWrapper();

    renderHook(() => useInstructorAvailability('inst-1', '2025-01-10', 60), { wrapper });

    await waitFor(() =>
      expect(mockedGetAvailability).toHaveBeenCalledWith('inst-1', {
        start_date: '2025-01-10',
        end_date: '2025-02-08', // 30 days from Jan 10 - 1 = Feb 8
      })
    );
  });

  it('throws error when API returns error', async () => {
    mockedGetAvailability.mockResolvedValueOnce({
      status: 500,
      error: 'Server error',
      data: undefined,
    });

    const { wrapper } = createWrapper();

    const { result } = renderHook(() => useInstructorAvailability('inst-1'), { wrapper });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });

  it('handles rate limit (429) response as error', async () => {
    mockedGetAvailability.mockResolvedValueOnce({
      status: 429,
      error: 'Rate limited',
      data: undefined,
    });

    const { wrapper } = createWrapper();

    const { result } = renderHook(() => useInstructorAvailability('inst-1'), { wrapper });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });

  it('is disabled when instructorId is empty', async () => {
    const { wrapper } = createWrapper();

    const { result } = renderHook(() => useInstructorAvailability(''), { wrapper });

    // Should not fetch
    expect(mockedGetAvailability).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isFetching).toBe(false);
  });

  it('returns availability data on success', async () => {
    mockedGetAvailability.mockResolvedValueOnce({
      status: 200,
      data: {
        instructor_id: 'inst-1',
        instructor_first_name: 'John',
        instructor_last_initial: 'D',
        availability_by_date: {
          '2025-01-10': {
            date: '2025-01-10',
            available_slots: [{ start_time: '09:00', end_time: '12:00' }],
            is_blackout: false,
          },
        },
        timezone: 'America/New_York',
        total_available_slots: 3,
        earliest_available_date: '2025-01-10',
      },
    });

    const { wrapper } = createWrapper();

    const { result } = renderHook(() => useInstructorAvailability('inst-1'), { wrapper });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
      expect(result.current.data?.instructor_id).toBe('inst-1');
      expect(result.current.data?.timezone).toBe('America/New_York');
      expect(result.current.data?.total_available_slots).toBe(3);
    });
  });
});
