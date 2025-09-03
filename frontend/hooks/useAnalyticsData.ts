// frontend/hooks/useAnalyticsData.ts
/**
 * Hook for fetching and managing analytics data
 */

import { useState, useEffect, useCallback } from 'react';
import { logger } from '@/lib/logger';
import { analyticsApi } from '@/lib/analyticsApi';
import type {
  SearchTrend,
  PopularSearch,
  SearchReferrer,
  ZeroResultSearch,
  ServicePillPerformance,
  SearchAnalyticsSummary,
  SearchPerformance,
  ConversionMetrics,
} from '@/lib/analyticsApi';

interface AnalyticsData {
  trends: SearchTrend[] | null;
  popularSearches: PopularSearch[] | null;
  referrers: SearchReferrer[] | null;
  zeroResults: ZeroResultSearch[] | null;
  servicePills: ServicePillPerformance[] | null;
  summary: SearchAnalyticsSummary | null;
  performance: SearchPerformance | null;
  conversions: ConversionMetrics | null;
}

interface UseAnalyticsDataReturn {
  data: AnalyticsData;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  dateRange: number;
  setDateRange: (days: number) => void;
}

export function useAnalyticsData(token: string | null): UseAnalyticsDataReturn {
  const [data, setData] = useState<AnalyticsData>({
    trends: null,
    popularSearches: null,
    referrers: null,
    zeroResults: null,
    servicePills: null,
    summary: null,
    performance: null,
    conversions: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState(30);

  const fetchAllData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch all data in parallel
      const [
        trends,
        popularSearches,
        referrers,
        zeroResults,
        servicePills,
        summary,
        performance,
        conversions,
      ] = await Promise.all([
        analyticsApi.getSearchTrends(token ?? '', dateRange),
        analyticsApi.getPopularSearches(token ?? '', dateRange, 20),
        analyticsApi.getSearchReferrers(token ?? '', dateRange),
        analyticsApi.getZeroResultSearches(token ?? '', dateRange, 20),
        analyticsApi.getServicePillPerformance(token ?? '', dateRange),
        analyticsApi.getAnalyticsSummary(token ?? '', dateRange),
        analyticsApi.getSearchPerformance(token ?? '', dateRange),
        analyticsApi.getConversionMetrics(token ?? '', dateRange),
      ]);

      setData({
        trends,
        popularSearches,
        referrers,
        zeroResults,
        servicePills,
        summary,
        performance,
        conversions,
      });
    } catch (err) {
      logger.error('Failed to fetch analytics data', err as Error);
      setError(err instanceof Error ? err.message : 'Failed to fetch analytics data');
    } finally {
      setLoading(false);
    }
  }, [token, dateRange]);

  // Fetch data on mount and when date range changes
  useEffect(() => {
    fetchAllData();
  }, [fetchAllData]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const interval = setInterval(
      () => {
        fetchAllData();
      },
      5 * 60 * 1000
    );

    return () => clearInterval(interval);
  }, [fetchAllData]);

  return {
    data,
    loading,
    error,
    refetch: fetchAllData,
    dateRange,
    setDateRange,
  };
}
