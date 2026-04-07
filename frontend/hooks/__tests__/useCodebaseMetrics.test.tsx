import { act, renderHook, waitFor } from '@testing-library/react';

import { useCodebaseMetrics } from '../useCodebaseMetrics';
import { analyticsApi } from '@/lib/analyticsApi';

jest.mock('@/lib/analyticsApi', () => ({
  analyticsApi: {
    getCodebaseMetrics: jest.fn(),
  },
}));

const getCodebaseMetricsMock = analyticsApi.getCodebaseMetrics as jest.Mock;

describe('useCodebaseMetrics', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches history on mount and exposes the latest entry', async () => {
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

    const { result } = renderHook(() => useCodebaseMetrics('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getCodebaseMetricsMock).toHaveBeenCalledWith('token-123');
    expect(result.current.data).toEqual(history[1]);
    expect(result.current.history).toEqual(history);
  });

  it('defaults history to an empty array when the endpoint returns no items', async () => {
    getCodebaseMetricsMock.mockResolvedValue([]);

    const { result } = renderHook(() => useCodebaseMetrics('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.history).toEqual([]);
    expect(result.current.data).toBeNull();
  });

  it('reports errors when fetch fails', async () => {
    getCodebaseMetricsMock.mockRejectedValueOnce(new Error('Metrics failed'));

    const { result } = renderHook(() => useCodebaseMetrics('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe('Metrics failed');
  });

  it('refetch triggers another request cycle', async () => {
    getCodebaseMetricsMock.mockResolvedValue([]);

    const { result } = renderHook(() => useCodebaseMetrics('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.refetch();
    });

    expect(getCodebaseMetricsMock).toHaveBeenCalledTimes(2);
  });

  it('uses an empty token when token is undefined', async () => {
    getCodebaseMetricsMock.mockResolvedValue([]);

    const { result } = renderHook(() => useCodebaseMetrics(undefined));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getCodebaseMetricsMock).toHaveBeenCalledWith('');
  });

  it('auto-refreshes on interval tick and survives a rejected fetch', async () => {
    jest.useFakeTimers();

    const history = [
      {
        timestamp: '2024-01-01T00:00:00',
        total_files: 100,
        total_lines: 500,
        backend_lines: 300,
        frontend_lines: 200,
        git_commits: 10,
      },
    ];

    getCodebaseMetricsMock.mockResolvedValue(history);

    const { result } = renderHook(() => useCodebaseMetrics('token-123'));

    // Wait for the initial fetch to complete
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getCodebaseMetricsMock).toHaveBeenCalledTimes(1);

    // Make the next fetch reject to verify the interval callback handles errors
    getCodebaseMetricsMock.mockRejectedValueOnce(new Error('Network timeout'));

    // Advance time by 10 minutes to trigger the interval
    await act(async () => {
      jest.advanceTimersByTime(10 * 60 * 1000);
    });

    // The interval should have triggered a second call
    await waitFor(() => expect(getCodebaseMetricsMock).toHaveBeenCalledTimes(2));

    // Error should be captured in state, not thrown
    expect(result.current.error).toBe('Network timeout');
    // Previous data should still be present (hook sets error but doesn't clear data)
    expect(result.current.data).toEqual(history[0]);

    jest.useRealTimers();
  });
});
