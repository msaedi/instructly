// frontend/lib/api.ts
import { WeekSchedule, WeekValidationResponse } from '@/types/availability';
import { BookingPreview, UpcomingBooking } from '@/types/booking';
import { logger } from '@/lib/logger';

/**
 * API Client for InstaInstru Platform
 *
 * This module provides centralized API communication with proper authentication,
 * error handling, and logging. All API calls should go through these functions
 * to ensure consistent behavior across the application.
 *
 * Features:
 * - Automatic token management from localStorage
 * - Structured logging for all API calls
 * - Type-safe endpoint constants
 * - Specialized functions for complex operations
 *
 * @module api
 */

/** Base API URL from environment or default to localhost */
export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Helper function for authenticated requests
 *
 * Automatically adds the Authorization header with the JWT token from localStorage.
 * Logs all requests and responses for debugging.
 *
 * @param endpoint - API endpoint path (e.g., '/auth/me')
 * @param options - Standard fetch RequestInit options
 * @returns Promise<Response> - The fetch response
 *
 * @example
 * ```ts
 * const response = await fetchWithAuth('/instructors/me', {
 *   method: 'PUT',
 *   headers: { 'Content-Type': 'application/json' },
 *   body: JSON.stringify(profileData)
 * });
 * ```
 */
export const fetchWithAuth = async (endpoint: string, options: RequestInit = {}) => {
  const token = localStorage.getItem('access_token');
  const method = options.method || 'GET';

  // Log the API call
  logger.info(`API ${method} ${endpoint}`, {
    hasToken: !!token,
    hasBody: !!options.body,
  });

  // Start timing the request
  const timerLabel = `API ${method} ${endpoint}`;
  logger.time(timerLabel);

  try {
    const needsCookies = endpoint.startsWith('/auth/') || endpoint.startsWith('/api/auth/2fa');
    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      // Ensure trust/delete cookies flow for auth endpoints
      credentials: options.credentials ?? (needsCookies ? 'include' : 'same-origin'),
      headers: {
        ...options.headers,
        Authorization: token ? `Bearer ${token}` : '',
      },
    });

    // Log response details
    logger.timeEnd(timerLabel);

    if (response.ok) {
      logger.debug(`API ${method} ${endpoint} succeeded`, {
        status: response.status,
        statusText: response.statusText,
      });
    } else {
      // Log error responses with more detail
      logger.warn(`API ${method} ${endpoint} failed`, {
        status: response.status,
        statusText: response.statusText,
        endpoint,
      });

      // Try to get error details from response body
      try {
        const errorBody = await response.clone().json();
        // Downgrade 4xx (client/expected) to warn to avoid noisy console errors
        if (response.status >= 500) {
          logger.error('API error response body', undefined, {
            endpoint,
            status: response.status,
            error: errorBody,
          });
        } else {
          logger.warn('API error response', {
            endpoint,
            status: response.status,
          });
          logger.debug('API error body', { endpoint, error: errorBody });
        }
      } catch (e) {
        // Response body might not be JSON
        logger.debug('Could not parse error response as JSON');
      }
    }

    return response;
  } catch (error) {
    logger.timeEnd(timerLabel);
    logger.error(`API ${method} ${endpoint} network error`, error, {
      endpoint,
      method,
    });
    throw error;
  }
};

/**
 * Helper function for unauthenticated requests
 *
 * Used for public endpoints that don't require authentication.
 * Still provides consistent logging and error handling.
 *
 * @param endpoint - API endpoint path
 * @param options - Standard fetch RequestInit options
 * @returns Promise<Response> - The fetch response
 *
 * @example
 * ```ts
 * const response = await fetchAPI('/auth/login', {
 *   method: 'POST',
 *   headers: { 'Content-Type': 'application/json' },
 *   body: JSON.stringify({ email, password })
 * });
 * ```
 */
export const fetchAPI = async (endpoint: string, options: RequestInit = {}) => {
  const method = options.method || 'GET';

  logger.info(`API ${method} ${endpoint} (unauthenticated)`, {
    hasBody: !!options.body,
  });

  const timerLabel = `API ${method} ${endpoint}`;
  logger.time(timerLabel);

  try {
    const response = await fetch(`${API_URL}${endpoint}`, options);

    logger.timeEnd(timerLabel);

    if (response.ok) {
      logger.debug(`API ${method} ${endpoint} succeeded`, {
        status: response.status,
      });
    } else {
      logger.warn(`API ${method} ${endpoint} failed`, {
        status: response.status,
        statusText: response.statusText,
      });
    }

    return response;
  } catch (error) {
    logger.timeEnd(timerLabel);
    logger.error(`API ${method} ${endpoint} network error`, error, {
      endpoint,
      method,
    });
    throw error;
  }
};

/**
 * Common API endpoints as constants
 *
 * Centralized endpoint definitions to avoid typos and make refactoring easier.
 * Organized by feature area for better maintainability.
 */
export const API_ENDPOINTS = {
  // Auth endpoints
  LOGIN: '/auth/login',
  REGISTER: '/auth/register',
  ME: '/auth/me',

  // Instructor endpoints
  INSTRUCTORS: '/instructors',
  INSTRUCTOR_PROFILE: '/instructors/me',

  // Availability Management endpoints
  INSTRUCTOR_AVAILABILITY_WEEKLY: '/instructors/availability/weekly',
  INSTRUCTOR_AVAILABILITY_PRESET: '/instructors/availability/preset',
  INSTRUCTOR_AVAILABILITY_SPECIFIC: '/instructors/availability/specific-date',
  INSTRUCTOR_BLACKOUT_DATES: '/instructors/availability/blackout-dates',

  // Week-specific availability endpoints
  INSTRUCTOR_AVAILABILITY_WEEK: '/instructors/availability/week',
  INSTRUCTOR_AVAILABILITY_COPY_WEEK: '/instructors/availability/copy-week',
  INSTRUCTOR_AVAILABILITY_APPLY_RANGE: '/instructors/availability/apply-to-date-range',
  INSTRUCTOR_AVAILABILITY_BULK_UPDATE: '/instructors/availability/bulk-update',
  INSTRUCTOR_AVAILABILITY: '/instructors/availability/',
  INSTRUCTOR_AVAILABILITY_VALIDATE: '/instructors/availability/week/validate-changes',

  // Student availability checking
  CHECK_AVAILABILITY: '/api/availability/slots',

  // Booking endpoints
  BOOKINGS: '/bookings',
  BOOKINGS_UPCOMING: '/bookings/upcoming',

  // Add more endpoints as needed
} as const;

/**
 * Validate week schedule changes before saving
 *
 * Sends the current and saved week schedules to the backend for validation.
 * Returns detailed information about what changes will be made and any conflicts.
 *
 * @param currentWeek - The current week schedule in the UI
 * @param savedWeek - The saved week schedule from the backend
 * @param weekStart - The start date of the week
 * @returns Promise<WeekValidationResponse> - Validation results with conflicts and changes
 * @throws Error if validation fails
 *
 * @example
 * ```ts
 * try {
 *   const validation = await validateWeekChanges(currentWeek, savedWeek, weekStart);
 *   if (validation.has_conflicts) {
 *     // Show conflicts to user
 *   }
 * } catch (error) {
 *   // Handle validation error
 * }
 * ```
 */
export async function validateWeekChanges(
  currentWeek: WeekSchedule,
  savedWeek: WeekSchedule,
  weekStart: Date
): Promise<WeekValidationResponse> {
  logger.info('Validating week schedule changes', {
    weekStart: weekStart.toISOString().split('T')[0],
  });

  try {
    const response = await fetchWithAuth(API_ENDPOINTS.INSTRUCTOR_AVAILABILITY_VALIDATE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_week: currentWeek,
        saved_week: savedWeek,
        week_start: weekStart.toISOString().split('T')[0],
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      logger.error('Week validation failed', undefined, {
        status: response.status,
        error,
      });
      throw new Error(error.detail || 'Failed to validate changes');
    }

    const validationResult = await response.json();
    logger.info('Week validation completed', {
      hasConflicts: validationResult.has_conflicts,
      changesCount: validationResult.changes?.length || 0,
    });

    return validationResult;
  } catch (error) {
    logger.error('Week validation error', error);
    throw error;
  }
}

/**
 * Fetch booking preview information
 *
 * Retrieves a lightweight preview of a booking, typically used for
 * modal previews in the calendar view. Contains essential information
 * without full booking details.
 *
 * @param bookingId - The ID of the booking to preview
 * @returns Promise<BookingPreview> - Preview information for the booking
 * @throws Error if the fetch fails
 *
 * @example
 * ```ts
 * try {
 *   const preview = await fetchBookingPreview(bookingId);
 *   // Display preview in modal
 * } catch (error) {
 *   // Handle error
 * }
 * ```
 */
export async function fetchBookingPreview(bookingId: string): Promise<BookingPreview> {
  logger.info('Fetching booking preview', { bookingId });

  try {
    const response = await fetchWithAuth(`${API_ENDPOINTS.BOOKINGS}/${bookingId}/preview`);

    if (!response.ok) {
      logger.error('Failed to fetch booking preview', undefined, {
        bookingId,
        status: response.status,
      });
      throw new Error('Failed to fetch booking preview');
    }

    const preview = await response.json();
    logger.debug('Booking preview fetched successfully', {
      bookingId,
      hasStudentInfo: !!(preview.student_first_name && preview.student_last_name),
    });

    return preview;
  } catch (error) {
    logger.error('Booking preview fetch error', error, { bookingId });
    throw error;
  }
}

/**
 * Fetch upcoming bookings for the current user
 *
 * @param limit - Maximum number of bookings to return (default: 5)
 * @returns Promise<UpcomingBooking[]> - Array of upcoming bookings
 */
export async function getUpcomingBookings(limit: number = 5): Promise<UpcomingBooking[]> {
  logger.info('Fetching upcoming bookings', { limit });

  try {
    const response = await fetchWithAuth(`${API_ENDPOINTS.BOOKINGS_UPCOMING}?limit=${limit}`);

    if (!response.ok) {
      logger.error('Failed to fetch upcoming bookings', undefined, {
        status: response.status,
      });
      throw new Error('Failed to fetch upcoming bookings');
    }

    const data = await response.json();
    // Now always returns consistent paginated format
    logger.debug('Upcoming bookings fetched successfully', {
      count: data.items.length,
      total: data.total,
    });

    return data.items;
  } catch (error) {
    logger.error('Upcoming bookings fetch error', error);
    throw error;
  }
}

/**
 * Type guard to check if an error is a network error
 *
 * @param error - The error to check
 * @returns boolean indicating if it's a network error
 */
export function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError && error.message === 'Failed to fetch';
}

/**
 * Type guard to check if a response indicates authentication failure
 *
 * @param response - The fetch response to check
 * @returns boolean indicating if it's an auth failure (401)
 */
export function isAuthError(response: Response): boolean {
  return response.status === 401;
}

/**
 * Helper to extract error message from API response
 *
 * @param response - The fetch response
 * @returns Promise<string> - The error message
 */
export async function getErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data.detail || data.message || 'An error occurred';
  } catch {
    return `Error: ${response.statusText}`;
  }
}
