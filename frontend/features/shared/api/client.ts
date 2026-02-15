// frontend/features/shared/api/client.ts
/**
 * Clean API Client for Student Features
 *
 * A simple, clean fetch-based API client that doesn't rely on legacy patterns.
 * Used for all new student-facing features.
 */

import { getSessionId, refreshSession } from '@/lib/sessionTracking';
import { withApiBaseForRequest } from '@/lib/apiBase';
import { NEXT_PUBLIC_APP_URL as APP_URL } from '@/lib/env';
import { logger } from '@/lib/logger';
import type {
  AgeGroup,
  ApiErrorResponse,
  AllServicesWithInstructorsResponse,
  BookingCreate,
  CategoryDetail as ApiCategoryDetail,
  CategorySummary as ApiCategorySummary,
  CategoryTreeNode,
  CategoryWithSubcategories,
  components,
  CatalogService as ApiCatalogService,
  CatalogServiceMinimal,
  FilterValidationResponse as ApiFilterValidationResponse,
  InstructorFilterContext as ApiInstructorFilterContext,
  InstructorService as ApiInstructorService,
  NaturalLanguageSearchResponse as GenNaturalLanguageSearchResponse,
  Booking,
  BookingStatus,
  SearchHistoryResponse,
  ServiceCatalogDetail as ApiServiceCatalogDetail,
  ServiceCatalogSummary as ApiServiceCatalogSummary,
  ServiceCategory as ApiServiceCategory,
  SubcategoryBrief as ApiSubcategoryBrief,
  SubcategoryDetail as ApiSubcategoryDetail,
  SubcategoryFilterResponse as ApiSubcategoryFilterResponse,
  SubcategoryWithServices as ApiSubcategoryWithServices,
  TopCategoryItem as ApiTopCategoryItem,
  TopCategoryServiceItem as ApiTopCategoryServiceItem,
  TopServicesPerCategoryResponse as ApiTopServicesPerCategoryResponse,
  UpdateFilterSelectionsRequest,
  ValidateFiltersRequest,
} from '@/features/shared/api/types';

// Type aliases for generated types
// Keep generated type imports for future use
export type PaginatedBookingResponse = components['schemas']['PaginatedResponse_BookingResponse_'];
type InstructorProfileResponse = components['schemas']['InstructorProfileResponse'];

export type InstructorBookingsParams = {
  page?: number;
  per_page?: number;
  status?: BookingStatus;
  upcoming?: boolean;
  signal?: AbortSignal | undefined;
};

// Browser calls go through Next.js proxy to avoid CORS and proxy redirects
// Ensure an absolute base URL for URL construction
function getRequestOrigin(): string {
  if (typeof window !== 'undefined') {
    return window.location.origin;
  }
  return APP_URL || 'http://localhost:3000';
}

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
 *
 * ✅ MIGRATED TO V1 - All instructor endpoints now use /api/v1/instructors
 */
export const PUBLIC_ENDPOINTS = {
  instructors: {
    list: '/api/v1/instructors', // Migrated to v1
    profile: (id: string) => `/api/v1/instructors/${id}`, // Migrated to v1
    availability: (id: string) => `/api/v1/public/instructors/${id}/availability`, // Migrated to v1 Phase 18
  },
} as const;

/**
 * Protected API endpoints (authentication required)
 */
export const PROTECTED_ENDPOINTS = {
  bookings: {
    create: '/api/v1/bookings',
    list: '/api/v1/bookings',
    get: (id: string) => `/api/v1/bookings/${id}`,
    cancel: (id: string) => `/api/v1/bookings/${id}/cancel`,
    reschedule: (id: string) => `/api/v1/bookings/${id}/reschedule`,
  },
  instructor: {
    bookings: {
      list: '/api/v1/instructor-bookings/',
      completed: '/api/v1/instructor-bookings/completed',
      upcoming: '/api/v1/instructor-bookings/upcoming',
    },
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
 * Get guest session ID from cookie (preferred) or sessionStorage fallback
 */
function getGuestSessionId(): string | null {
  if (typeof document === 'undefined') return null;
  const fromCookie = document.cookie.split('; ').find(c => c.startsWith('guest_id='));
  if (fromCookie) return decodeURIComponent(fromCookie.split('=')[1] || '');
  try {
    return sessionStorage.getItem('guest_session_id');
  } catch {
    return null;
  }
}

/**
 * Unified fetch wrapper for search history endpoints
 * Works for both authenticated users and guests
 */
async function unifiedFetch<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<ApiResponse<T>> {
  const guestSessionId = getGuestSessionId();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getAnalyticsHeaders(),
    ...((options.headers as Record<string, string>) || {}),
  };

  // Add guest session ID if available (for unified guest tracking)
  if (guestSessionId) {
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
export async function cleanFetch<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<ApiResponse<T>> {
  const { params, ...fetchOptions } = options;
  const resolvedEndpoint = withApiBaseForRequest(endpoint, fetchOptions.method ?? 'GET');

  // Build URL with query params (support relative endpoints in browser/SSR)
  const isAbsolute = /^https?:\/\//i.test(resolvedEndpoint);
  let url: URL;
  if (isAbsolute) {
    url = new URL(resolvedEndpoint);
  } else if (typeof window !== 'undefined') {
    // Respect proxy toggle for browser requests
    // Don't double-apply proxy prefix if already present
    const adjustedPath = resolvedEndpoint.startsWith('/api/proxy')
      ? resolvedEndpoint
      : withApiBaseForRequest(resolvedEndpoint, fetchOptions.method ?? 'GET');
    url = new URL(adjustedPath, window.location.origin);
  } else {
    const base = getRequestOrigin();
    url = new URL(resolvedEndpoint, base);
  }
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
      // Always include credentials so session cookies (__Host-sid_*) are sent
      credentials: fetchOptions?.credentials ?? 'include',
    });

    const retryAfterHeader = response.headers.get('Retry-After');
    const retryAfterSeconds = retryAfterHeader ? parseInt(retryAfterHeader, 10) : undefined;

    let data: ApiErrorResponse | T | null = null;
    if (response.status !== 204 && response.status !== 205) {
      try {
        data = (await response.json()) as ApiErrorResponse | T;
      } catch (parseError) {
        logger.error('Failed to parse API response as JSON', {
          url: url.toString(),
          status: response.status,
          error: parseError instanceof Error ? parseError.message : String(parseError),
        });
        if (response.ok) {
          return {
            error: 'Invalid response format',
            status: response.status,
          };
        }
        data = null;
      }
    }

    if (!response.ok) {
      // Normalize rate limit errors for callers
      if (response.status === 429) {
        const secs = Number.isFinite(retryAfterSeconds) ? retryAfterSeconds! : undefined;
        return {
          // Friendly user-facing copy
          error: secs ? `Our hamsters are sprinting. Give them ${secs}s.` : 'Our hamsters are sprinting. Please try again shortly.',
          status: 429,
          retryAfterSeconds: secs,
        } as ApiResponse<T> & { retryAfterSeconds?: number };
      }

      const detailValue = (data as ApiErrorResponse | null)?.detail;
      const errorValue =
        detailValue !== undefined && detailValue !== null
          ? typeof detailValue === 'string'
            ? detailValue
            : JSON.stringify(detailValue)
          : `Error: ${response.status}`;
      return {
        error: errorValue,
        status: response.status,
      };
    }

    return {
      data: data as T,
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
 * Fetch normalized place details for a suggestion.
 */
export async function getPlaceDetails(params: {
  place_id: string;
  provider?: string;
  signal?: AbortSignal;
}): Promise<ApiResponse<components['schemas']['PlaceDetails']>> {
  const { place_id, provider, signal } = params;
  const searchParams = new URLSearchParams({ place_id });
  if (provider) {
    searchParams.set('provider', provider);
  }

  const options: FetchOptions = {};
  if (signal) {
    options.signal = signal;
  }

  return cleanFetch<components['schemas']['PlaceDetails']>(
    `/api/v1/addresses/places/details?${searchParams.toString()}`,
    options
  );
}

/**
 * Optional authenticated fetch wrapper
 * Includes auth token if available, but doesn't fail if not authenticated
 */
async function optionalAuthFetch<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<ApiResponse<T>> {
  const mergedHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getAnalyticsHeaders(),
    ...((options.headers as Record<string, string>) || {}),
  };

  // Delegate to cleanFetch to get normalized 429 handling
  return cleanFetch<T>(endpoint, {
    ...options,
    headers: mergedHeaders,
  });
}

/**
 * Authenticated fetch wrapper
 */
async function authFetch<T>(endpoint: string, options: FetchOptions = {}): Promise<ApiResponse<T>> {
  return cleanFetch<T>(endpoint, {
    ...options,
  });
}

/**
 * Natural language search response type
 */
export type NaturalLanguageSearchResponse = GenNaturalLanguageSearchResponse;

/**
 * Public API client for student features
 */
/**
 * Service catalog API types
 */
export type ServiceCategory = ApiServiceCategory;
export type CatalogService = ApiCatalogService;
export type TopServiceSummary = ApiTopCategoryServiceItem;
export type CategoryWithTopServices = ApiTopCategoryItem;
export type TopServicesResponse = ApiTopServicesPerCategoryResponse;

const SEARCH_HISTORY_API_BASE = '/api/v1/search-history';

export const publicApi = {
  /**
   * Natural language search for instructors and services
   * Uses AI-powered search to understand queries like "piano lessons under $50 today"
   */
  async searchWithNaturalLanguage(
    query: string,
    params?: {
      skill_level?: string;
      subcategory_id?: string;
      content_filters?: string;
    }
  ): Promise<ApiResponse<GenNaturalLanguageSearchResponse>> {
    // Use optionalAuthFetch to allow unauthenticated searches
    // but include auth token if available for search history tracking
    return optionalAuthFetch<GenNaturalLanguageSearchResponse>('/api/v1/search', {
      params: {
        q: query,
        ...(params?.skill_level ? { skill_level: params.skill_level } : {}),
        ...(params?.subcategory_id ? { subcategory_id: params.subcategory_id } : {}),
        ...(params?.content_filters ? { content_filters: params.content_filters } : {}),
      },
    });
  },

  /**
   * Get recent search history (unified for authenticated and guest users)
   * For guests, pass X-Guest-Session-ID header
   */
  async getRecentSearches(limit: number = 3) {
    return unifiedFetch<SearchHistoryResponse[]>(SEARCH_HISTORY_API_BASE, {
      params: { limit },
    });
  },

  /**
   * Delete a search from history (unified for authenticated and guest users)
   * For guests, pass X-Guest-Session-ID header
   */
  async deleteSearchHistory(searchId: number) {
    return unifiedFetch<void>(`${SEARCH_HISTORY_API_BASE}/${String(searchId)}`, {
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
    search_context?: Record<string, unknown>;
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
      id: string;
      search_query: string;
      search_type: string;
      results_count: number | null;
      created_at: string;
      first_searched_at: string;
      last_searched_at: string;
      search_count: number;
    }>(SEARCH_HISTORY_API_BASE, {
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
      id: string;
      search_query: string;
      search_type: string;
      results_count: number | null;
      created_at: string;
      guest_session_id: string;
    }>(`${SEARCH_HISTORY_API_BASE}/guest`, {
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
        id: string;
        search_query: string;
        search_type: string;
        results_count: number | null;
        created_at: string;
      }>
    >(`${SEARCH_HISTORY_API_BASE}/guest/${guestSessionId}`, {
      params: { limit },
    });
  },

  /**
   * @deprecated Use deleteSearchHistory with appropriate headers instead
   */
  async deleteGuestSearchHistory(guestSessionId: string, searchId: number) {
    return cleanFetch<void>(`${SEARCH_HISTORY_API_BASE}/guest/${guestSessionId}/${searchId}`, {
      method: 'DELETE',
    });
  },

  /**
   * Search for instructors by service ID (service-first model)
   * Note: service_catalog_id is now required
   */
  async searchInstructors(params: {
    service_catalog_id: string; // Required: Service catalog ID (ULID string)
    min_price?: number; // Minimum hourly rate
    max_price?: number; // Maximum hourly rate
    skill_level?: string; // Comma-separated skill levels
    subcategory_id?: string; // Optional subcategory context for taxonomy filtering
    content_filters?: string; // Taxonomy content filters: key:val1,val2|key2:val3
    page?: number; // Page number (1-based)
    per_page?: number; // Items per page
  }) {
    // Backend now always returns standardized paginated response
    return cleanFetch<{
      items: Array<{
        id: string;  // ULID string
        user_id: string;  // ULID string
        bio: string;
        service_area_boroughs?: string[];
        service_area_neighborhoods?: Array<{
          neighborhood_id: string;
          ntacode?: string | null;
          name?: string | null;
          borough?: string | null;
        }>;
        service_area_summary?: string | null;
        years_experience: number;
        min_advance_booking_hours: number;
        buffer_time_minutes: number;
        created_at: string;
        updated_at?: string;
        user: {
          id: string;  // ULID string
          first_name: string;
          last_initial: string;
          // No email for privacy
        };
        services: Array<{
          id: string;  // ULID string
          service_catalog_id: string;  // ULID string
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
   * Uses generated InstructorProfileResponse type
   */
  async getInstructorProfile(instructorId: string) {
    return optionalAuthFetch<InstructorProfileResponse>(PUBLIC_ENDPOINTS.instructors.profile(instructorId));
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
      instructor_id: string;
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
    return cleanFetch<ServiceCategory[]>('/api/v1/services/categories');
  },

  /**
   * Get catalog services, optionally filtered by category ID
   */
  async getCatalogServices(categoryId?: string) {
    return cleanFetch<CatalogService[]>('/api/v1/services/catalog', {
      params: categoryId ? { category_id: categoryId } : {},
    });
  },

  /**
   * Get top services per category - optimized for homepage
   * Returns all categories with their top services in a single request
   */
  async getTopServicesPerCategory() {
    return cleanFetch<TopServicesResponse>('/api/v1/services/catalog/top-per-category');
  },

  /**
   * Get all services with instructor counts - optimized for All Services page
   * Returns all categories with all their services and active instructor counts
   */
  async getAllServicesWithInstructors() {
    return cleanFetch<AllServicesWithInstructorsResponse>('/api/v1/services/catalog/all-with-instructors');
  },

  /**
   * Get services that have at least one kids-capable instructor
   * Returns minimal entries for pills: { id, name, slug }
   */
  async getKidsAvailableServices() {
    return cleanFetch<CatalogServiceMinimal[]>('/api/v1/services/catalog/kids-available');
  },

  // ── 3-level taxonomy endpoints ────────────────────────────────

  /**
   * Get all categories with subcategory briefs (for browse page)
   */
  async getCategoriesWithSubcategories() {
    return cleanFetch<CategoryWithSubcategories[]>('/api/v1/services/categories/browse');
  },

  /**
   * Get full 3-level tree for a category (category → subcategories → services)
   */
  async getCategoryTree(categoryId: string) {
    return cleanFetch<CategoryTreeNode>(`/api/v1/services/categories/${categoryId}/tree`);
  },

  /**
   * Get subcategories for a category (lightweight briefs)
   */
  async getSubcategoriesByCategory(categoryId: string) {
    return cleanFetch<ApiSubcategoryBrief[]>(`/api/v1/services/categories/${categoryId}/subcategories`);
  },

  /**
   * Get a subcategory with its services
   */
  async getSubcategoryWithServices(subcategoryId: string) {
    return cleanFetch<ApiSubcategoryWithServices>(`/api/v1/services/subcategories/${subcategoryId}`);
  },

  /**
   * Get available filters for a subcategory
   */
  async getSubcategoryFilters(subcategoryId: string) {
    return cleanFetch<ApiSubcategoryFilterResponse[]>(`/api/v1/services/subcategories/${subcategoryId}/filters`);
  },

  /**
   * Get catalog services eligible for a specific age group
   */
  async getServicesByAgeGroup(ageGroup: AgeGroup) {
    return cleanFetch<ApiCatalogService[]>(`/api/v1/services/catalog/by-age-group/${ageGroup}`);
  },

  /**
   * Get filter context for instructor service editing (available filters + current selections)
   */
  async getServiceFilterContext(serviceId: string) {
    return cleanFetch<ApiInstructorFilterContext>(`/api/v1/services/catalog/${serviceId}/filter-context`);
  },

  // ── Slug-based catalog browse endpoints ─────────────────────

  /**
   * List all active categories with subcategory counts
   */
  async listCatalogCategories() {
    return cleanFetch<ApiCategorySummary[]>('/api/v1/catalog/categories');
  },

  /**
   * Get category detail by slug with subcategory listing
   */
  async getCatalogCategory(slug: string) {
    return cleanFetch<ApiCategoryDetail>(`/api/v1/catalog/categories/${encodeURIComponent(slug)}`);
  },

  /**
   * Get subcategory detail by slug pair with services and filters
   */
  async getCatalogSubcategory(categorySlug: string, subcategorySlug: string) {
    return cleanFetch<ApiSubcategoryDetail>(`/api/v1/catalog/categories/${encodeURIComponent(categorySlug)}/${encodeURIComponent(subcategorySlug)}`);
  },

  /**
   * Get single service detail by ID
   */
  async getCatalogService(serviceId: string) {
    return cleanFetch<ApiServiceCatalogDetail>(`/api/v1/catalog/services/${serviceId}`);
  },

  /**
   * List services in a subcategory by ID
   */
  async listCatalogSubcategoryServices(subcategoryId: string) {
    return cleanFetch<ApiServiceCatalogSummary[]>(`/api/v1/catalog/subcategories/${subcategoryId}/services`);
  },

  /**
   * Get filter definitions for a subcategory by ID
   */
  async getCatalogSubcategoryFilters(subcategoryId: string) {
    return cleanFetch<ApiSubcategoryFilterResponse[]>(`/api/v1/catalog/subcategories/${subcategoryId}/filters`);
  },
};

/**
 * Booking type definitions
 */
export type CreateBookingRequest = BookingCreate;

// Re-export generated Booking type for tests that import from this module
export type { Booking } from '@/features/shared/api/types';

type LowercaseBookingStatus = Lowercase<BookingStatus>;

type GetBookingsParams = {
  status?: BookingStatus | LowercaseBookingStatus;
  upcoming?: boolean;
  exclude_future_confirmed?: boolean;
  include_past_confirmed?: boolean;
  limit?: number;
  offset?: number;
  page?: number;
  per_page?: number;
  signal?: AbortSignal;
};

const normalizeBookingStatus = (
  status?: GetBookingsParams['status'],
): BookingStatus | undefined => {
  if (!status) return undefined;
  return String(status).toUpperCase() as BookingStatus;
};

/**
 * Protected API client for authenticated features
 */
async function fetchInstructorBookings(
  params: InstructorBookingsParams = {},
): Promise<ApiResponse<PaginatedBookingResponse>> {
  const { signal, ...rest } = params;
  const options: FetchOptions = {};
  if (signal) {
    options.signal = signal;
  }
  const normalized: Record<string, string | number | boolean> = {};
  Object.entries(rest).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      normalized[key] = value as string | number | boolean;
    }
  });
  if (typeof normalized['per_page'] === 'number' && normalized['per_page'] > 100) {
    normalized['per_page'] = 100;
  }
  if (Object.keys(normalized).length > 0) {
    options.params = normalized;
  }
  return authFetch<PaginatedBookingResponse>(
    PROTECTED_ENDPOINTS.instructor.bookings.list,
    options,
  );
}

/**
 * Protected API client for authenticated features
 */
export const protectedApi = {
  /**
   * Create a new booking
   * Uses generated type from OpenAPI
   */
  async createBooking(data: CreateBookingRequest) {
    return authFetch<Booking>(PROTECTED_ENDPOINTS.bookings.create, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Get list of bookings for authenticated user.
   * Normalizes `status` to the uppercase BookingStatus enum expected by the API.
   */
  async getBookings(params: GetBookingsParams = {}) {
    const { signal, ...rest } = params;
    const options: FetchOptions = {};

    if (signal) {
      options.signal = signal;
    }

    const { status, ...otherParams } = rest;
    const normalizedStatus = normalizeBookingStatus(status);
    const normalizedQuery: Record<string, string | number | boolean> = {};

    Object.entries(otherParams).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        normalizedQuery[key] = value as string | number | boolean;
      }
    });

    if (normalizedStatus) {
      normalizedQuery['status'] = normalizedStatus;
    }

    if (Object.keys(normalizedQuery).length > 0) {
      options.params = normalizedQuery;
    }

    // Use generated PaginatedBookingResponse type
    return authFetch<PaginatedBookingResponse>(PROTECTED_ENDPOINTS.bookings.list, options);
  },

  /**
   * Get a specific booking
   * Uses generated BookingResponse type
   */
  async getBooking(bookingId: string) {
    return authFetch<Booking>(PROTECTED_ENDPOINTS.bookings.get(bookingId));
  },

  async getInstructorBookings(params: InstructorBookingsParams = {}) {
    return fetchInstructorBookings(params);
  },

  async getInstructorUpcomingBookings(page: number = 1, perPage: number = 50, signal?: AbortSignal) {
    return authFetch<PaginatedBookingResponse>(PROTECTED_ENDPOINTS.instructor.bookings.upcoming, {
      params: { page, per_page: Math.min(perPage, 100) },
      signal: signal ?? null,
    });
  },

  async getInstructorCompletedBookings(page: number = 1, perPage: number = 50, signal?: AbortSignal) {
    return authFetch<PaginatedBookingResponse>(PROTECTED_ENDPOINTS.instructor.bookings.completed, {
      params: { page, per_page: Math.min(perPage, 100) },
      signal: signal ?? null,
    });
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

  // Add reschedule endpoint client
  async rescheduleBooking(
    bookingId: string,
    payload: { booking_date: string; start_time: string; selected_duration: number; instructor_service_id?: string }
  ) {
    return authFetch<Booking>(PROTECTED_ENDPOINTS.bookings.reschedule(bookingId), {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // ── Instructor filter management ────────────────────────────

  /**
   * Update filter selections on an instructor service
   */
  async updateFilterSelections(instructorServiceId: string, data: UpdateFilterSelectionsRequest) {
    return authFetch<ApiInstructorService>(`/api/v1/services/instructor/services/${instructorServiceId}/filters`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /**
   * Validate filter selections for a catalog service
   */
  async validateFilterSelections(data: ValidateFiltersRequest) {
    return authFetch<ApiFilterValidationResponse>('/api/v1/services/instructor/services/validate-filters', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
