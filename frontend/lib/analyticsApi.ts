'use client';

// Analytics API client for admin dashboard (search analytics + codebase metrics)

import { logger } from '@/lib/logger';
import { env } from '@/lib/env';

const API_BASE_URL = env.get('NEXT_PUBLIC_API_BASE') || 'http://localhost:8000';

// Codebase metrics types
export interface CodebaseCategoryStats {
  files: number;
  lines: number;
}

export interface CodebaseSection {
  total_files: number;
  total_lines: number;
  total_lines_with_blanks: number;
  categories: Record<string, CodebaseCategoryStats>;
  largest_files: Array<{
    path: string;
    lines: number;
    lines_with_blanks: number;
    size_kb: number;
  }>;
}

export interface GitStats {
  total_commits: number;
  unique_contributors: number;
  first_commit: string;
  last_commit: string;
  current_branch: string;
}

export interface CodebaseMetricsResponse {
  timestamp: string;
  backend: CodebaseSection;
  frontend: CodebaseSection;
  git: GitStats;
  summary: {
    total_lines: number;
    total_files: number;
  };
}

export interface CodebaseHistoryEntry {
  timestamp: string;
  total_lines: number;
  total_files: number;
  backend_lines: number;
  frontend_lines: number;
  git_commits: number;
}

// Search analytics types
export interface SearchTrend {
  date: string;
  total_searches: number;
  unique_users: number;
  unique_guests: number;
}

export interface PopularSearch {
  query: string;
  search_count: number;
  unique_users: number;
  average_results: number;
}

export interface SearchReferrer {
  page: string;
  search_count: number;
  unique_sessions: number;
  search_types: string[];
}

export interface ZeroResultSearch {
  query: string;
  count: number;
  last_searched: string;
}

export interface ServicePillPerformance {
  service_name: string;
  clicks: number;
  unique_users: number;
  conversion_rate: number;
}

export interface SearchAnalyticsSummary {
  date_range: {
    start: string;
    end: string;
    days: number;
  };
  totals: {
    total_searches: number;
    unique_users: number;
    unique_guests: number;
    total_users: number;
    deleted_searches: number;
    deletion_rate: number;
  };
  users: {
    authenticated: number;
    guests: number;
    converted_guests: number;
    user_percentage: number;
    guest_percentage: number;
  };
  search_types: Record<string, { count: number; percentage: number }>;
  conversions: {
    guest_sessions: {
      total: number;
      converted: number;
      conversion_rate: number;
    };
    conversion_behavior: {
      avg_searches_before_conversion: number;
      avg_days_to_conversion: number;
      most_common_first_search: string;
    };
  };
  performance: {
    avg_results_per_search: number;
    zero_result_rate: number;
    most_effective_type: string;
  };
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

export interface ConversionMetrics {
  period: {
    start: string;
    end: string;
    days: number;
  };
  guest_sessions: {
    total: number;
    converted: number;
    conversion_rate: number;
  };
  conversion_behavior: {
    avg_searches_before_conversion: number;
    avg_days_to_conversion: number;
    most_common_first_search: string;
  };
  guest_engagement: {
    avg_searches_per_session: number;
    engaged_sessions: number;
    engagement_rate: number;
  };
}

export interface SearchPerformance {
  result_distribution: {
    zero_results: number;
    '1_5_results': number;
    '6_10_results': number;
    over_10_results: number;
  };
  effectiveness: {
    avg_results_per_search: number;
    median_results: number;
    searches_with_results: number;
    zero_result_rate: number;
  };
  problematic_queries: Array<{
    query: string;
    count: number;
    avg_results: number;
  }>;
}

// Candidates analytics types
export interface CandidateSummary {
  total_candidates: number;
  events_with_candidates: number;
  avg_candidates_per_event: number;
  zero_result_events_with_candidates: number;
  source_breakdown: Record<string, number>;
}

export interface CandidateCategoryTrend {
  date: string;
  category: string;
  count: number;
}

export interface CandidateTopService {
  service_catalog_id: string;
  service_name: string;
  category_name: string;
  candidate_count: number;
  avg_score: number;
  avg_position: number;
  active_instructors: number;
  opportunity_score: number;
}

// Shared fetch helper
async function fetchWithAuth<T>(endpoint: string, _token: string | null | undefined): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  logger.info(`Analytics API GET ${endpoint}`, { base: API_BASE_URL });
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

  const json = await response.json();
  logger.debug('Analytics API success', { endpoint, status: response.status });
  return json;
}

// Client
export const analyticsApi = {
  // Search analytics
  async getSearchTrends(token: string, days: number = 30): Promise<SearchTrend[]> {
    return fetchWithAuth<SearchTrend[]>(`/api/analytics/search/search-trends?days=${days}`, token);
  },

  async getPopularSearches(
    token: string,
    days: number = 30,
    limit: number = 20
  ): Promise<PopularSearch[]> {
    return fetchWithAuth<PopularSearch[]>(
      `/api/analytics/search/popular-searches?days=${days}&limit=${limit}`,
      token
    );
  },

  async getSearchReferrers(token: string, days: number = 30): Promise<SearchReferrer[]> {
    return fetchWithAuth<SearchReferrer[]>(`/api/analytics/search/referrers?days=${days}`, token);
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
      `/api/analytics/search/search-analytics-summary?days=${days}`,
      token
    );
  },

  async getUserSearchBehavior(
    token: string,
    days: number = 30,
    userId?: number
  ): Promise<UserSearchBehavior> {
    const url = userId
      ? `/api/analytics/search/user-search-behavior?days=${days}&user_id=${userId}`
      : `/api/analytics/search/user-search-behavior?days=${days}`;
    return fetchWithAuth<UserSearchBehavior>(url, token);
  },

  async getConversionMetrics(token: string, days: number = 30): Promise<ConversionMetrics> {
    return fetchWithAuth<ConversionMetrics>(
      `/api/analytics/search/conversion-metrics?days=${days}`,
      token
    );
  },

  async getSearchPerformance(token: string, days: number = 30): Promise<SearchPerformance> {
    return fetchWithAuth<SearchPerformance>(
      `/api/analytics/search/search-performance?days=${days}`,
      token
    );
  },

  // Candidates analytics
  async getCandidatesSummary(token: string, days: number = 30): Promise<CandidateSummary> {
    return fetchWithAuth<CandidateSummary>(`/api/analytics/search/candidates/summary?days=${days}`, token);
  }
  ,
  async getCandidateCategoryTrends(token: string, days: number = 30): Promise<CandidateCategoryTrend[]> {
    return fetchWithAuth<CandidateCategoryTrend[]>(
      `/api/analytics/search/candidates/category-trends?days=${days}`,
      token
    );
  }
  ,
  async getCandidateTopServices(token: string, days: number = 30, limit: number = 20): Promise<CandidateTopService[]> {
    return fetchWithAuth<CandidateTopService[]>(
      `/api/analytics/search/candidates/top-services?days=${days}&limit=${limit}`,
      token
    );
  }
  ,
  async getCandidateServiceQueries(
    token: string,
    service_catalog_id: string,
    days: number = 30,
    limit: number = 50
  ): Promise<Array<{ searched_at: string; search_query: string; results_count: number | null; position: number; score: number | null; source: string | null }>> {
    return fetchWithAuth(
      `/api/analytics/search/candidates/queries?service_catalog_id=${service_catalog_id}&days=${days}&limit=${limit}`,
      token
    );
  },
  async getCandidateScoreDistribution(
    token: string,
    days: number = 30
  ): Promise<{ gte_0_90: number; gte_0_80_lt_0_90: number; gte_0_70_lt_0_80: number; lt_0_70: number }> {
    return fetchWithAuth(`/api/analytics/search/candidates/score-distribution?days=${days}`, token);
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
    return fetchWithAuth<CodebaseMetricsResponse>('/api/analytics/codebase/metrics', token);
  },
  async getCodebaseHistory(token: string): Promise<{ items: CodebaseHistoryEntry[] }> {
    return fetchWithAuth<{ items: CodebaseHistoryEntry[] }>('/api/analytics/codebase/history', token);
  },
};
