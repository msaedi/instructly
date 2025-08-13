// frontend/features/shared/api/client.ts
/**
 * Clean API Client for Student Features
 *
 * A simple, clean fetch-based API client that doesn't rely on legacy patterns.
 * Used for all new student-facing features.
 */

import { getSessionId, refreshSession } from '@/lib/sessionTracking';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * API response type for consistent error handling
 */
export interface ApiResponse<T> {
  data?: T;
  error?: string;
  status: number;
}

/**
 * Public API endpoints (no authentication required)
 */
export const PUBLIC_ENDPOINTS = {
  instructors: {
    list: '/instructors', // Note: This is the actual backend endpoint
    profile: (id: string) => `/instructors/${id}`,
    availability: (id: string) => `/api/public/instructors/${id}/availability`,
  },
} as const;

/**
 * Protected API endpoints (authentication required)
 */
export const PROTECTED_ENDPOINTS = {
  bookings: {
    create: '/bookings/',
    list: '/bookings/',
    get: (id: string) => `/bookings/${id}`,
    cancel: (id: string) => `/bookings/${id}/cancel`,
  },
} as const;

/**
 * Fetch options with common defaults
 */
interface FetchOptions extends RequestInit {
  params?: Record<string, string | number | boolean>;
}

/**
 * Get analytics headers for all requests
 */
function getAnalyticsHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};

  if (typeof window !== 'undefined') {
    // Browser session ID for journey tracking
    const sessionId = getSessionId();
    if (sessionId) {
      headers['X-Session-ID'] = sessionId;
    }

    // Current page path for referrer analytics
    headers['X-Search-Origin'] = window.location.pathname;
  }

  return headers;
}

/**
 * Get guest session ID from localStorage
 */
function getGuestSessionId(): string | null {
  if (typeof window === 'undefined') return null;

  const guestSessionId = localStorage.getItem('guest_session_id');
  return guestSessionId;
}

/**
 * Unified fetch wrapper for search history endpoints
 * Works for both authenticated users and guests
 */
async function unifiedFetch<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<ApiResponse<T>> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const guestSessionId = getGuestSessionId();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getAnalyticsHeaders(),
    ...((options.headers as Record<string, string>) || {}),
  };

  // Add auth token if available
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  // Otherwise add guest session ID if available
  else if (guestSessionId) {
    headers['X-Guest-Session-ID'] = guestSessionId;
  }

  return cleanFetch<T>(endpoint, {
    ...options,
    headers,
  });
}

/**
 * Clean fetch wrapper with error handling
 */
async function cleanFetch<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<ApiResponse<T>> {
  const { params, ...fetchOptions } = options;

  // Build URL with query params
  const url = new URL(`${API_BASE_URL}${endpoint}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, String(value));
      }
    });
  }

  try {
    const response = await fetch(url.toString(), {
      ...fetchOptions,
      headers: {
        'Content-Type': 'application/json',
        ...getAnalyticsHeaders(),
        ...((fetchOptions.headers as Record<string, string>) || {}),
      },
    });

    const data = await response.json();

    if (!response.ok) {
      return {
        error: data.detail || `Error: ${response.status}`,
        status: response.status,
      };
    }

    return {
      data,
      status: response.status,
    };
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Network error',
      status: 0,
    };
  }
}

/**
 * Optional authenticated fetch wrapper
 * Includes auth token if available, but doesn't fail if not authenticated
 */
async function optionalAuthFetch<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<ApiResponse<T>> {
  const { params, ...fetchOptions } = options;

  // Build URL with query params
  const url = new URL(`${API_BASE_URL}${endpoint}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.append(key, String(value));
      }
    });
  }

  // Get token if available
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  try {
    const response = await fetch(url.toString(), {
      ...fetchOptions,
      headers: {
        'Content-Type': 'application/json',
        ...getAnalyticsHeaders(),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...((fetchOptions.headers as Record<string, string>) || {}),
      },
    });

    const data = await response.json();

    if (!response.ok) {
      return {
        error: data.detail || `Error: ${response.status}`,
        status: response.status,
      };
    }

    return {
      data,
      status: response.status,
    };
  } catch (error) {
    return {
      error: error instanceof Error ? error.message : 'Network error',
      status: 0,
    };
  }
}

/**
 * Authenticated fetch wrapper
 */
async function authFetch<T>(endpoint: string, options: FetchOptions = {}): Promise<ApiResponse<T>> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;

  if (!token) {
    return {
      error: 'Not authenticated',
      status: 401,
    };
  }

  return cleanFetch<T>(endpoint, {
    ...options,
    headers: {
      ...((options.headers as Record<string, string>) || {}),
      Authorization: `Bearer ${token}`,
    },
  });
}

/**
 * Natural language search response type
 */
export interface NaturalLanguageSearchResponse {
  query?: string;
  parsed: {
    original_query: string;
    cleaned_query: string;
    service_query?: string;
    price: {
      max?: number;
      min?: number;
    };
    time: {
      date?: string;
      time_of_day?: string;
    };
    location: {
      area?: string;
      type?: string;
    };
    level: {
      skill_level?: string;
    };
    constraints?: {
      max_price?: number;
      date?: string;
      location?: string;
    };
  };
  results: Array<{
    service: {
      id: number;
      category_id: number;
      category_name: string;
      category_slug: string;
      name: string;
      slug: string;
      description: string;
      search_terms: string[];
      actual_min_price: number;
      actual_max_price: number;
      display_order: number;
      related_services: any[];
      online_capable: boolean;
      requires_certification: boolean;
      is_active: boolean;
      is_offered: boolean;
      instructor_count: number;
      relevance_score: number;
      demand_score: number;
      is_trending: boolean;
    };
    instructor: {
      id: number;
      first_name: string;
      last_initial: string;  // Privacy protected
      bio: string;
      years_experience: number;
      areas_of_service: string;
    };
    offering: {
      id: number;
      hourly_rate: number;
      experience_level: string;
      description: string;
      duration_options: number[];
      equipment_required: string[];
      levels_taught: string[];
      age_groups: string[];
      location_types: string[];
      max_distance_miles: number;
    };
    match_score: number;
  }>;
  total_found: number;
  search_metadata?: {
    search_time_ms: number;
    embedding_time_ms: number;
  };
}

/**
 * Public API client for student features
 */
/**
 * Service catalog API types
 */
export interface ServiceCategory {
  id: number;
  name: string;
  slug: string;
  subtitle: string;
  description: string;
  display_order: number;
  icon_name?: string;
}

export interface CatalogService {
  id: number;
  category_id: number;
  name: string;
  slug: string;
  description: string;
  search_terms: string[];
  display_order: number;
  online_capable: boolean;
  requires_certification: boolean;
  is_active: boolean;
  actual_min_price?: number;
  actual_max_price?: number;
  instructor_count?: number;
}

export interface TopServiceSummary {
  id: number;
  name: string;
  slug: string;
  demand_score: number;
  active_instructors: number;
  is_trending: boolean;
  display_order: number;
}

export interface CategoryWithTopServices {
  id: number;
  name: string;
  slug: string;
  icon_name?: string;
  services: TopServiceSummary[];
}

export interface TopServicesResponse {
  categories: CategoryWithTopServices[];
}

export const publicApi = {
  /**
   * Natural language search for instructors and services
   * Uses AI-powered search to understand queries like "piano lessons under $50 today"
   */
  async searchWithNaturalLanguage(
    query: string
  ): Promise<ApiResponse<NaturalLanguageSearchResponse>> {
    // Use optionalAuthFetch to allow unauthenticated searches
    // but include auth token if available for search history tracking
    return optionalAuthFetch<NaturalLanguageSearchResponse>('/api/search/instructors', {
      params: { q: query },
    });
  },

  /**
   * Get recent search history (unified for authenticated and guest users)
   * For guests, pass X-Guest-Session-ID header
   */
  async getRecentSearches(limit: number = 3) {
    return unifiedFetch<
      Array<{
        id: number;
        search_query: string;
        search_type: string;
        results_count: number | null;
        created_at: string;
        first_searched_at: string;
        last_searched_at: string;
        search_count: number;
      }>
    >('/api/search-history/', {
      params: { limit },
    });
  },

  /**
   * Delete a search from history (unified for authenticated and guest users)
   * For guests, pass X-Guest-Session-ID header
   */
  async deleteSearchHistory(searchId: number) {
    return unifiedFetch<void>(`/api/search-history/${searchId}`, {
      method: 'DELETE',
    });
  },

  /**
   * Record a search to history (unified for authenticated and guest users)
   * For guests, pass X-Guest-Session-ID header
   */
  async recordSearchHistory(data: {
    search_query: string;
    search_type: string;
    results_count?: number | null;
    search_context?: any;
  }) {
    // Refresh session on search activity
    refreshSession();

    // Add analytics context if not provided
    const searchData = {
      ...data,
      search_context: data.search_context || {
        page: typeof window !== 'undefined' ? window.location.pathname : '/',
        viewport:
          typeof window !== 'undefined' ? `${window.innerWidth}x${window.innerHeight}` : '0x0',
        timestamp: new Date().toISOString(),
      },
    };

    return unifiedFetch<{
      id: number;
      search_query: string;
      search_type: string;
      results_count: number | null;
      created_at: string;
      first_searched_at: string;
      last_searched_at: string;
      search_count: number;
    }>('/api/search-history/', {
      method: 'POST',
      body: JSON.stringify(searchData),
    });
  },

  // Legacy methods for backward compatibility - can be removed once all components are updated
  /**
   * @deprecated Use recordSearchHistory with appropriate headers instead
   */
  async recordGuestSearchHistory(data: {
    guest_session_id: string;
    search_query: string;
    search_type: string;
    results_count?: number | null;
  }) {
    return cleanFetch<{
      id: number;
      search_query: string;
      search_type: string;
      results_count: number | null;
      created_at: string;
      guest_session_id: string;
    }>('/api/search-history/guest', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * @deprecated Use getRecentSearches with appropriate headers instead
   */
  async getGuestRecentSearches(guestSessionId: string, limit: number = 3) {
    return cleanFetch<
      Array<{
        id: number;
        search_query: string;
        search_type: string;
        results_count: number | null;
        created_at: string;
      }>
    >('/api/search-history/guest/' + guestSessionId, {
      params: { limit },
    });
  },

  /**
   * @deprecated Use deleteSearchHistory with appropriate headers instead
   */
  async deleteGuestSearchHistory(guestSessionId: string, searchId: number) {
    return cleanFetch<void>(`/api/search-history/guest/${guestSessionId}/${searchId}`, {
      method: 'DELETE',
    });
  },

  /**
   * Search for instructors by service ID (service-first model)
   * Note: service_catalog_id is now required
   */
  async searchInstructors(params: {
    service_catalog_id: number; // Required: Service catalog ID
    min_price?: number; // Minimum hourly rate
    max_price?: number; // Maximum hourly rate
    page?: number; // Page number (1-based)
    per_page?: number; // Items per page
  }) {
    // Backend now always returns standardized paginated response
    return cleanFetch<{
      items: Array<{
        id: number;
        user_id: number;
        bio: string;
        areas_of_service: string[];
        years_experience: number;
        min_advance_booking_hours: number;
        buffer_time_minutes: number;
        created_at: string;
        updated_at?: string;
        user: {
          id: number;
          first_name: string;
          last_initial: string;
          // No email for privacy
        };
        services: Array<{
          id: number;
          service_catalog_id: number;
          hourly_rate: number;
          description?: string;
          duration_options: number[];
          is_active?: boolean;
        }>;
      }>;
      total: number;
      page: number;
      per_page: number;
      has_next: boolean;
      has_prev: boolean;
    }>(PUBLIC_ENDPOINTS.instructors.list, {
      params,
    });
  },

  /**
   * Get instructor profile
   */
  async getInstructorProfile(instructorId: string) {
    return cleanFetch<{
      user_id: number;
      bio: string;
      areas_of_service: string[];
      years_experience: number;
      min_advance_booking_hours: number;
      buffer_time_minutes: number;
      created_at: string;
      updated_at?: string;
      user: {
        first_name: string;
        last_initial: string;
        // No email for privacy
      };
      services: Array<{
        id: number;
        service_catalog_id: number;
        name?: string;
        hourly_rate: number;
        description?: string;
        duration_options: number[];
        is_active?: boolean;
      }>;
      rating?: number;
      total_reviews?: number;
      total_hours_taught?: number;
      education?: string;
      languages?: string[];
      verified?: boolean;
    }>(PUBLIC_ENDPOINTS.instructors.profile(instructorId));
  },

  /**
   * Get instructor availability
   */
  async getInstructorAvailability(
    instructorId: string,
    params: {
      start_date: string;
      end_date: string;
    }
  ) {
    return cleanFetch<{
      instructor_id: number;
      instructor_first_name: string | null;
      instructor_last_initial: string | null;
      availability_by_date: Record<
        string,
        {
          date: string;
          available_slots: Array<{
            start_time: string;
            end_time: string;
          }>;
          is_blackout: boolean;
        }
      >;
      timezone: string;
      total_available_slots: number;
      earliest_available_date: string;
    }>(PUBLIC_ENDPOINTS.instructors.availability(instructorId), {
      params,
    });
  },

  /**
   * Get all service categories
   */
  async getServiceCategories() {
    return cleanFetch<ServiceCategory[]>('/services/categories');
  },

  /**
   * Get catalog services, optionally filtered by category
   */
  async getCatalogServices(categorySlug?: string) {
    return cleanFetch<CatalogService[]>('/services/catalog', {
      params: categorySlug ? { category: categorySlug } : {},
    });
  },

  /**
   * Get top services per category - optimized for homepage
   * Returns all categories with their top services in a single request
   */
  async getTopServicesPerCategory() {
    return cleanFetch<TopServicesResponse>('/services/catalog/top-per-category');
  },

  /**
   * Get all services with instructor counts - optimized for All Services page
   * Returns all categories with all their services and active instructor counts
   */
  async getAllServicesWithInstructors() {
    return cleanFetch<{
      categories: Array<{
        id: number;
        name: string;
        slug: string;
        subtitle: string;
        description: string;
        icon_name?: string;
        services: Array<
          CatalogService & {
            active_instructors: number;
            instructor_count: number;
            demand_score: number;
            is_trending: boolean;
            actual_min_price?: number;
            actual_max_price?: number;
          }
        >;
      }>;
      metadata: {
        total_categories: number;
        total_services: number;
        cached_for_seconds: number;
        updated_at: string;
      };
    }>('/services/catalog/all-with-instructors');
  },
};

/**
 * Booking type definitions
 */
export interface CreateBookingRequest {
  instructor_id: number;
  service_id: number;
  booking_date: string; // ISO date string (YYYY-MM-DD)
  start_time: string; // HH:MM format
  end_time: string; // HH:MM format
  selected_duration: number; // Duration in minutes
  student_note?: string;
  meeting_location?: string;
  location_type?: 'student_home' | 'instructor_location' | 'neutral';
}

export interface Booking {
  id: number;
  instructor_id: number;
  student_id: number;
  service_id: number;
  booking_date: string;
  start_time: string;
  end_time: string;
  status: 'pending' | 'confirmed' | 'cancelled' | 'completed';
  total_price: number;
  cancellation_reason?: string;
  student_note?: string;
  meeting_location?: string;
  location_type?: 'student_home' | 'instructor_location' | 'neutral';
  created_at: string;
  updated_at: string;
  instructor: {
    user_id: number;
    user: {
      first_name: string;
      last_initial: string;
      // No email for privacy
    };
  };
  service: {
    skill: string;
    hourly_rate: number;
  };
}

/**
 * Protected API client for authenticated features
 */
export const protectedApi = {
  /**
   * Create a new booking
   */
  async createBooking(data: CreateBookingRequest) {
    return authFetch<Booking>(PROTECTED_ENDPOINTS.bookings.create, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Get list of bookings for authenticated user
   */
  async getBookings(params?: {
    status?: 'pending' | 'confirmed' | 'cancelled' | 'completed';
    upcoming?: boolean;
    limit?: number;
    offset?: number;
  }) {
    return authFetch<{
      bookings: Booking[];
      total: number;
    }>(PROTECTED_ENDPOINTS.bookings.list, {
      params,
    });
  },

  /**
   * Get a specific booking
   */
  async getBooking(bookingId: string) {
    return authFetch<Booking>(PROTECTED_ENDPOINTS.bookings.get(bookingId));
  },

  /**
   * Cancel a booking
   */
  async cancelBooking(bookingId: string, reason?: string) {
    return authFetch<Booking>(PROTECTED_ENDPOINTS.bookings.cancel(bookingId), {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  },
};
