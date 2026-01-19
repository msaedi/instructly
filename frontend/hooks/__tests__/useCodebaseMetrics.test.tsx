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
});
