import { QueryFunctionContext } from '@tanstack/react-query';
import { ApiResponse } from '@/features/shared/api/client';

/**
 * React Query API Integration
 *
 * This module provides utilities to integrate the existing API client
 * with React Query, handling errors, cancellation, and response parsing.
 */

/**
 * Base API URL from environment
 */
import { withApiBase } from '@/lib/apiBase';

/**
 * Custom error class for API errors with proper typing
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: any
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Get guest session ID from localStorage
 */
function getGuestSessionId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('guest_session_id');
}

/**
 * Get analytics headers for tracking
 */
function getAnalyticsHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};

  if (typeof window !== 'undefined') {
    // Session tracking headers
    const sessionId = localStorage.getItem('session_id');
    if (sessionId) {
      headers['X-Session-ID'] = sessionId;
    }

    // Current page for referrer analytics
    headers['X-Search-Origin'] = window.location.pathname;
  }

  return headers;
}

/**
 * Query function options type
 */
export interface QueryOptions extends RequestInit {
  params?: Record<string, string | number | boolean>;
  requireAuth?: boolean;
}

/**
 * Main query function for React Query
 *
 * This function wraps fetch to provide:
 * - Automatic auth token inclusion
 * - AbortController support for cancellation
 * - Consistent error handling
 * - Response parsing
 *
 * @example
 * ```ts
 * useQuery({
 *   queryKey: ['user'],
 *   queryFn: queryFn('/api/auth/me', { requireAuth: true })
 * })
 * ```
 */
export function queryFn<T = any>(endpoint: string, options: QueryOptions = {}) {
  return async ({ signal }: QueryFunctionContext): Promise<T> => {
    const { params, ...fetchOptions } = options;

    // Build URL using centralized API base resolver
    const fullPath = withApiBase(endpoint);
    const isAbsolute = /^https?:\/\//i.test(fullPath);
    const base = isAbsolute
      ? undefined
      : (typeof window !== 'undefined'
          ? window.location.origin
          : (process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'));
    const url = new URL(fullPath, base as string | undefined);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      });
    }

    // Build headers
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...getAnalyticsHeaders(),
      ...((fetchOptions.headers as Record<string, string>) || {}),
    };

    // Cookie-based authentication is handled automatically via credentials: 'include'
    // The backend accepts HttpOnly cookies for auth in all environments
    // Optional guest/session analytics
    const guestSessionId = getGuestSessionId();
    if (guestSessionId) {
      headers['X-Guest-Session-ID'] = guestSessionId;
    }

    try {
      const response = await fetch(url.toString(), {
        ...fetchOptions,
        headers,
        // Always include cookies for cross-site API domain
        credentials: (fetchOptions as any)?.credentials ?? 'include',
        signal, // Pass AbortSignal for query cancellation
      });

      // Parse response
      const data = await response.json();

      // Handle errors
      if (!response.ok) {
        throw new ApiError(
          data.detail || data.message || `Error: ${response.status}`,
          response.status,
          data
        );
      }

      return data;
    } catch (error) {
      // Handle network errors
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new ApiError('Network error', 0);
      }

      // Handle abort errors
      if (error instanceof Error && error.name === 'AbortError') {
        throw new ApiError('Request cancelled', 0);
      }

      // Re-throw other errors
      throw error;
    }
  };
}

/**
 * Mutation function for React Query mutations
 *
 * Similar to queryFn but designed for mutations (POST, PUT, DELETE)
 *
 * @example
 * ```ts
 * useMutation({
 *   mutationFn: mutationFn('/api/bookings', {
 *     method: 'POST',
 *     requireAuth: true
 *   })
 * })
 * ```
 */
export function mutationFn<TData = any, TVariables = any>(
  endpoint: string,
  options: QueryOptions = {}
) {
  return async (variables: TVariables): Promise<TData> => {
    const { params, ...fetchOptions } = options;

    // Build URL using centralized API base resolver
    const fullPath = withApiBase(endpoint);
    const isAbsolute = /^https?:\/\//i.test(fullPath);
    const base = isAbsolute
      ? undefined
      : (typeof window !== 'undefined'
          ? window.location.origin
          : (process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'));
    const url = new URL(fullPath, base as string | undefined);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      });
    }

    // Build headers
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...getAnalyticsHeaders(),
      ...((fetchOptions.headers as Record<string, string>) || {}),
    };
    // Cookie-based authentication is handled automatically via credentials: 'include'
    // The backend accepts HttpOnly cookies for auth in all environments

    // Cookies-only auth: rely on session cookie; backend will 401 if not authenticated
    const guestSessionId = getGuestSessionId();
    if (guestSessionId) {
      headers['X-Guest-Session-ID'] = guestSessionId;
    }

    try {
      const response = await fetch(url.toString(), {
        ...fetchOptions,
        headers,
        body: variables ? JSON.stringify(variables) : undefined,
        // Always include cookies for cross-site API domain
        credentials: (fetchOptions as any)?.credentials ?? 'include',
      });

      // Parse response
      const data = await response.json();

      // Handle errors
      if (!response.ok) {
        throw new ApiError(
          data.detail || data.message || `Error: ${response.status}`,
          response.status,
          data
        );
      }

      return data;
    } catch (error) {
      // Handle network errors
      if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new ApiError('Network error', 0);
      }

      // Re-throw other errors
      throw error;
    }
  };
}

/**
 * Helper to determine if an error is an API error
 */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/**
 * Helper to determine if an error is a network error
 */
export function isNetworkError(error: unknown): boolean {
  return isApiError(error) && error.status === 0;
}

/**
 * Helper to determine if an error is an auth error
 */
export function isAuthError(error: unknown): boolean {
  return isApiError(error) && error.status === 401;
}

/**
 * Convert legacy API response to React Query format
 *
 * This helper converts the ApiResponse<T> format from the existing
 * API client to throw errors that React Query expects
 */
export function convertApiResponse<T>(response: ApiResponse<T>): T {
  if (response.error) {
    throw new ApiError(response.error, response.status);
  }

  if (!response.data) {
    throw new ApiError('No data in response', response.status);
  }

  return response.data;
}
