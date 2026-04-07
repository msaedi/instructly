import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useCodebaseMetrics } from '../useCodebaseMetrics';
import { analyticsApi } from '@/lib/analyticsApi';

jest.mock('@/lib/analyticsApi', () => ({
  analyticsApi: {
    getCodebaseMetrics: jest.fn(),
  },
}));

const getCodebaseMetricsMock = analyticsApi.getCodebaseMetrics as jest.Mock;

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'CodebaseMetricsQueryClientWrapper';
  return { Wrapper };
};

describe('useCodebaseMetrics', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches history on mount and keeps the latest entry at the end of the array', async () => {
    const history = [
      {
        timestamp: '2024-01-01T00:00:00',
        total_files: 100,
        total_lines: 500,
        backend_lines: 300,
        frontend_lines: 200,
        git_commits: 10,
      },
      {
        timestamp: '2024-01-02T00:00:00',
        total_files: 120,
        total_lines: 600,
        backend_lines: 360,
        frontend_lines: 240,
        git_commits: 12,
      },
    ];

    getCodebaseMetricsMock.mockResolvedValue(history);

    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useCodebaseMetrics(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(getCodebaseMetricsMock).toHaveBeenCalledWith();
    expect(result.current.data).toEqual(history);
    expect(result.current.data?.at(-1)).toEqual(history[1]);
  });

  it('returns an empty history array when the endpoint has no entries', async () => {
    getCodebaseMetricsMock.mockResolvedValue([]);

    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useCodebaseMetrics(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual([]);
    expect(result.current.data?.at(-1)).toBeUndefined();
  });

  it('surfaces query errors when fetch fails', async () => {
    getCodebaseMetricsMock.mockRejectedValueOnce(new Error('Metrics failed'));

    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useCodebaseMetrics(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error?.message).toBe('Metrics failed');
  });

  it('refetch triggers another request cycle', async () => {
    getCodebaseMetricsMock.mockResolvedValue([]);

    const { Wrapper } = createWrapper();
    const { result } = renderHook(() => useCodebaseMetrics(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    await act(async () => {
      await result.current.refetch();
    });

    expect(getCodebaseMetricsMock).toHaveBeenCalledTimes(2);
  });
});
