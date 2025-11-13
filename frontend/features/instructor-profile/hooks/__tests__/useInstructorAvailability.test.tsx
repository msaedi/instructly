import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useInstructorAvailability } from '../useInstructorAvailability';
import { publicApi } from '@/features/shared/api/client';
import { queryKeys } from '@/lib/react-query/queryClient';

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
    const queryClient = new QueryClient();
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

    const cached = queryClient
      .getQueryCache()
      .find({ queryKey: queryKeys.availability.week('inst-1', '2025-01-12') });
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
});
