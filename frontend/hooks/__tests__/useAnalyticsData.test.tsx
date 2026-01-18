import { act, renderHook, waitFor } from '@testing-library/react';

import { useAnalyticsData } from '../useAnalyticsData';
import { analyticsApi } from '@/lib/analyticsApi';
import { logger } from '@/lib/logger';

jest.mock('@/lib/analyticsApi', () => ({
  analyticsApi: {
    getSearchTrends: jest.fn(),
    getPopularSearches: jest.fn(),
    getSearchReferrers: jest.fn(),
    getZeroResultSearches: jest.fn(),
    getServicePillPerformance: jest.fn(),
    getAnalyticsSummary: jest.fn(),
    getSearchPerformance: jest.fn(),
    getConversionMetrics: jest.fn(),
  },
}));

jest.mock('@/lib/logger', () => ({
  logger: {
    error: jest.fn(),
  },
}));

const getSearchTrendsMock = analyticsApi.getSearchTrends as jest.Mock;
const getPopularSearchesMock = analyticsApi.getPopularSearches as jest.Mock;
const getSearchReferrersMock = analyticsApi.getSearchReferrers as jest.Mock;
const getZeroResultSearchesMock = analyticsApi.getZeroResultSearches as jest.Mock;
const getServicePillPerformanceMock = analyticsApi.getServicePillPerformance as jest.Mock;
const getAnalyticsSummaryMock = analyticsApi.getAnalyticsSummary as jest.Mock;
const getSearchPerformanceMock = analyticsApi.getSearchPerformance as jest.Mock;
const getConversionMetricsMock = analyticsApi.getConversionMetrics as jest.Mock;
const loggerErrorMock = logger.error as jest.Mock;

const mockPayloads = () => {
  const trends = [{ query: 'math', count: 2 }];
  const popular = [{ query: 'math', search_count: 10, average_results: 3, unique_users: 5 }];
  const referrers = [{ referrer: 'google', count: 4 }];
  const zeroResults = [{ query: 'none', count: 1, last_searched: '2024-01-01T00:00:00Z' }];
  const servicePills = [{ service_name: 'math', clicks: 3, unique_users: 2, conversion_rate: 0.2 }];
  const summary = { total_searches: 10 };
  const performance = { average_latency_ms: 120 };
  const conversions = { conversion_rate: 0.08 };

  getSearchTrendsMock.mockResolvedValue(trends);
  getPopularSearchesMock.mockResolvedValue(popular);
  getSearchReferrersMock.mockResolvedValue(referrers);
  getZeroResultSearchesMock.mockResolvedValue(zeroResults);
  getServicePillPerformanceMock.mockResolvedValue(servicePills);
  getAnalyticsSummaryMock.mockResolvedValue(summary);
  getSearchPerformanceMock.mockResolvedValue(performance);
  getConversionMetricsMock.mockResolvedValue(conversions);

  return {
    trends,
    popular,
    referrers,
    zeroResults,
    servicePills,
    summary,
    performance,
    conversions,
  };
};

describe('useAnalyticsData', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches analytics data on mount', async () => {
    const payloads = mockPayloads();

    const { result } = renderHook(() => useAnalyticsData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(getSearchTrendsMock).toHaveBeenCalledWith('token-123', 30);
    expect(getPopularSearchesMock).toHaveBeenCalledWith('token-123', 30, 20);
    expect(getSearchReferrersMock).toHaveBeenCalledWith('token-123', 30);
    expect(getZeroResultSearchesMock).toHaveBeenCalledWith('token-123', 30, 20);
    expect(getServicePillPerformanceMock).toHaveBeenCalledWith('token-123', 30);
    expect(getAnalyticsSummaryMock).toHaveBeenCalledWith('token-123', 30);
    expect(getSearchPerformanceMock).toHaveBeenCalledWith('token-123', 30);
    expect(getConversionMetricsMock).toHaveBeenCalledWith('token-123', 30);

    expect(result.current.data.trends).toEqual(payloads.trends);
    expect(result.current.data.popularSearches).toEqual(payloads.popular);
    expect(result.current.data.referrers).toEqual(payloads.referrers);
    expect(result.current.data.zeroResults).toEqual(payloads.zeroResults);
    expect(result.current.data.servicePills).toEqual(payloads.servicePills);
    expect(result.current.data.summary).toEqual(payloads.summary);
    expect(result.current.data.performance).toEqual(payloads.performance);
    expect(result.current.data.conversions).toEqual(payloads.conversions);
  });

  it('uses an empty token when token is null', async () => {
    mockPayloads();

    const { result } = renderHook(() => useAnalyticsData(null));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getSearchTrendsMock).toHaveBeenCalledWith('', 30);
  });

  it('sets error state and logs when a fetch fails', async () => {
    mockPayloads();
    getSearchTrendsMock.mockRejectedValueOnce(new Error('Boom'));

    const { result } = renderHook(() => useAnalyticsData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.error).toBe('Boom');
    expect(loggerErrorMock).toHaveBeenCalledWith(
      'Failed to fetch analytics data',
      expect.any(Error)
    );
  });

  it('refetch triggers another request cycle', async () => {
    mockPayloads();

    const { result } = renderHook(() => useAnalyticsData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.refetch();
    });

    expect(getSearchTrendsMock).toHaveBeenCalledTimes(2);
  });

  it('setDateRange triggers a fetch with the new range', async () => {
    mockPayloads();

    const { result } = renderHook(() => useAnalyticsData('token-123'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      result.current.setDateRange(7);
    });

    await waitFor(() =>
      expect(getSearchTrendsMock).toHaveBeenLastCalledWith('token-123', 7)
    );
    expect(result.current.dateRange).toBe(7);
  });
});
