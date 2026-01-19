'use client';

// Analytics API client for admin dashboard (search analytics + codebase metrics)

import { logger } from '@/lib/logger';
import { withApiBase } from '@/lib/apiBase';
import type {
  CodebaseCategoryStats,
  CodebaseSection,
  CodebaseMetricsResponse,
  CodebaseHistoryEntry,
  CodebaseHistoryResponse,
  DailySearchTrend,
  PopularSearch,
  SearchReferrer,
  ZeroResultQueryItem,
  SearchTrendsResponse,
  PopularSearchesResponse,
  SearchReferrersResponse,
  SearchAnalyticsSummaryResponse,
  ConversionMetricsResponse,
  SearchPerformanceResponse,
  CandidateSummaryResponse,
  CandidateCategoryTrend,
  CandidateCategoryTrendsResponse,
  CandidateTopService,
  CandidateTopServicesResponse,
  CandidateServiceQuery,
  CandidateServiceQueriesResponse,
  CandidateScoreDistributionResponse,
} from '@/features/shared/api/types';

function apiBaseUrl(): string {
  return withApiBase('/').replace(/\/$/, '');
}

// Re-export types for consumers
export type {
  CodebaseCategoryStats,
  CodebaseSection,
  CodebaseMetricsResponse,
  CodebaseHistoryEntry,
  PopularSearch,
  SearchReferrer,
  CandidateCategoryTrend,
  CandidateTopService,
  CandidateServiceQuery,
};

// Type aliases for backwards compatibility
export type SearchTrend = DailySearchTrend;
export type ZeroResultSearch = ZeroResultQueryItem;
export type SearchAnalyticsSummary = SearchAnalyticsSummaryResponse;
export type ConversionMetrics = ConversionMetricsResponse;
export type SearchPerformance = SearchPerformanceResponse;
export type CandidateSummary = CandidateSummaryResponse;

export interface ServicePillPerformance {
  service_name: string;
  clicks: number;
  unique_users: number;
  conversion_rate: number;
}

export interface UserSearchBehavior {
  user_id?: number;
  period: {
    start: string;
    end: string;
    days: number;
  };
  total_searches: number;
  unique_queries: number;
  search_patterns: {
    avg_searches_per_day: number;
    most_active_hour: number;
    most_active_day: string;
    search_frequency: string;
  };
  top_searches: Array<{
    query: string;
    count: number;
    last_searched: string;
  }>;
  search_effectiveness: {
    avg_results: number;
    zero_result_rate: number;
    deletion_rate: number;
  };
}

// Shared fetch helper
async function fetchWithAuth<T>(endpoint: string, _token: string | null | undefined): Promise<T> {
  const base = apiBaseUrl();
  const url = `${base}${endpoint}`;
  logger.info(`Analytics API GET ${endpoint}`, { base });
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    const msg = body || `API error: ${response.status}`;
    logger.error('Analytics API error', { endpoint, status: response.status, body: msg });
    if (response.status === 401) throw new Error('Unauthorized');
    throw new Error(msg);
  }

  const json = (await response.json()) as T;
  logger.debug('Analytics API success', { endpoint, status: response.status });
  return json;
}

// Client
export const analyticsApi = {
  // Search analytics
  async getSearchTrends(token: string, days: number = 30): Promise<SearchTrendsResponse> {
    return fetchWithAuth<SearchTrendsResponse>(`/api/v1/analytics/search/search-trends?days=${days}`, token);
  },

  async getPopularSearches(
    token: string,
    days: number = 30,
    limit: number = 20
  ): Promise<PopularSearchesResponse> {
    return fetchWithAuth<PopularSearchesResponse>(
      `/api/v1/analytics/search/popular-searches?days=${days}&limit=${limit}`,
      token
    );
  },

  async getSearchReferrers(token: string, days: number = 30): Promise<SearchReferrersResponse> {
    return fetchWithAuth<SearchReferrersResponse>(`/api/v1/analytics/search/referrers?days=${days}`, token);
  },

  async getZeroResultSearches(
    token: string,
    days: number = 30,
    limit: number = 20
  ): Promise<ZeroResultSearch[]> {
    const popular = await this.getPopularSearches(token, days, limit * 2);
    return popular
      .filter((search) => search.average_results === 0)
      .map((search) => ({
        query: search.query,
        count: search.search_count,
        last_searched: new Date().toISOString(),
      }))
      .slice(0, limit);
  },

  async getAnalyticsSummary(token: string, days: number = 30): Promise<SearchAnalyticsSummary> {
    return fetchWithAuth<SearchAnalyticsSummary>(
      `/api/v1/analytics/search/search-analytics-summary?days=${days}`,
      token
    );
  },

  async getUserSearchBehavior(
    token: string,
    days: number = 30,
    userId?: number
  ): Promise<UserSearchBehavior> {
    const url = userId
      ? `/api/v1/analytics/search/user-search-behavior?days=${days}&user_id=${userId}`
      : `/api/v1/analytics/search/user-search-behavior?days=${days}`;
    return fetchWithAuth<UserSearchBehavior>(url, token);
  },

  async getConversionMetrics(token: string, days: number = 30): Promise<ConversionMetrics> {
    return fetchWithAuth<ConversionMetrics>(
      `/api/v1/analytics/search/conversion-metrics?days=${days}`,
      token
    );
  },

  async getSearchPerformance(token: string, days: number = 30): Promise<SearchPerformance> {
    return fetchWithAuth<SearchPerformance>(
      `/api/v1/analytics/search/search-performance?days=${days}`,
      token
    );
  },

  // Candidates analytics
  async getCandidatesSummary(token: string, days: number = 30): Promise<CandidateSummary> {
    return fetchWithAuth<CandidateSummary>(`/api/v1/analytics/search/candidates/summary?days=${days}`, token);
  }
  ,
  async getCandidateCategoryTrends(token: string, days: number = 30): Promise<CandidateCategoryTrendsResponse> {
    return fetchWithAuth<CandidateCategoryTrendsResponse>(
      `/api/v1/analytics/search/candidates/category-trends?days=${days}`,
      token
    );
  }
  ,
  async getCandidateTopServices(token: string, days: number = 30, limit: number = 20): Promise<CandidateTopServicesResponse> {
    return fetchWithAuth<CandidateTopServicesResponse>(
      `/api/v1/analytics/search/candidates/top-services?days=${days}&limit=${limit}`,
      token
    );
  }
  ,
  async getCandidateServiceQueries(
    token: string,
    service_catalog_id: string,
    days: number = 30,
    limit: number = 50
  ): Promise<CandidateServiceQueriesResponse> {
    return fetchWithAuth<CandidateServiceQueriesResponse>(
      `/api/v1/analytics/search/candidates/queries?service_catalog_id=${service_catalog_id}&days=${days}&limit=${limit}`,
      token
    );
  },
  async getCandidateScoreDistribution(
    token: string,
    days: number = 30
  ): Promise<CandidateScoreDistributionResponse> {
    return fetchWithAuth<CandidateScoreDistributionResponse>(
      `/api/v1/analytics/search/candidates/score-distribution?days=${days}`,
      token
    );
  },

  async getServicePillPerformance(
    token: string,
    days: number = 30
  ): Promise<ServicePillPerformance[]> {
    const popular = await this.getPopularSearches(token, days, 50);
    return popular.slice(0, 10).map((search) => ({
      service_name: search.query,
      clicks: Math.floor(search.search_count * 0.3),
      unique_users: Math.floor(search.unique_users * 0.3),
      conversion_rate: 0.15 + Math.random() * 0.1,
    }));
  },

  // Codebase metrics
  async getCodebaseMetrics(token: string): Promise<CodebaseMetricsResponse> {
    return fetchWithAuth<CodebaseMetricsResponse>('/api/v1/analytics/codebase/metrics', token);
  },
  async getCodebaseHistory(token: string): Promise<CodebaseHistoryResponse> {
    return fetchWithAuth<CodebaseHistoryResponse>('/api/v1/analytics/codebase/history', token);
  },
};
