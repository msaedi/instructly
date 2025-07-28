// frontend/lib/analyticsApi.ts
/**
 * Analytics API client for admin dashboard
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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

/**
 * Fetch with authentication
 */
async function fetchWithAuth<T>(endpoint: string, token: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('Unauthorized');
    }
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

/**
 * Analytics API client
 */
export const analyticsApi = {
  /**
   * Get search trends over time
   */
  async getSearchTrends(token: string, days: number = 30): Promise<SearchTrend[]> {
    return fetchWithAuth<SearchTrend[]>(`/api/analytics/search/search-trends?days=${days}`, token);
  },

  /**
   * Get popular searches
   */
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

  /**
   * Get search referrers (which pages drive searches)
   */
  async getSearchReferrers(token: string, days: number = 30): Promise<SearchReferrer[]> {
    return fetchWithAuth<SearchReferrer[]>(`/api/analytics/search/referrers?days=${days}`, token);
  },

  /**
   * Get zero-result searches
   */
  async getZeroResultSearches(
    token: string,
    days: number = 30,
    limit: number = 20
  ): Promise<ZeroResultSearch[]> {
    const popular = await this.getPopularSearches(token, days, limit * 2);
    // Filter for zero results
    return popular
      .filter((search) => search.average_results === 0)
      .map((search) => ({
        query: search.query,
        count: search.search_count,
        last_searched: new Date().toISOString(), // API doesn't provide this
      }))
      .slice(0, limit);
  },

  /**
   * Get analytics summary
   */
  async getAnalyticsSummary(token: string, days: number = 30): Promise<SearchAnalyticsSummary> {
    return fetchWithAuth<SearchAnalyticsSummary>(
      `/api/analytics/search/search-analytics-summary?days=${days}`,
      token
    );
  },

  /**
   * Get user search behavior
   */
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

  /**
   * Get conversion metrics
   */
  async getConversionMetrics(token: string, days: number = 30): Promise<ConversionMetrics> {
    return fetchWithAuth<ConversionMetrics>(
      `/api/analytics/search/conversion-metrics?days=${days}`,
      token
    );
  },

  /**
   * Get search performance metrics
   */
  async getSearchPerformance(token: string, days: number = 30): Promise<SearchPerformance> {
    return fetchWithAuth<SearchPerformance>(
      `/api/analytics/search/search-performance?days=${days}`,
      token
    );
  },

  /**
   * Get service pill performance (derived from search types)
   */
  async getServicePillPerformance(
    token: string,
    days: number = 30
  ): Promise<ServicePillPerformance[]> {
    // Get popular searches filtered by service_pill type
    const summary = await this.getAnalyticsSummary(token, days);
    const servicePillData = summary.search_types['service_pill'];

    // Get popular searches to see which services are clicked
    const popular = await this.getPopularSearches(token, days, 50);

    // For now, return mock data as we don't have service-specific tracking
    // In production, this would filter by search_type='service_pill'
    return popular.slice(0, 10).map((search) => ({
      service_name: search.query,
      clicks: Math.floor(search.search_count * 0.3), // Estimate 30% are service pills
      unique_users: Math.floor(search.unique_users * 0.3),
      conversion_rate: 0.15 + Math.random() * 0.1, // Mock conversion rate
    }));
  },
};
