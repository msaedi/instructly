import { act, renderHook, waitFor } from '@testing-library/react';

import { useCodebaseMetrics } from '../useCodebaseMetrics';
import { analyticsApi } from '@/lib/analyticsApi';

jest.mock('@/lib/analyticsApi', () => ({
  analyticsApi: {
    getCodebaseMetrics: jest.fn(),
    getCodebaseHistory: jest.fn(),
  },
}));

const getCodebaseMetricsMock = analyticsApi.getCodebaseMetrics as jest.Mock;
const getCodebaseHistoryMock = analyticsApi.getCodebaseHistory as jest.Mock;

describe('useCodebaseMetrics', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches snapshot and history on mount', async () => {
    const snapshot = { total_files: 120 };
    const history = { items: [{ timestamp: '2024-01-01', total_files: 100 }] };

    getCodebaseMetricsMock.mockResolvedValue(snapshot);
    getCodebaseHistoryMock.mockResolvedValue(history);

    const { result } = renderHook(() => useCodebaseMetrics('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getCodebaseMetricsMock).toHaveBeenCalledWith('token-123');
    expect(getCodebaseHistoryMock).toHaveBeenCalledWith('token-123');
    expect(result.current.data).toEqual(snapshot);
    expect(result.current.history).toEqual(history.items);
  });

  it('defaults history to an empty array when items are missing', async () => {
    getCodebaseMetricsMock.mockResolvedValue({ total_files: 120 });
    getCodebaseHistoryMock.mockResolvedValue({});

    const { result } = renderHook(() => useCodebaseMetrics('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.history).toEqual([]);
  });

  it('reports errors when fetch fails', async () => {
    getCodebaseMetricsMock.mockRejectedValueOnce(new Error('Metrics failed'));
    getCodebaseHistoryMock.mockResolvedValue({ items: [] });

    const { result } = renderHook(() => useCodebaseMetrics('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe('Metrics failed');
  });

  it('refetch triggers another request cycle', async () => {
    getCodebaseMetricsMock.mockResolvedValue({ total_files: 120 });
    getCodebaseHistoryMock.mockResolvedValue({ items: [] });

    const { result } = renderHook(() => useCodebaseMetrics('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.refetch();
    });

    expect(getCodebaseMetricsMock).toHaveBeenCalledTimes(2);
    expect(getCodebaseHistoryMock).toHaveBeenCalledTimes(2);
  });

  it('uses an empty token when token is undefined', async () => {
    getCodebaseMetricsMock.mockResolvedValue({ total_files: 120 });
    getCodebaseHistoryMock.mockResolvedValue({ items: [] });

    const { result } = renderHook(() => useCodebaseMetrics(undefined));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getCodebaseMetricsMock).toHaveBeenCalledWith('');
    expect(getCodebaseHistoryMock).toHaveBeenCalledWith('');
  });

  it('auto-refreshes on interval tick and survives a rejected fetch', async () => {
    jest.useFakeTimers();

    const snapshot = { total_files: 120 };
    const history = { items: [{ timestamp: '2024-01-01', total_files: 100 }] };

    getCodebaseMetricsMock.mockResolvedValue(snapshot);
    getCodebaseHistoryMock.mockResolvedValue(history);

    const { result } = renderHook(() => useCodebaseMetrics('token-123'));

    // Wait for the initial fetch to complete
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getCodebaseMetricsMock).toHaveBeenCalledTimes(1);
    expect(getCodebaseHistoryMock).toHaveBeenCalledTimes(1);

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
    expect(result.current.data).toEqual(snapshot);

    jest.useRealTimers();
  });
});
