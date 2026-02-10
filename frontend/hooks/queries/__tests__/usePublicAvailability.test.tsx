import React from 'react';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { usePublicAvailability } from '../usePublicAvailability';
import { publicApi } from '@/features/shared/api/client';

jest.mock('@/features/shared/api/client', () => ({
  publicApi: {
    getInstructorAvailability: jest.fn(),
  },
}));

const getInstructorAvailabilityMock = publicApi.getInstructorAvailability as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

describe('usePublicAvailability', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2025-01-10T10:00:00Z'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('returns empty data when no instructor ids provided', async () => {
    const { result } = renderHook(() => usePublicAvailability([]), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current).toEqual({});
    });
    expect(getInstructorAvailabilityMock).not.toHaveBeenCalled();
  });

  it('fetches availability for unique ids and normalizes time', async () => {
    getInstructorAvailabilityMock.mockImplementation((instructorId: string) => {
      if (instructorId === 'inst-a') {
        return Promise.resolve({
          status: 200,
          data: {
            availability_by_date: {
              '2025-01-12': {
                available_slots: [{ start_time: '9:5', end_time: null }],
                is_blackout: false,
              },
            },
            timezone: 'UTC',
          },
        });
      }
      return Promise.resolve({
        status: 500,
        error: 'Server error',
      });
    });

    const { result } = renderHook(() => usePublicAvailability(['inst-b', 'inst-a', 'inst-a']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current['inst-a']).toBeDefined();
    });

    expect(getInstructorAvailabilityMock).toHaveBeenCalledTimes(2);
    const calls = getInstructorAvailabilityMock.mock.calls.map((call) => call[0]);
    expect(calls).toEqual(expect.arrayContaining(['inst-a', 'inst-b']));
    getInstructorAvailabilityMock.mock.calls.forEach((call) => {
      expect(call[1]).toEqual({
        start_date: '2025-01-10',
        end_date: '2025-01-24',
      });
    });

    expect(result.current['inst-a']).toEqual({
      timezone: 'UTC',
      availabilityByDate: {
        '2025-01-12': {
          available_slots: [{ start_time: '09:05', end_time: '00:00' }],
          is_blackout: false,
        },
      },
    });
    expect(result.current['inst-b']).toBeUndefined();
  });

  it('returns null for response with missing data field', async () => {
    getInstructorAvailabilityMock.mockResolvedValueOnce({
      status: 200,
      data: null,
    });

    const { result } = renderHook(() => usePublicAvailability(['inst-c']), {
      wrapper: createWrapper(),
    });

    // The combine function skips entries where data is null,
    // so inst-c should not be in the result
    await waitFor(() => {
      expect(getInstructorAvailabilityMock).toHaveBeenCalled();
    });
    expect(result.current['inst-c']).toBeUndefined();
  });

  it('handles availability_by_date being undefined (uses || {} fallback)', async () => {
    getInstructorAvailabilityMock.mockResolvedValueOnce({
      status: 200,
      data: {
        availability_by_date: undefined,
        timezone: 'America/New_York',
      },
    });

    const { result } = renderHook(() => usePublicAvailability(['inst-d']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current['inst-d']).toBeDefined();
    });

    expect(result.current['inst-d']?.availabilityByDate).toEqual({});
    expect(result.current['inst-d']?.timezone).toBe('America/New_York');
  });

  it('handles day with null available_slots (uses || [] fallback)', async () => {
    getInstructorAvailabilityMock.mockResolvedValueOnce({
      status: 200,
      data: {
        availability_by_date: {
          '2025-01-15': {
            available_slots: null,
            is_blackout: false,
          },
        },
        timezone: null,
      },
    });

    const { result } = renderHook(() => usePublicAvailability(['inst-e']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current['inst-e']).toBeDefined();
    });

    expect(result.current['inst-e']?.availabilityByDate['2025-01-15']?.available_slots).toEqual([]);
    // timezone null should become undefined via ?? undefined
    expect(result.current['inst-e']?.timezone).toBeUndefined();
  });

  it('skips null day entries in availability_by_date', async () => {
    getInstructorAvailabilityMock.mockResolvedValueOnce({
      status: 200,
      data: {
        availability_by_date: {
          '2025-01-20': null,
          '2025-01-21': {
            available_slots: [{ start_time: '10:00', end_time: '11:00' }],
            is_blackout: false,
          },
        },
        timezone: 'UTC',
      },
    });

    const { result } = renderHook(() => usePublicAvailability(['inst-f']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current['inst-f']).toBeDefined();
    });

    // Null day should be skipped
    expect(result.current['inst-f']?.availabilityByDate['2025-01-20']).toBeUndefined();
    // Valid day should be present
    expect(result.current['inst-f']?.availabilityByDate['2025-01-21']?.available_slots).toHaveLength(1);
  });

  it('filters out empty string instructor IDs', async () => {
    getInstructorAvailabilityMock.mockResolvedValueOnce({
      status: 200,
      data: {
        availability_by_date: {},
        timezone: 'UTC',
      },
    });

    const { result } = renderHook(() => usePublicAvailability(['inst-g', '', 'inst-g']), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current['inst-g']).toBeDefined();
    });

    // Empty string should be filtered, and duplicates deduped
    expect(getInstructorAvailabilityMock).toHaveBeenCalledTimes(1);
  });
});
