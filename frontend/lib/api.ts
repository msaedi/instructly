// frontend/lib/api.ts
import { WeekSchedule, WeekValidationResponse } from '@/types/availability';
import { BookingPreview, UpcomingBooking } from '@/types/booking';
import { logger } from '@/lib/logger';
import { API_BASE, withApiBase } from '@/lib/apiBase';

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

/** @deprecated Use API_BASE from @/lib/apiBase instead */
export const API_URL = API_BASE;

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
  const method = options.method || 'GET';

  // Log the API call
  logger.info(`API ${method} ${endpoint}`, {
    hasBody: !!options.body,
  });

  // Start timing the request
  const timerLabel = `API ${method} ${endpoint}`;
  logger.time(timerLabel);

  try {
    const url = withApiBase(endpoint);
    const baseHeaders = { ...(options.headers || {}) } as Record<string, string>;
    const response = await fetch(url, {
      ...options,
      // Always include credentials to support cookie-based sessions across all endpoints
      credentials: 'include',
      headers: baseHeaders,
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
        const errorBody: { detail?: string; message?: string; [key: string]: unknown } =
          (await response.clone().json()) as { detail?: string; message?: string; [key: string]: unknown };
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
      } catch {
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
  // Onboarding helpers
  NYC_ZIP_CHECK: '/api/addresses/zip/is-nyc',
  STRIPE_IDENTITY_SESSION: '/api/payments/identity/session',
  STRIPE_IDENTITY_REFRESH: '/api/payments/identity/refresh',
  R2_SIGNED_UPLOAD: '/api/uploads/r2/signed-url',
  R2_PROXY_UPLOAD: '/api/uploads/r2/proxy',
  PROFILE_PICTURE_FINALIZE: '/api/users/me/profile-picture',
  PROFILE_PICTURE_URL: (userId: string) => `/api/users/${userId}/profile-picture-url`,
  CONNECT_STATUS: '/api/payments/connect/status',

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
      const error: { detail?: string; message?: string; [key: string]: unknown } =
        (await response.json()) as { detail?: string; message?: string; [key: string]: unknown };
      logger.error('Week validation failed', undefined, {
        status: response.status,
        error,
      });
      throw new Error(error.detail || 'Failed to validate changes');
    }

    const validationResult: WeekValidationResponse = (await response.json()) as WeekValidationResponse;
    logger.info('Week validation completed', {
      hasConflicts: validationResult.summary.has_conflicts,
      changesCount: validationResult.details.length || 0,
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

    const preview: BookingPreview = (await response.json()) as BookingPreview;
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

    const data: { items: UpcomingBooking[]; total: number } =
      (await response.json()) as { items: UpcomingBooking[]; total: number };
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

// ========== Onboarding helper API calls ==========

export async function checkIsNYCZip(zip: string): Promise<{ is_nyc: boolean; borough?: string }> {
  const res = await fetchAPI(`${API_ENDPOINTS.NYC_ZIP_CHECK}?zip=${encodeURIComponent(zip)}`);
  if (!res.ok) throw new Error('ZIP check failed');
  return res.json();
}

export async function createStripeIdentitySession(): Promise<{ verification_session_id: string; client_secret: string }>{
  const res = await fetchWithAuth(API_ENDPOINTS.STRIPE_IDENTITY_SESSION, { method: 'POST' });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
}

export async function createSignedUpload(params: {
  filename: string;
  content_type: string;
  size_bytes: number;
  purpose: 'background_check' | 'profile_picture';
}): Promise<{ upload_url: string; object_key: string; public_url?: string; headers: Record<string, string> }>{
  const res = await fetchWithAuth(API_ENDPOINTS.R2_SIGNED_UPLOAD, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
}

export async function proxyUploadToR2(params: {
  key: string;
  file: Blob;
  contentType: string;
}): Promise<{ ok: boolean; url?: string | null }>{
  const formData = new FormData();
  formData.append('key', params.key);
  formData.append('content_type', params.contentType);
  formData.append('file', params.file);

  const res = await fetchWithAuth(API_ENDPOINTS.R2_PROXY_UPLOAD, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json() as Promise<{ ok: boolean; url?: string | null }>;
}

export async function finalizeProfilePicture(object_key: string): Promise<{ success: boolean; message: string }>{
  const res = await fetchWithAuth(API_ENDPOINTS.PROFILE_PICTURE_FINALIZE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ object_key }),
  });
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
}

export async function getProfilePictureUrl(userId: string, variant: 'original' | 'display' | 'thumb' = 'display'):
  Promise<{ success: boolean; message: string; data: { url: string; expires_at: string } }>{
  const res = await fetchWithAuth(`${API_ENDPOINTS.PROFILE_PICTURE_URL(userId)}?variant=${variant}`);
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
}

export async function getConnectStatus(): Promise<{
  has_account: boolean;
  onboarding_completed: boolean;
  charges_enabled: boolean;
  payouts_enabled: boolean;
  details_submitted: boolean;
}> {
  const res = await fetchWithAuth(API_ENDPOINTS.CONNECT_STATUS);
  if (!res.ok) throw new Error(await getErrorMessage(res));
  return res.json();
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
    const data: { detail?: string; message?: string } = (await response.json()) as {
      detail?: string;
      message?: string;
    };
    return data.detail || data.message || 'An error occurred';
  } catch {
    return `Error: ${response.statusText}`;
  }
}
