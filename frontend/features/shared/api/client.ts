// frontend/features/shared/api/client.ts
/**
 * Clean API Client for Student Features
 *
 * A simple, clean fetch-based API client that doesn't rely on legacy patterns.
 * Used for all new student-facing features.
 */

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
        ...fetchOptions.headers,
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
  const token = localStorage.getItem('access_token');

  if (!token) {
    return {
      error: 'Not authenticated',
      status: 401,
    };
  }

  return cleanFetch<T>(endpoint, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Bearer ${token}`,
    },
  });
}

/**
 * Public API client for student features
 */
export const publicApi = {
  /**
   * Search for instructors with backend filtering
   */
  async searchInstructors(params: {
    search?: string; // Text search across name, bio, skills
    skill?: string; // Filter by specific skill
    min_price?: number; // Minimum hourly rate
    max_price?: number; // Maximum hourly rate
    skip?: number; // Pagination offset
    limit?: number; // Page size
  }) {
    // Backend returns different formats based on whether filters are applied
    const hasFilters =
      params.search ||
      params.skill ||
      params.min_price !== undefined ||
      params.max_price !== undefined;

    if (hasFilters) {
      // With filters: returns object with instructors array and metadata
      return cleanFetch<{
        instructors: Array<{
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
            full_name: string;
            email: string;
          };
          services: Array<{
            id: number;
            skill: string;
            hourly_rate: number;
            description?: string;
            duration_override?: number;
            duration: number;
            is_active?: boolean;
          }>;
        }>;
        metadata: {
          filters_applied: Record<string, any>;
          pagination: {
            skip: number;
            limit: number;
            count: number;
          };
          total_matches: number;
          active_instructors: number;
        };
      }>(PUBLIC_ENDPOINTS.instructors.list, {
        params,
      });
    } else {
      // No filters: returns simple array
      return cleanFetch<
        Array<{
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
            full_name: string;
            email: string;
          };
          services: Array<{
            id: number;
            skill: string;
            hourly_rate: number;
            description?: string;
            duration_override?: number;
            duration: number;
          }>;
        }>
      >(PUBLIC_ENDPOINTS.instructors.list, {
        params,
      });
    }
  },

  /**
   * Get instructor profile
   */
  async getInstructorProfile(instructorId: string) {
    return cleanFetch<{
      id: string;
      user: {
        first_name: string;
        last_name: string;
        email: string;
      };
      bio: string;
      subjects: string[];
      hourly_rate: number;
      rating: number;
      total_reviews: number;
      total_hours_taught: number;
      years_of_experience: number;
      education: string;
      languages: string[];
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
      instructor_name: string;
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
      full_name: string;
      email: string;
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
